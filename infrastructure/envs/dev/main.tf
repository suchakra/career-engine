# CareerEngine — dev environment root.
#
# Wires the reusable modules into a deployable dev stack. State is local by
# default (no backend block) so `init`/`validate`/`fmt` run with no cloud
# credentials; `plan`/`apply` require GCP credentials (see README). For prod,
# configure a remote GCS backend.

terraform {
  required_version = ">= 1.5"

  # Remote state in GCS (shared by CI + local). Configured at init via
  # -backend-config (bucket/prefix) so the code stays project-agnostic.
  backend "gcs" {}

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0, < 7.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = ">= 5.0, < 6.0"
    }
  }
}

provider "cloudflare" {
  # When cloudflare_api_token is empty (CI), use a syntactically valid placeholder.
  # The provider requires a-z/A-Z/0-9/hyphens/underscores but won't make API calls
  # because all cloudflare_dns resources have count=0 when the token is absent.
  api_token = var.cloudflare_api_token != "" ? var.cloudflare_api_token : "placeholder-no-dns-resources-will-be-created"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable the APIs the stack needs (idempotent — adopts already-enabled ones).
# Kept in Terraform so a fresh project is reproducible from code (IaC all the way).
resource "google_project_service" "apis" {
  for_each = toset([
    # cloudresourcemanager is the bootstrap API the provider itself needs to manage
    # project services + IAM — enable it out-of-band first (chicken-and-egg), then
    # this block adopts it.
    "cloudresourcemanager.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "firestore.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudscheduler.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
  ])
  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

data "google_project" "current" {
  project_id = var.project_id
}

# Runtime SA: Firestore access (per-user workspace + discovery sessions).
resource "google_project_iam_member" "runtime_datastore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${module.cloud_run.service_account_email}"
}

# Runtime SA: manage per-user BYOK key secrets ONLY (ce-key-*), scoped via an IAM
# condition so a compromised instance can't create/rotate other secrets (incl. the
# OAuth client + cookie secrets). Reads of ce-key-* are ALSO scoped (secret_manager
# module condition); the two OIDC auth secrets are granted per-secret below.
# (SECURITY.md 2026-07-05 review.)
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

# The runtime SA must READ the two OIDC auth secrets — Cloud Run mounts them as
# env vars at container start. Granted PER-SECRET (not project-wide) so the scoped
# ce-key-* read condition above stays least-privilege: a compromised instance can
# read users' BYOK keys + these two auth secrets, and nothing else in the project.
# OPERATOR NOTE: on the first apply that scopes the project-level read, these
# per-secret grants must propagate before a NEW Cloud Run revision mounts the
# secrets; the already-running revision keeps its mounted values, so no downtime.
resource "google_secret_manager_secret_iam_member" "runtime_reads_client_secret" {
  project   = var.project_id
  secret_id = module.auth_secrets.client_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${module.cloud_run.service_account_email}"
}

resource "google_secret_manager_secret_iam_member" "runtime_reads_cookie_secret" {
  project   = var.project_id
  secret_id = module.auth_secrets.cookie_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${module.cloud_run.service_account_email}"
}

module "artifact_registry" {
  source        = "../../modules/artifact_registry"
  project_id    = var.project_id
  region        = var.region
  repository_id = "${var.name_prefix}-images"
}

module "firestore" {
  source          = "../../modules/firestore"
  project_id      = var.project_id
  location        = var.firestore_location
  deletion_policy = "DELETE" # dev: allow teardown
}

module "auth_secrets" {
  source     = "../../modules/auth_secrets"
  project_id = var.project_id
}

module "cloud_run" {
  source             = "../../modules/cloud_run"
  project_id         = var.project_id
  region             = var.region
  service_name       = "${var.name_prefix}-app"
  service_account_id = "${var.name_prefix}-run"
  image              = var.image
  contract_version   = var.contract_version
  min_instances      = 0
  # Single instance keeps a user's Streamlit session (session_state) pinned to one
  # server for the demo. Concurrency stays at the module default — Streamlit needs
  # many concurrent connections (websocket + static assets + reruns), so
  # concurrency=1 breaks asset loading ("Rate exceeded"). The multi-user
  # global-model-client-factory race is a documented, deferred limitation
  # (SECURITY.md): the demo URL is single-user.
  max_instances = 1

  # Public web app; sign-in is enforced at the app layer (Streamlit OIDC).
  allow_unauthenticated = true

  env = {
    GCP_PROJECT_ID    = var.project_id
    GCP_REGION        = var.region
    CE_AUTH_CLIENT_ID = var.auth_client_id
    # Streamlit's native OIDC handler lives at /oauth2callback (NOT /_stcore/...).
    # The /_stcore/oauth2callback path only returns the app shell → the callback
    # silently fails and login hangs. Keep this path in sync with the redirect URI
    # registered in the Google OAuth client.
    CE_AUTH_REDIRECT_URI = var.auth_redirect_uri != "" ? var.auth_redirect_uri : "https://${var.custom_domain}/oauth2callback"
    CE_AUTH_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"
    # The web app is BYOK (every user brings their own key), so reasoning-heavy
    # steps route to Pro on the user's key instead of Flash. ACCESS_MODE drives
    # models.registry: REASONING_HIGH → gemini-2.5-pro in BYOK mode.
    ACCESS_MODE = "BYOK"
  }

  # Values are set out-of-band (never in state); resources come from auth_secrets.
  secret_env = {
    CE_AUTH_CLIENT_SECRET = module.auth_secrets.client_secret_id
    CE_AUTH_COOKIE_SECRET = module.auth_secrets.cookie_secret_id
  }
}

module "secret_manager" {
  source                = "../../modules/secret_manager"
  project_id            = var.project_id
  project_number        = data.google_project.current.number
  service_account_email = module.cloud_run.service_account_email
}

module "sweep_job" {
  source                        = "../../modules/cloud_run_job"
  project_id                    = var.project_id
  region                        = var.region
  job_name                      = "${var.name_prefix}-sweep"
  image                         = var.image
  service_account_email         = module.cloud_run.service_account_email
  invoker_service_account_email = module.cloud_run.service_account_email
}

module "scheduler" {
  source                        = "../../modules/scheduler"
  project_id                    = var.project_id
  region                        = var.region
  job_name                      = "${var.name_prefix}-pending-action-sweep"
  schedule                      = var.sweep_schedule
  target_uri                    = module.sweep_job.job_execute_uri
  service_uri                   = "https://run.googleapis.com/"
  cloud_run_service_name        = module.cloud_run.service_name
  invoker_service_account_email = module.cloud_run.service_account_email
  # Cloud Run Jobs Execute API requires an OAuth2 access token, not an OIDC JWT.
  token_type = "oauth2"
}

module "domain_mapping" {
  source       = "../../modules/cloud_run_domain_mapping"
  project_id   = var.project_id
  region       = var.region
  domain       = var.custom_domain
  service_name = module.cloud_run.service_name
}

# Cloudflare DNS management is optional — skipped when cloudflare_api_token is
# empty (the default). DNS is a one-time bootstrap; CI deploys only need GCP.
# Run locally with TF_VAR_cloudflare_api_token set to manage DNS records.
module "cloudflare_dns" {
  count                   = var.cloudflare_api_token != "" ? 1 : 0
  source                  = "../../modules/cloudflare_dns"
  zone_id                 = var.cloudflare_zone_id
  subdomain               = "career-engine"
  google_verification_txt = var.google_domain_verification_txt
  # resource_records is decoupled from module.domain_mapping.resource_records
  # because for_each keys must be known at plan time, but Cloud Run domain mapping
  # A/AAAA records are only known after apply (GCP assigns IPs at provision time).
  # Phase 2 bootstrap: after Phase 1 apply, run `terraform output domain_mapping_resource_records`,
  # paste the result into terraform.tfvars as dns_resource_records, then apply again.
  resource_records = var.dns_resource_records
}

output "service_uri" {
  description = "Cloud Run service URL."
  value       = module.cloud_run.service_uri
}

output "image_repository_url" {
  description = "Artifact Registry Docker repo URL for pushing images."
  value       = module.artifact_registry.repository_url
}

output "domain_mapping_resource_records" {
  description = "A/AAAA DNS records from the Cloud Run domain mapping. After Phase 1 apply, paste these into terraform.tfvars as dns_resource_records, then apply again (Phase 2) to create the Cloudflare DNS records."
  value       = module.domain_mapping.resource_records
}

output "secret_accessor_member" {
  description = "Runtime SA granted secretmanager.secretAccessor."
  value       = module.secret_manager.secret_accessor_member
}
