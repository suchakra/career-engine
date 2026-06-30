# CareerEngine — prod environment root.
#
# Same module composition as dev with production-safe defaults: Firestore is
# NOT auto-deleted on teardown (deletion_policy defaults to ABANDON in the
# module), and Cloud Run keeps a warm instance. Configure a remote GCS backend
# before real use (see the commented backend block + README).

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0, < 7.0"
    }
  }

  # Recommended for prod — uncomment and set a real bucket:
  # backend "gcs" {
  #   bucket = "your-prod-tfstate-bucket"
  #   prefix = "career-engine/prod"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

module "artifact_registry" {
  source        = "../../modules/artifact_registry"
  project_id    = var.project_id
  region        = var.region
  repository_id = "${var.name_prefix}-images"
}

module "firestore" {
  source     = "../../modules/firestore"
  project_id = var.project_id
  location   = var.firestore_location
  # deletion_policy defaults to ABANDON — prod data is not torn down with the stack.
}

module "cloud_run" {
  source             = "../../modules/cloud_run"
  project_id         = var.project_id
  region             = var.region
  service_name       = "${var.name_prefix}-app"
  service_account_id = "${var.name_prefix}-run"
  image              = var.image
  contract_version   = var.contract_version
  min_instances      = 1
  max_instances      = 10
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
