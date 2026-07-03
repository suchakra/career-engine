# CareerEngine — dev environment variables. No secrets here; provide values
# via terraform.tfvars (gitignored) or TF_VAR_* env vars.

variable "project_id" {
  type        = string
  description = "GCP project ID for the dev environment."
}

variable "region" {
  type        = string
  description = "Primary region (Cloud Run, Artifact Registry, Scheduler)."
  default     = "us-central1"
}

variable "firestore_location" {
  type        = string
  description = "Firestore location (multi-region like nam5, or a region)."
  default     = "nam5"
}

variable "name_prefix" {
  type        = string
  description = "Prefix applied to all resource names for this environment."
  default     = "career-engine-dev"
}

variable "image" {
  type        = string
  description = "Container image to deploy (Artifact Registry path:tag)."
  # Placeholder until the first image is pushed; override in tfvars.
  default = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "contract_version" {
  type        = string
  description = "CONTRACT_VERSION stamped into the runtime — MUST track config.py:CONTRACT_VERSION."
  default     = "2.4.0"
}

variable "sweep_schedule" {
  type        = string
  description = "Cron schedule for the pending-action sweep."
  default     = "0 3 * * *"
}

variable "auth_client_id" {
  type        = string
  description = "Google OAuth 2.0 Web client ID for Streamlit login (created in the Console)."
  default     = ""
}

variable "auth_redirect_uri" {
  type        = string
  description = "OIDC redirect URI (public app URL + /oauth2callback), e.g. https://<domain>/oauth2callback."
  default     = ""
}
