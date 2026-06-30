# CareerEngine — prod environment variables. No secrets here.

variable "project_id" {
  type        = string
  description = "GCP project ID for the prod environment."
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
  default     = "career-engine-prod"
}

variable "image" {
  type        = string
  description = "Container image to deploy (Artifact Registry path:tag)."
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "contract_version" {
  type        = string
  description = "CONTRACT_VERSION stamped into the runtime — MUST track config.py:CONTRACT_VERSION."
  default     = "2.2.0"
}

variable "sweep_schedule" {
  type        = string
  description = "Cron schedule for the pending-action sweep."
  default     = "0 3 * * *"
}
