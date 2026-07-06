# CareerEngine — Cloud Scheduler trigger for the 14-day pending-action sweep.
#
# Invokes the target URI on a cron schedule using a service-account-minted token
# (OIDC for Cloud Run services; OAuth2 access token for Google REST APIs such as
# the Cloud Run Jobs Execute endpoint). Controlled by var.token_type.

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
  description = "Cloud Run sweep endpoint to POST (e.g. <service_uri>/jobs/pending-action-sweep)."
}

variable "service_uri" {
  type        = string
  description = "BASE Cloud Run service URL — used as the OIDC token audience (Cloud Run validates aud against the base URL, NOT the request path)."
}

variable "cloud_run_service_name" {
  type        = string
  description = "Name of the Cloud Run service to invoke (for the run.invoker binding)."
}

variable "invoker_service_account_email" {
  type        = string
  description = "Service account whose OIDC token / OAuth2 access token authenticates the invocation."
}

variable "token_type" {
  type        = string
  description = "Auth token type: 'oidc' (Cloud Run service) or 'oauth2' (Google REST API e.g. Cloud Run Jobs)."
  default     = "oidc"
  validation {
    condition     = contains(["oidc", "oauth2"], var.token_type)
    error_message = "token_type must be 'oidc' or 'oauth2'."
  }
}

# Without roles/run.invoker the OIDC token is rejected (HTTP 403) and the sweep
# never fires. Grant the invoker SA permission to invoke exactly this service.
# When token_type = "oauth2" (Cloud Run Jobs path) the IAM binding is managed by
# the cloud_run_job module instead, but we keep this for the oidc path.
resource "google_cloud_run_v2_service_iam_member" "scheduler_invoker" {
  count    = var.token_type == "oidc" ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = var.cloud_run_service_name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.invoker_service_account_email}"
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

    # Cloud Run services require an OIDC JWT (audience = service base URL).
    # Google REST APIs (e.g. Cloud Run Jobs Execute) require an OAuth2 access token.
    dynamic "oidc_token" {
      for_each = var.token_type == "oidc" ? [1] : []
      content {
        service_account_email = var.invoker_service_account_email
        # Audience is the BASE service URL, not the request path, or Cloud Run
        # rejects the token (401).
        audience = var.service_uri
      }
    }

    dynamic "oauth_token" {
      for_each = var.token_type == "oauth2" ? [1] : []
      content {
        service_account_email = var.invoker_service_account_email
        scope                 = "https://www.googleapis.com/auth/cloud-platform"
      }
    }
  }

  # Ensure the invoker binding exists before the job that relies on it (oidc path).
  depends_on = [google_cloud_run_v2_service_iam_member.scheduler_invoker]
}

output "job_name" {
  description = "The Cloud Scheduler job name."
  value       = google_cloud_scheduler_job.pending_action_sweep.name
}
