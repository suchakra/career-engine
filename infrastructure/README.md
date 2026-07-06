# CareerEngine — Infrastructure (Terraform)

IaC-first GCP baseline for CareerEngine (ARCHITECTURE.md §9). `infrastructure/`
**defines** the environment so the whole platform can be stood up or torn down
with one command.

## Layout

```
infrastructure/
  modules/
    cloud_run/          Cloud Run v2 service + runtime service account
    firestore/          Firestore (Native) database
    artifact_registry/  Docker image repository
    secret_manager/     API enablement + runtime SA secretAccessor grant
    scheduler/          Cloud Scheduler job → 14-day pending-action sweep
  envs/
    dev/                Dev root (local state; scale-to-zero; Firestore DELETE)
    prod/               Prod root (GCS backend recommended; Firestore ABANDON)
```

## What gets created

| Component | Resource | Notes |
|-----------|----------|-------|
| Compute | `google_cloud_run_v2_service` + `google_service_account` | Runtime identity is the per-env SA |
| Persistence | `google_firestore_database` (Native) | Keyed by `user_id` in app code; no secrets stored |
| Registry | `google_artifact_registry_repository` (Docker) | Container images |
| Secrets | `google_project_service` + `google_project_iam_member` | **Least privilege:** runtime SA gets only `roles/secretmanager.secretAccessor` |
| Scheduling | `google_cloud_scheduler_job` | OIDC-authenticated POST to the sweep endpoint |

**Per-user BYOK keys (`ce-key-{user_id}`) are created at runtime by the app
(`auth/key_vault.py`), never by Terraform** — so no secret material is in this
config or in state.

## Variables (no secrets)

Everything is parameterized; nothing is hardcoded. Set values via
`terraform.tfvars` (gitignored) or `TF_VAR_*` env vars. See
`envs/<env>/terraform.tfvars.example`. Key variables: `project_id` (required),
`region`, `firestore_location`, `name_prefix`, `image`, `contract_version`,
`sweep_schedule`.

## Prerequisites

- Terraform `>= 1.5`.
- For `plan`/`apply`: a GCP project and credentials —
  `gcloud auth application-default login` (or a service-account key via
  `GOOGLE_APPLICATION_CREDENTIALS`), and the relevant APIs enabled.
- `fmt` and `validate` need **no** credentials.

## Usage

```bash
# Gateable with no cloud credentials (CI-friendly):
make tf-check                 # = tf-fmt + tf-validate (both env roots)

# Requires GCP credentials + a real project_id in terraform.tfvars:
cp infrastructure/envs/dev/terraform.tfvars.example infrastructure/envs/dev/terraform.tfvars
# edit terraform.tfvars → set project_id (and image once pushed)
make deploy                   # terraform -chdir=envs/dev apply
make destroy                  # terraform -chdir=envs/dev destroy
```

Prod is driven directly (guard rails on): `terraform -chdir=infrastructure/envs/prod plan` /
`apply` after configuring the GCS backend in `envs/prod/main.tf`.

## State & backends

- **dev** uses **local state** (no backend block) so `init -backend=false` +
  `validate` run anywhere.
- **prod** should use a **remote GCS backend** — uncomment and set the `backend "gcs"`
  block in `envs/prod/main.tf` before real use, so state is shared and locked.

## Rollback

- Re-`apply` a previous commit of this directory to roll forward/back declaratively.
- `make destroy` tears down **dev** (Firestore `deletion_policy = DELETE` there).
- **prod** Firestore defaults to `ABANDON` (data survives a stack `destroy`); delete the
  database deliberately if truly intended.

> CI note: only `make tf-check` runs in this repo's gates (no credentials in CI).
> `plan`/`apply` are operator steps in a credentialed environment.

## Custom domain (`career-engine.bitcrafty.cloud`)

The `domain_mapping` and `cloudflare_dns` modules in `envs/dev/main.tf` wire up
a GCP-managed TLS certificate on the custom domain. Cloudflare acts as **DNS-only
(grey cloud / `proxied = false`)** — GCP validates the A/AAAA records and manages
the certificate. The first-time setup is a **two-phase apply**.

### Required secrets / env vars

| Variable | How to set | Notes |
|---|---|---|
| `TF_VAR_cloudflare_api_token` | CI secret or local env | Cloudflare API token scoped to _Edit zone DNS_ for `bitcrafty.cloud`. Create at Cloudflare Dashboard → My Profile → API Tokens → Create Token → **Edit zone DNS**. Never commit. |
| `TF_VAR_cloudflare_zone_id` | `terraform.tfvars` or env | Zone ID for `bitcrafty.cloud` — visible in Cloudflare Dashboard → Overview sidebar. Not sensitive; can live in `terraform.tfvars` (gitignored). |
| `TF_VAR_google_domain_verification_txt` | env only (one-time) | TXT value from Google domain verification (see Phase 1 below). Only needed for the initial bootstrap apply. |

### Phase 1 — DNS verification (one-time bootstrap)

```bash
# 1. Obtain the Google domain verification TXT value:
gcloud domains verify career-engine.bitcrafty.cloud
# Copy the TXT string it prints (google-site-verification=...).

# 2. Export required vars:
export TF_VAR_cloudflare_api_token="<token>"
export TF_VAR_cloudflare_zone_id="<zone-id>"
export TF_VAR_google_domain_verification_txt="<google-site-verification=...>"

# 3. Apply only the TXT verification record:
terraform -chdir=infrastructure/envs/dev apply \
  -target=module.cloudflare_dns.cloudflare_dns_record.verification

# 4. Wait ~30 s for DNS propagation, then complete Google's verification:
gcloud domains verify career-engine.bitcrafty.cloud --verify
# (or: Cloud Console → Cloud Run → Domain Mappings → Verify)
```

### Phase 2 — Full apply (steady state)

```bash
# 5. Run full apply (creates domain_mapping, A/AAAA records, updates redirect URI):
terraform -chdir=infrastructure/envs/dev apply

# 6. SSL provisioning takes 5–30 min; monitor status:
gcloud run domain-mappings describe \
  --domain career-engine.bitcrafty.cloud \
  --region us-central1

# 7. ONE-TIME MANUAL: add the custom-domain redirect URI to the OAuth 2.0 client.
#    Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs →
#    edit the web client → Authorized redirect URIs → Add:
#      https://career-engine.bitcrafty.cloud/_stcore/oauth2callback
#    (the existing *.run.app URI can remain; both coexist safely)
```

### Ongoing (after first apply)

Normal `terraform apply` workflow — domain mapping and DNS records are idempotent.
The `CE_AUTH_REDIRECT_URI` change in `envs/dev/main.tf` causes a new Cloud Run
revision to deploy automatically on `apply` (no manual step).

## Access / auth posture (handoff for Phase 2B)

The Cloud Run service uses `ingress = INGRESS_TRAFFIC_ALL` but **no `allUsers`
`run.invoker` binding** — so it requires authentication for every request
(correct security posture). Consequences:

- The Cloud Scheduler sweep works because the scheduler module grants the
  invoker SA `roles/run.invoker` (OIDC). 
- A **browser hitting the service URL directly will get HTTP 403.** Reaching the
  Streamlit app from a browser needs Identity-Aware Proxy (IAP) or a
  Firebase-Hosting/Identity-Platform proxy — wired in **Phase 2B**. Do not add a
  public `allUsers` invoker binding to "fix" 403s; route through authenticated
  access instead.

