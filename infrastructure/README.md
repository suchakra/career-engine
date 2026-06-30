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
