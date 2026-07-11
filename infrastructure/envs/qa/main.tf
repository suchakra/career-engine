# CareerEngine — qa environment root.
#
# A PRE-DEV PREVIEW service in the SAME GCP project as dev (NOT a new project) — the
# operator wanted a cheap, near-dev env, not a paid isolated one. It is a SECOND Cloud
# Run service with its own *.run.app URL; dev is untouched. `min_instances = 0` → it
# scales to zero, so it costs ~nothing when idle.
#
# New stack (Next.js + FastAPI, Firebase auth), so vs dev's Streamlit root this OMITS:
#   - Firestore (the project's `(default)` DB already exists — created by dev; qa reuses
#     it, so qa SHARES dev's data — acceptable for a solo preview, per operator).
#   - auth_secrets / CE_AUTH_* / cookie secret (Firebase replaces the Streamlit OIDC).
#   - custom domain / Cloudflare / scheduler-sweep (not needed to preview the UI).
#
# State: reuse dev's GCS bucket with a distinct prefix (envs/qa) — see deploy.yml.

terraform {
  required_version = ">= 1.5"
  backend "gcs" {} # bucket/prefix supplied at init via -backend-config

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0, < 7.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "current" {
  project_id = var.project_id
}

# Artifact Registry: qa REUSES dev's existing `career-engine-dev-images` repo (same project)
# rather than creating its own — this sidesteps the first-deploy chicken-and-egg (the CI build
# pushes the image BEFORE `terraform apply` runs). deploy.yml tags qa images `qa-<sha>` there.

module "cloud_run" {
  source             = "../../modules/cloud_run"
  project_id         = var.project_id
  region             = var.region
  service_name       = "${var.name_prefix}-app"
  service_account_id = "${var.name_prefix}-run"
  image              = var.image
  contract_version   = var.contract_version

  min_instances = 0 # scale to zero — ~no idle cost
  max_instances = 2
  # concurrency=1: one request at a time per instance, so the process-global model-client
  # factory (BYOK) can't cross-contaminate between users. The multi-tenant isolation model
  # is revisited in Phase 11.C; concurrency=1 is the safe posture for a shared-project preview.
  max_concurrency = 1

  allow_unauthenticated = true # public web app; sign-in is enforced at the app layer (Firebase)

  # New-stack runtime env — NO Streamlit CE_AUTH_* / cookie secret. FIREBASE_PROJECT_ID is
  # what makes auth/firebase_auth.py pin securetoken.google.com/<project> + the project as the
  # accepted token audience, so Firebase Web SDK sign-in tokens verify.
  env = {
    GCP_PROJECT_ID      = var.project_id
    GCP_REGION          = var.region
    FIREBASE_PROJECT_ID = var.firebase_project_id != "" ? var.firebase_project_id : var.project_id
    ACCESS_MODE         = "BYOK"
  }
}

# Runtime SA: Firestore access (per-user workspace + discovery sessions). Additive IAM
# member — coexists with dev's runtime SA binding in the same project.
resource "google_project_iam_member" "runtime_datastore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${module.cloud_run.service_account_email}"
}

# Runtime SA: CREATE/rotate per-user BYOK key secrets (ce-key-*) — the app writes a user's
# key on save. Scoped to ce-key-* only (least privilege; mirrors dev).
resource "google_project_iam_member" "runtime_key_writer" {
  project = var.project_id
  role    = "roles/secretmanager.admin"
  member  = "serviceAccount:${module.cloud_run.service_account_email}"
  condition {
    title       = "ce-key-secrets-only"
    description = "Limit to per-user BYOK key secrets"
    expression  = "resource.name.startsWith(\"projects/${data.google_project.current.number}/secrets/ce-key-\")"
  }
}

# Runtime SA: READ ce-key-* secrets (scoped) — the app reads a user's key at grill/tailor time.
module "secret_manager" {
  source                = "../../modules/secret_manager"
  project_id            = var.project_id
  project_number        = data.google_project.current.number
  service_account_email = module.cloud_run.service_account_email
}

output "service_uri" {
  description = "qa Cloud Run service URL (open this in a browser)."
  value       = module.cloud_run.service_uri
}
