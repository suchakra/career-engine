# Cloud Run Job for the pending-action sweep.
# Runs the career-engine image with `career-engine sweep` on demand (triggered by Cloud Scheduler).

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
  description = "Region for the Cloud Run Job."
}

variable "job_name" {
  type        = string
  description = "Cloud Run Job name."
}

variable "image" {
  type        = string
  description = "Full image URI including tag/digest."
}

variable "service_account_email" {
  type        = string
  description = "SA the job runs as."
}

variable "invoker_service_account_email" {
  type        = string
  description = "SA that triggers the job (Cloud Scheduler)."
}

variable "env_vars" {
  type        = map(string)
  default     = {}
  description = "Environment variables passed to the job container."
}

resource "google_cloud_run_v2_job" "sweep" {
  name     = var.job_name
  location = var.region
  project  = var.project_id

  template {
    template {
      service_account = var.service_account_email
      containers {
        image   = var.image
        command = ["career-engine", "sweep"]
        dynamic "env" {
          for_each = var.env_vars
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }
}

# Scheduler SA needs roles/run.invoker on the Job to execute it.
resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.sweep.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.invoker_service_account_email}"
}

output "job_name" {
  description = "The Cloud Run Job name."
  value       = google_cloud_run_v2_job.sweep.name
}

output "job_execute_uri" {
  description = "Cloud Run Jobs Execute API URI for this job."
  value       = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.sweep.name}:run"
}
