# CareerEngine — Cloud Scheduler trigger for the 14-day pending-action sweep.
#
# Invokes the Cloud Run sweep endpoint on a cron schedule using an OIDC token
# minted for the given invoker service account (ARCHITECTURE §8).

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
  description = "Region for the Cloud Scheduler job."
}

variable "job_name" {
  type        = string
  description = "Cloud Scheduler job name."
}

variable "schedule" {
  type        = string
  description = "Cron schedule for the sweep (default: daily at 03:00)."
  default     = "0 3 * * *"
}

variable "time_zone" {
  type        = string
  description = "IANA time zone for the schedule."
  default     = "Etc/UTC"
}

variable "target_uri" {
  type        = string
  description = "Cloud Run sweep endpoint to invoke (e.g. <service_uri>/jobs/pending-action-sweep)."
}

variable "invoker_service_account_email" {
  type        = string
  description = "Service account whose OIDC token authenticates the invocation."
}

resource "google_cloud_scheduler_job" "pending_action_sweep" {
  project   = var.project_id
  region    = var.region
  name      = var.job_name
  schedule  = var.schedule
  time_zone = var.time_zone

  http_target {
    http_method = "POST"
    uri         = var.target_uri

    oidc_token {
      service_account_email = var.invoker_service_account_email
      audience              = var.target_uri
    }
  }
}

output "job_name" {
  description = "The Cloud Scheduler job name."
  value       = google_cloud_scheduler_job.pending_action_sweep.name
}
