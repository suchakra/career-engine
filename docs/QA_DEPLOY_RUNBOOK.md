# See the new UI today — deploy to a `qa` Cloud Run service

> **Status:** `active` · 2026-07-10 · **Goal:** get the new Next.js + FastAPI app running on a **separate
> Cloud Run service** you can open in a browser, sign into, and click through — **without touching the
> Kaggle-visible `dev` service**. This is the fast path (reuses your existing GCP project); the clean
> new-project version is Phase 11.A.

**What you get:** a public URL `https://career-engine-qa-…-uc.a.run.app` serving the whole product (FastAPI
API + the static Next.js frontend, one container, same-origin). Auth = Google sign-in via Firebase; the
grill/tailor run on your own Gemini key (BYOK).

**Time:** ~20–30 min, most of it the one-time Firebase setup.

**You run this** — it needs Console clicks + secrets that an agent can't do. Copy-paste the commands.

---

## 0. Prerequisites (once)

```bash
# You're already gcloud-authed as chakraborty.sumanta@gmail.com. Set these:
export PROJECT="gen-lang-client-0513394764"     # the existing dev GCP project
export REGION="us-central1"
gcloud config set project "$PROJECT"
# Docker must be running locally (Docker Desktop / engine on your laptop).
docker version >/dev/null && echo "docker OK"
```

You'll deploy from a checkout of this repo (`master`, at or after the Phase-10 completion commit).

---

## 1. Firebase setup (Console — the part only you can do)

The new stack authenticates with **Firebase Auth** (not the old Streamlit OIDC). Add Firebase to the
existing project and get a web-app config.

1. Go to <https://console.firebase.google.com> → **Add project** → **"Add Firebase to an existing Google
   Cloud project"** → pick **`gen-lang-client-0513394764`**. Accept defaults.
2. **Build → Authentication → Get started → Sign-in method → Google → Enable** (set a support email) →
   **Save**.
3. **Project settings (gear) → General → Your apps → Web (`</>`) → Register app** (nickname `career-engine-qa`,
   no Hosting). Copy the shown config — you need three values:

```bash
# From the Firebase web config object:
export NEXT_PUBLIC_FIREBASE_API_KEY="AIza…"                       # config.apiKey
export NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN="$PROJECT.firebaseapp.com" # config.authDomain
export NEXT_PUBLIC_FIREBASE_PROJECT_ID="$PROJECT"                  # config.projectId (== the GCP project)
```

> These are **public** client config, not secrets. `authDomain` is normally `<project>.firebaseapp.com`.

---

## 2. Build the image (frontend config baked in at build time)

`output: export` bakes `NEXT_PUBLIC_*` into the JS **at build time**, so they're passed as `--build-arg`.
`NEXT_PUBLIC_API_BASE_URL` is **empty** on purpose — same origin, the client calls `/api/...`.

```bash
export IMAGE="$REGION-docker.pkg.dev/$PROJECT/career-engine-dev-images/qa:$(date +%Y%m%d-%H%M)"
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet

docker build \
  --build-arg NEXT_PUBLIC_API_BASE_URL="" \
  --build-arg NEXT_PUBLIC_FIREBASE_API_KEY="$NEXT_PUBLIC_FIREBASE_API_KEY" \
  --build-arg NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN="$NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN" \
  --build-arg NEXT_PUBLIC_FIREBASE_PROJECT_ID="$NEXT_PUBLIC_FIREBASE_PROJECT_ID" \
  -t "$IMAGE" .

docker push "$IMAGE"
```

> Reuses the existing `career-engine-dev-images` Artifact Registry repo (no new repo needed). If push 403s,
> run `gcloud artifacts repositories list --location=$REGION` to confirm the repo name.

---

## 3. Deploy the `qa` Cloud Run service

Reuses the existing **runtime service account** `career-engine-dev-run` (it already has Firestore access +
permission to read/write per-user BYOK `ce-key-*` secrets). Runtime env: **`FIREBASE_PROJECT_ID` is what
makes the backend accept Firebase sign-in tokens** (it pins `securetoken.google.com/<project>` as the
allowed issuer + `<project>` as the audience).

```bash
export RUNTIME_SA="career-engine-dev-run@$PROJECT.iam.gserviceaccount.com"
gcloud iam service-accounts describe "$RUNTIME_SA" >/dev/null && echo "runtime SA OK"

gcloud run deploy career-engine-qa \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "$RUNTIME_SA" \
  --port 8080 \
  --cpu 1 --memory 512Mi \
  --min-instances 0 --max-instances 2 \
  --set-env-vars "GCP_PROJECT_ID=$PROJECT,GCP_REGION=$REGION,FIREBASE_PROJECT_ID=$PROJECT,ACCESS_MODE=BYOK"

export QA_URL="$(gcloud run services describe career-engine-qa --region "$REGION" --format='value(status.url)')"
echo "QA URL: $QA_URL"
```

> Note: no Streamlit `CE_AUTH_*` vars, no Firestore provisioning (it reuses the project's existing
> `(default)` database — so this qa shares dev's data, which is fine for a preview), `concurrency` is the
> default (the old `=1` Streamlit pin is gone).

---

## 4. Let Firebase trust the Cloud Run domain

Google sign-in popups only work from **authorized domains**.

- Firebase Console → **Authentication → Settings → Authorized domains → Add domain** → paste the **host**
  of `$QA_URL` (e.g. `career-engine-qa-abcxyz-uc.a.run.app`, no `https://`, no path).

---

## 5. See it 🎉

```bash
curl -s "$QA_URL/api/health"          # → {"status":"ok"}
echo "Open in your browser: $QA_URL"
```

Open `$QA_URL` → you should see the **bitcrafty-branded login** → **Sign in with Google** → land on the
**Dashboard**. Set your **Gemini key** when prompted (BYOK), then try **Grill** and **Tailor**.

---

## 6. Verify / troubleshoot

| Symptom | Fix |
|---|---|
| `curl /api/health` fails | Deploy failed — `gcloud run services logs read career-engine-qa --region $REGION`. |
| Login page loads, but **sign-in popup blocked/`auth/unauthorized-domain`** | Step 4 (add the `*.run.app` host to Firebase Authorized domains). |
| Sign-in succeeds in the popup but the app **redirects back to login / API calls 401** | The backend rejected the Firebase token. Confirm `FIREBASE_PROJECT_ID` is set on the service (`gcloud run services describe career-engine-qa --region $REGION --format='value(spec.template.spec.containers[0].env)'`) and equals your Firebase project. If it's set and still 401s, it's the token-verifier detail (the backend uses Google's `tokeninfo` endpoint; if it doesn't accept the Firebase `securetoken` JWT, swap the verifier in `auth/firebase_auth.py` for `firebase-admin`'s `verify_id_token` — a small follow-up; flag me and I'll do it). |
| Grill/Tailor error about a key | You need to set your **own Gemini API key** in the UI (BYOK); it's stored in Secret Manager. |
| Blank page / 404 on refresh of a deep link | Static export routing — confirm the image built with `trailingSlash` (it does on `master`); rebuild if stale. |

---

## 7. Iterate + promote

- **Redeploy after changes:** re-run **Step 2 + Step 3** (new `$IMAGE` tag each time). qa is disposable.
- **Promote to dev (only once you're happy):** deploy the **same image** to the dev service — either
  `gh workflow run deploy.yml --ref master -f environment=dev` (rebuilds + `terraform apply` to dev; note
  the dev env still carries Streamlit `CE_AUTH_*` config in Terraform — that's cleaned up when the dev env
  is reconciled to the new stack), or `gcloud run services update career-engine-dev-app --region $REGION
  --image "$IMAGE" --set-env-vars FIREBASE_PROJECT_ID=$PROJECT`. **Validate on qa first.**
- **Tear down qa when done:** `gcloud run services delete career-engine-qa --region $REGION`.

---

## Notes / provenance

- This is the **fast preview path** (same project as dev, reused SA/AR, shared Firestore). The **clean,
  isolated version — a new GCP project with its own Firestore/secrets/OAuth — is Phase 11.A** (I'll build
  the Terraform `infrastructure/envs/qa` + `deploy.yml environment=qa` for that; provisioning is
  operator-gated on a new project + billing).
- **Local laptop dev** (run the stack without deploying) is Phase 11.H
  ([REFINED_PROJECT_PLAN.md](REFINED_PROJECT_PLAN.md)).
- Backend auth wiring: `auth/firebase_auth.py` (issuer/audience pinning derives from `FIREBASE_PROJECT_ID`),
  `api/auth.py`, `api/deps.py:get_auth_provider`. Build-time frontend config: `Dockerfile` `web` stage args.
