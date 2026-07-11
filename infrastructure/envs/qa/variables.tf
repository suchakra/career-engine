variable "project_id" {
  type        = string
  description = "GCP project ID — the SAME project as dev (qa is a second Cloud Run service in it)."
}

variable "region" {
  type        = string
  description = "Primary region (Cloud Run, Artifact Registry)."
  default     = "us-central1"
}

variable "name_prefix" {
  type        = string
  description = "Prefix applied to qa resource names (service, SA, image repo)."
  default     = "career-engine-qa"
}

variable "image" {
  type        = string
  description = "Container image to deploy (Artifact Registry path:tag)."
}

variable "contract_version" {
  type        = string
  description = "CONTRACT_VERSION stamped into the runtime — track config.py:CONTRACT_VERSION."
  default     = "2.8.0"
}

variable "firebase_project_id" {
  type        = string
  description = "Firebase project id (token audience). Empty → defaults to project_id (Firebase on the same project)."
  default     = ""
}
