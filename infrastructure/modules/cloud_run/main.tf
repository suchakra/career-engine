# CareerEngine — Cloud Run service + runtime service account.
#
# The runtime service account is the platform identity at run time. It is
# granted least-privilege Secret Manager access by the secret_manager module
# (it receives this SA's email), so the app can read per-user BYOK keys
# (ce-key-{user_id}) and nothing broader. No secrets are set here.

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0, < 7.0"
    }
  }
}

variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "Region for the Cloud Run service."
}

variable "service_name" {
  type        = string
  description = "Cloud Run service name."
}

variable "service_account_id" {
  type        = string
  description = "Account ID (local part) for the runtime service account."
}

variable "image" {
  type        = string
  description = "Fully-qualified container image to deploy."
}

variable "contract_version" {
  type        = string
  description = "CONTRACT_VERSION stamped into the runtime environment."
}

variable "min_instances" {
  type        = number
  description = "Minimum Cloud Run instances (0 = scale to zero)."
  default     = 0
}

variable "max_instances" {
  type        = number
  description = "Maximum Cloud Run instances."
  default     = 4
}

variable "cpu" {
  type        = string
  description = "CPU limit per instance."
  default     = "1"
}

variable "memory" {
  type        = string
  description = "Memory limit per instance."
  default     = "512Mi"
}

resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = var.service_account_id
  display_name = "CareerEngine Cloud Run runtime (${var.service_name})"
}

resource "google_cloud_run_v2_service" "app" {
  project  = var.project_id
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime.email

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.image

      env {
        name  = "CONTRACT_VERSION"
        value = var.contract_version
      }

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
      }
    }
  }
}

output "service_account_email" {
  description = "Email of the runtime service account (input to IAM bindings)."
  value       = google_service_account.runtime.email
}

output "service_uri" {
  description = "HTTPS URL of the deployed Cloud Run service."
  value       = google_cloud_run_v2_service.app.uri
}

output "service_name" {
  description = "Cloud Run service name."
  value       = google_cloud_run_v2_service.app.name
}
