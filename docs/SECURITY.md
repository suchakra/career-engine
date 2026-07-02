# CareerEngine — Security posture & review log

> Status: `active` · Last reviewed: 2026-07-02
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

**Confirmed NOT vulnerable (checked this pass):**
- Dev escape hatch (`dev_user_id` / `dev_gemini_key`) is honored only in the CLI
  auth path (`auth/cli_auth.py`, `cli/app.py`) — the deployed web path uses
  `FirebaseAuthProvider` and never consults it, so it is not a prod auth bypass.
- PDF rendering (`tools/pdf_renderer.py`) uses Jinja2 with autoescape on, no
  `|safe`, and no user-controlled URL attributes → model output can't inject HTML
  or drive WeasyPrint into local-file/SSRF fetches.
- Secret IDs / Firestore doc paths are keyed by the token `sub` (issuer-controlled,
  charset-restricted), not free-form user input → no path traversal.
