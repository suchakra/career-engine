# CareerEngine — Secret Manager enablement + least-privilege runtime access.
#
# Per-user BYOK keys (id: ce-key-{user_id}) are created at RUNTIME by the app
# (auth/key_vault.py), NOT by Terraform — so no secret material lives in this
# config or in state. This module only:
#   1. ensures the Secret Manager API is enabled, and
#   2. grants the Cloud Run runtime SA roles/secretmanager.secretAccessor
#      CONDITIONED to per-user BYOK key secrets (ce-key-*) ONLY, so a compromised
#      instance can read users' keys but NOT the OAuth client / cookie secrets or
#      any other secret in the project (least privilege; ARCHITECTURE §5,
#      SECURITY.md 2026-07-05 review). The OIDC auth secrets are granted per-secret
#      in the env root (dev) where they are defined.

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

variable "project_number" {
  type        = string
  description = "GCP project NUMBER — used in the IAM condition that scopes reads to ce-key-* secrets."
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

  # Least privilege: the runtime SA may READ only per-user BYOK key secrets
  # (ce-key-*), never the OAuth client / cookie secrets or any other project
  # secret. Mirrors the ce-key-* write condition in the env root.
  condition {
    title       = "ce-key-secrets-read-only"
    description = "Runtime SA reads only per-user BYOK key secrets (ce-key-*)."
    expression  = "resource.name.startsWith(\"projects/${var.project_number}/secrets/ce-key-\")"
  }
}

output "secret_accessor_member" {
  description = "The IAM member granted secretAccessor (for verification)."
  value       = google_project_iam_member.runtime_secret_accessor.member
}
