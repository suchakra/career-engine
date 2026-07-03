# CareerEngine — dev environment root.
#
# Wires the reusable modules into a deployable dev stack. State is local by
# default (no backend block) so `init`/`validate`/`fmt` run with no cloud
# credentials; `plan`/`apply` require GCP credentials (see README). For prod,
# configure a remote GCS backend.

terraform {
  required_version = ">= 1.5"
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

# Enable the APIs the stack needs (idempotent — adopts already-enabled ones).
# Kept in Terraform so a fresh project is reproducible from code (IaC all the way).
resource "google_project_service" "apis" {
  for_each = toset([
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
  max_instances      = 2

  # Public web app; sign-in is enforced at the app layer (Streamlit OIDC).
  allow_unauthenticated = true

  env = {
    GCP_PROJECT_ID       = var.project_id
    GCP_REGION           = var.region
    CE_AUTH_CLIENT_ID    = var.auth_client_id
    CE_AUTH_REDIRECT_URI = var.auth_redirect_uri
    CE_AUTH_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"
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
  service_account_email = module.cloud_run.service_account_email
}

module "scheduler" {
  source                        = "../../modules/scheduler"
  project_id                    = var.project_id
  region                        = var.region
  job_name                      = "${var.name_prefix}-pending-action-sweep"
  schedule                      = var.sweep_schedule
  target_uri                    = "${module.cloud_run.service_uri}/jobs/pending-action-sweep"
  service_uri                   = module.cloud_run.service_uri
  cloud_run_service_name        = module.cloud_run.service_name
  invoker_service_account_email = module.cloud_run.service_account_email
}

output "service_uri" {
  description = "Cloud Run service URL."
  value       = module.cloud_run.service_uri
}

output "image_repository_url" {
  description = "Artifact Registry Docker repo URL for pushing images."
  value       = module.artifact_registry.repository_url
}

output "secret_accessor_member" {
  description = "Runtime SA granted secretmanager.secretAccessor."
  value       = module.secret_manager.secret_accessor_member
}
