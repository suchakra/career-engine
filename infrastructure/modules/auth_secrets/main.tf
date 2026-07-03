# CareerEngine — web OIDC auth secret RESOURCES.
#
# Streamlit native login (st.login) needs an OAuth client secret + a session
# cookie secret. Terraform manages the secret *containers* here; the secret
# VALUES are set out-of-band (gcloud / Console), NEVER in Terraform state —
# exactly like per-user BYOK keys (privacy-first, ARCHITECTURE §5).
#
# The Google OAuth *client* itself is created in the Console (Google exposes no
# Terraform resource for generic OAuth2 web clients) — a documented manual step.

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

variable "client_secret_id" {
  type        = string
  description = "Secret id for the OAuth client secret."
  default     = "ce-auth-client-secret"
}

variable "cookie_secret_id" {
  type        = string
  description = "Secret id for the Streamlit session cookie secret."
  default     = "ce-auth-cookie-secret"
}

resource "google_secret_manager_secret" "client_secret" {
  project   = var.project_id
  secret_id = var.client_secret_id
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "cookie_secret" {
  project   = var.project_id
  secret_id = var.cookie_secret_id
  replication {
    auto {}
  }
}

output "client_secret_id" {
  description = "Secret id for the OAuth client secret (set its VALUE out-of-band)."
  value       = google_secret_manager_secret.client_secret.secret_id
}

output "cookie_secret_id" {
  description = "Secret id for the session cookie secret (set its VALUE out-of-band)."
  value       = google_secret_manager_secret.cookie_secret.secret_id
}
