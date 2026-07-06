# CareerEngine — Security posture & review log

> Status: `active` · Last reviewed: 2026-07-05
> Companion to [ARCHITECTURE.md](ARCHITECTURE.md) §5 (identity & secrets). Status
> of security work is tracked in [PROGRESS.md](PROGRESS.md); this file is the
> design truth for the threat model and the review findings ledger.

## Threat model (summary)
CareerEngine is **privacy-first, not zero-knowledge**. The trust boundaries that
matter:

- **Identity** — `user_id` is the stable `sub` from a verified Identity Platform /
  Google ID token. It is the namespace key for the workspace doc and the BYOK
  secret (`ce-key-{user_id}`). A forged or substituted token = cross-tenant access.
- **BYOK keys** — stored ONLY in Secret Manager, never in Firestore, never logged.
  The Cloud Run runtime SA holds `roles/secretmanager.secretAccessor` and nothing
  broader (least privilege). Anything that can make the runtime issue arbitrary
  outbound requests can therefore reach the metadata server and other users' keys.
- **User-supplied URLs / documents** — the JD scraper fetches a fully
  user-controlled URL; the resume parser ingests user-supplied bytes. Both are
  untrusted input crossing into the trusted runtime.

## Review log

### 2026-07-02 — Phase 3 targeted security review (branch `security/phase3-review`)
Focused audit of key-handling, IAM least-privilege, and the scraper + document
ingest surfaces. Two exploitable findings, both fixed on this branch:

1. **Auth — missing audience/issuer validation (HIGH).**
   `FirebaseAuthProvider` verified an ID token's signature/expiry via Google's
   `tokeninfo` endpoint but never checked `aud`/`iss`. Any genuinely Google-signed
   token — including one minted for an unrelated Firebase project or OAuth client —
   was accepted and its `sub` trusted as our `user_id` (confused-deputy / token
   substitution → cross-tenant impersonation). **Fix:** `set_token` now pins `iss`
   to a Google-issuer allowlist (always) and `aud` to the app's configured
   audience (`settings.firebase_project_id` / `gcp_project_id`) when known.
   Regression tests in `tests/test_firebase_auth.py::TestAudienceAndIssuerPinning`.

2. **Scraper — SSRF via user-controlled URL (MEDIUM–HIGH).**
   `fetch_raw_html` fetched an arbitrary user-supplied URL (host + scheme) with
   auto-redirects and returned the body to the caller. On Cloud Run this could
   reach the metadata service / internal VPC endpoints and exfiltrate the
   response. **Fix:** `_assert_safe_url` enforces an http/https scheme allowlist,
   blocks the metadata hostname, and rejects any host resolving to a private /
   loopback / link-local / reserved address; redirects are followed manually and
   revalidated per hop. Regression tests in
   `tests/test_web_scraper.py::TestScraperSsrfGuards`.

**Residual risks (accepted, with compensating controls):**
- **DNS rebinding in the scraper (low).** `_assert_safe_url` resolves and validates
  the host, but httpx re-resolves at connect time, so an attacker-controlled domain
  with a low-TTL record could pass validation (public IP) then resolve to an internal
  address at connect. A complete app-layer fix requires an IP-pinning transport or an
  egress proxy (out of scope here). Compensating controls: (a) the JD fetch is a
  single-user-scoped action returning low-value content; (b) on Cloud Run the default
  egress has no route to RFC1918 / the metadata service; (c) metadata reads
  additionally require a `Metadata-Flavor: Google` header the scraper never sends.
  **Production control of record:** restrict Cloud Run egress (VPC egress firewall)
  so internal ranges and `169.254.169.254` are unreachable.

**Confirmed NOT vulnerable (checked this pass):**
- Dev escape hatch (`dev_user_id` / `dev_gemini_key`) is honored only in the CLI
  auth path (`auth/cli_auth.py`, `cli/app.py`) — the deployed web path uses
  `FirebaseAuthProvider` and never consults it, so it is not a prod auth bypass.
- PDF rendering (`tools/pdf_renderer.py`) uses Jinja2 with autoescape on, no
  `|safe`, and no user-controlled URL attributes → model output can't inject HTML
  or drive WeasyPrint into local-file/SSRF fetches.
- Secret IDs / Firestore doc paths are keyed by the token `sub` (issuer-controlled,
  charset-restricted), not free-form user input → no path traversal.

### 2026-07-05 — Pre-GA web-auth + BYOK key-storage + IAM review
Addresses the "Required next review" checklist below. Scope: web OIDC login, BYOK
key storage + Secret Manager IAM, public Cloud Run ingress, single-user isolation,
CI/CD deployer. One finding fixed in IaC + one defensive hardening; the rest are
confirmed OK or tracked as accepted residual risks.

1. **BYOK IAM — runtime SA could read ALL project secrets (MEDIUM). Fixed (IaC).**
   The Cloud Run runtime SA held `roles/secretmanager.secretAccessor` at the
   **project level** (`modules/secret_manager`), so a compromised instance could read
   every secret — including the OAuth **client secret** and session **cookie secret**,
   not just users' BYOK keys. **Fix:** the module grant is now **conditioned to
   `ce-key-*`** (read only per-user BYOK keys), mirroring the existing `ce-key-*` write
   condition; the two OIDC auth secrets the container needs at startup are granted
   **per-secret** (`google_secret_manager_secret_iam_member`) in the dev env root. Net
   (dev): the runtime SA can read users' BYOK keys + exactly those two auth secrets, and
   nothing else. (Prod omits the per-secret auth grants — it doesn't mount those secrets
   at all — so its runtime SA has only the scoped `ce-key-*` read.) `make tf-check` green
   (dev + prod). *Operator note:* on the first
   `apply` that scopes the project-level read, the per-secret grants must propagate
   before a NEW Cloud Run revision mounts the secrets; the running revision keeps its
   mounted values, so there is no downtime.

2. **BYOK — `user_id` used to build a secret resource id (defensive hardening).**
   `user_id` is the OIDC `sub` (Google issues a numeric subject), but
   `SecretManagerKeyVault._secret_id` now validates it against `[A-Za-z0-9_-]{1,200}`
   and raises `KeyVaultError` otherwise — belt-and-braces so a malformed/hostile
   subject can never produce an unexpected or path-like `ce-key-*` id. Tests in
   `tests/test_key_vault.py::TestUserIdValidation`.

**Confirmed OK (checked this pass):**
- **`st.user` → `user_id` trust boundary.** Streamlit native OIDC (`st.login`) verifies
  the Google ID token (Authlib) before populating `st.user`; `_current_user_id` trusts
  only the verified `sub` claim, never `email`. Redirect URI is pinned via
  `CE_AUTH_REDIRECT_URI` + the OAuth client config; the client/cookie secrets live only
  in Secret Manager and are injected as env at startup (never in state/logs).
- **Revoke/replace** (`KeyVault.delete_key` + "Remove key" UI) fully deletes the secret
  (idempotent) and no key material is logged or persisted outside Secret Manager.
- **Public ingress.** The OIDC sweep endpoint is still **not mounted** on the served
  Streamlit app (no HTTP route), so public ingress never fronts it. (When mounted, split
  it into a separate `allow_unauthenticated=false` service — tracked below.)

**Residual risks (accepted for the single-user demo; required before multi-user GA):**
- **Multi-user model-client isolation.** The web grill installs the BYOK client via a
  process-global factory; dev runs `max_instances=1` (single-user). The real fix is
  contextvar/thread-local client isolation — required before multi-user GA.
- **CI/CD deployer SA breadth.** `career-engine-deployer` holds broad admin roles for a
  full `terraform apply`; curate to least-privilege and add a plan-only identity for PRs.
- **CMEK / key TTL + rotation reminders** and enabling **Cloud Audit Logs** on Secret
  Manager access remain future hardening.

## Required next review — web auth + BYOK key storage (flagged 2026-07-03)

Status: **✅ COMPLETED 2026-07-05** — see the "Pre-GA web-auth + BYOK key-storage +
IAM review" entry above (runtime-SA read scope fixed in IaC + `user_id` validation
hardening; `st.user` trust boundary, revoke, and public-ingress posture confirmed OK;
multi-user isolation, deployer-SA curation, CMEK/audit-logs tracked as residual). The
original checklist that pass covered:

- **Web OIDC login** (`web/streamlit_app.py`, Streamlit `st.login`) — session/cookie
  handling, the OAuth consent scope, redirect-URI pinning, and the `st.user` →
  `user_id` trust boundary.
- **Storing users' (paid) BYOK Gemini keys** in Secret Manager (`web/grill_ui.py` →
  `SecretManagerKeyVault`). Encryption at rest (Secret Manager AES-256) + in transit
  (TLS) are covered by GCP defaults, but the operational controls need hardening:
  - **IAM scope** — the Cloud Run runtime SA currently has project-level
    `secretAccessor` and needs write to store keys. Scope this: read-only where
    possible, and name-conditioned write limited to `ce-key-*` (custom role / IAM
    condition) so a compromised instance can't read/rotate *all* secrets (incl. the
    OAuth client + cookie secrets).
  - **Consent + audit** — explicit user consent to storage (a line is shown in the
    UI); enable Cloud Audit Logs on Secret Manager access.
  - **Revoke/replace** — implemented (`KeyVault.delete_key` + the "Remove key" UI);
    verify it fully deletes and that no copy lingers in logs/session.
  - Consider CMEK / envelope encryption and key TTL/rotation reminders.
- **Public Cloud Run ingress** (`allow_unauthenticated`) — required for the web app.
  The OIDC sweep endpoint is currently **not mounted** on the served Streamlit app
  (no HTTP route), so it is not reachable via the public URL (the scheduler's daily
  POST 404s). Before the sweep is mounted, split it into a **separate private**
  (`allow_unauthenticated=false`) service so public ingress never fronts it.
- **Single-user isolation (demo):** the web grill installs the BYOK model client via
  a process-global factory. Dev Cloud Run runs `max_instances=1` (one server; keeps
  a user's Streamlit session pinned). Concurrency is left at the default — setting it
  to 1 broke Streamlit (it needs many concurrent connections). So the multi-user
  factory race is NOT fully prevented by infra; the demo URL is single-user, and the
  real fix is contextvar/thread-local client isolation (tracked, required before GA).
- **CI/CD deployer** — GitHub Actions deploys keyless via Workload Identity
  Federation (no stored keys; the `github-pool` provider is attribute-conditioned
  to `suchakra/career-engine`). The `career-engine-deployer` SA currently holds
  broad admin roles (run/artifactregistry/secretmanager/datastore/iam/…) to run a
  full `terraform apply`; a review should curate this down to the minimum and
  consider a separate plan-only identity for PRs.
