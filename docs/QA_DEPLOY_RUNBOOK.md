# Deploy `qa` (see the new UI) — repeatable, one command

> **Status:** `active` · 2026-07-11 · **What:** deploy the new Next.js + FastAPI app to a **`qa` Cloud Run
> service in the same project as dev** (scale-to-zero → ~free when idle), so it's viewable in a browser
> **without touching the Kaggle-visible `dev` service**. Codified so it runs from CI with one command.

**Topology:** `qa` is a second Cloud Run service (`career-engine-qa-app`) in the existing project. It reuses
the project's `(default)` Firestore (shares dev's data — fine for a solo preview), dev's Artifact Registry
repo, and the existing WIF/deployer SA. New stack = Firebase auth (no Streamlit OIDC). Terraform:
[`infrastructure/envs/qa`](../infrastructure/envs/qa).

---

## What I need from you — ONE-TIME bootstrap (~15 min, Console + repo settings)

These are the only things an agent can't do. After this, deploys are one command and repeatable.

### A. Add Firebase to the project + get the web config
1. <https://console.firebase.google.com> → **Add project → "add to an existing Google Cloud project"** →
   pick **`gen-lang-client-0513394764`**.
2. **Build → Authentication → Get started → Sign-in method → Google → Enable** (set a support email) → Save.
3. **Project settings (gear) → Your apps → Web (`</>`) → Register app** (nickname `career-engine`, no
   Hosting). From the shown config copy `apiKey`, `authDomain`, `projectId`.

### B. Set 3 GitHub repository Variables
**Settings → Secrets and variables → Actions → Variables → New repository variable** (these are **public**
Firebase config, not secrets — repo *Variables*, not Secrets):

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_FIREBASE_API_KEY` | `config.apiKey` (e.g. `AIza…`) |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | `config.authDomain` (e.g. `gen-lang-client-0513394764.firebaseapp.com`) |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | `config.projectId` (= `gen-lang-client-0513394764`) |

> The other deploy variables (`GCP_PROJECT_ID`, `GCP_WIF_PROVIDER`, `GCP_DEPLOY_SA`, `TF_STATE_BUCKET`,
> `AR_LOCATION`) are **already set** for dev — qa reuses them (same project). Nothing else to add.

That's it. **Tell me when A + B are done** and I run the deploy (step below) myself.

---

## The deploy — repeatable (I run this; you can too)

Runs only after this change is merged to `master` (workflow_dispatch reads the default branch):

```bash
gh workflow run deploy.yml --ref master -f environment=qa
gh run watch "$(gh run list --workflow=deploy.yml -L1 --json databaseId -q '.[0].databaseId')"
```

CI does: build the image **with the Firebase build args** → push to Artifact Registry → `terraform apply`
the `qa` service → prints the URL in the run summary. Re-run anytime after a change (each build is a new
`qa-<sha>` tag). Get the URL any time:

```bash
gcloud run services describe career-engine-qa-app --region us-central1 \
  --format='value(status.url)'
```

### C. After the FIRST deploy — authorize the domain (one-time)
Google sign-in popups only work from authorized domains:
- Firebase Console → **Authentication → Settings → Authorized domains → Add domain** → paste the **host**
  of the qa URL (e.g. `career-engine-qa-app-…-uc.a.run.app`, no `https://`, no path).

### D. See it 🎉
Open the URL → **Sign in with Google** → set your **Gemini key** (BYOK) → try Grill / Tailor.
`curl <qa-url>/api/health` → `{"status":"ok"}` confirms the backend.

---

## Tenet: dev is protected
- `qa` is the **default** deploy target. Deploying **dev** is blocked unless you pass
  `-f confirm_dev_cutover=true` (a guard step fails the run otherwise) — so dev can never be cut over to the
  new stack by accident while Kaggle reviewers might drop in.
- `qa` is a **separate service** in the same project; deploying/redeploying/deleting it never touches the
  running dev service. Tear down with `gcloud run services delete career-engine-qa-app --region us-central1`.

## Known risk (flagged)
If sign-in succeeds in the popup but the app bounces back to login / API calls return 401: the backend's
Google `tokeninfo` verifier may not accept Firebase `securetoken` JWTs. The issuer/audience are already
wired correctly (from `FIREBASE_PROJECT_ID`); the fix is a ~15-line swap of the verifier in
`auth/firebase_auth.py` to `firebase-admin`'s `verify_id_token`. Ping me and I'll do it.

## Promote to dev (only when validated)
Same image, deliberately: `gh workflow run deploy.yml --ref master -f environment=dev -f confirm_dev_cutover=true`.
Note dev's Terraform (`envs/dev`) still carries the Streamlit `CE_AUTH_*` config; reconcile it to the new
stack (Firebase env, drop `auth_secrets`) before promoting. Validate on qa first.
