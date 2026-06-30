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
