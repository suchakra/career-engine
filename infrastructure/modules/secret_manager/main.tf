# CareerEngine — Secret Manager enablement + least-privilege runtime access.
#
# Per-user BYOK keys (id: ce-key-{user_id}) are created at RUNTIME by the app
# (auth/key_vault.py), NOT by Terraform — so no secret material lives in this
# config or in state. This module only:
#   1. ensures the Secret Manager API is enabled, and
#   2. grants the Cloud Run runtime SA exactly roles/secretmanager.secretAccessor
#      at the project level so it can read those per-user keys and nothing more
#      (least privilege; see ARCHITECTURE §5).

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

variable "service_account_email" {
  type        = string
  description = "Runtime service account granted secretAccessor (from cloud_run module)."
}

resource "google_project_service" "secretmanager" {
  project            = var.project_id
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_iam_member" "runtime_secret_accessor" {
  project    = var.project_id
  role       = "roles/secretmanager.secretAccessor"
  member     = "serviceAccount:${var.service_account_email}"
  depends_on = [google_project_service.secretmanager]
}

output "secret_accessor_member" {
  description = "The IAM member granted secretAccessor (for verification)."
  value       = google_project_iam_member.runtime_secret_accessor.member
}
