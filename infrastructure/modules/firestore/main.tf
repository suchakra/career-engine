# CareerEngine — Firestore (Native) database.
#
# Stores agent state + resume metadata, isolated by user_id (see ARCHITECTURE
# §5). No secret/API key is ever written to Firestore (enforced in app code).

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

variable "location" {
  type        = string
  description = "Firestore location (e.g. nam5, eur3, or a region)."
}

variable "database_id" {
  type        = string
  description = "Firestore database id ('(default)' for the default database)."
  default     = "(default)"
}

variable "deletion_policy" {
  type        = string
  description = "DELETE allows teardown in dev; ABANDON protects prod data."
  default     = "ABANDON"
}

resource "google_firestore_database" "default" {
  project         = var.project_id
  name            = var.database_id
  location_id     = var.location
  type            = "FIRESTORE_NATIVE"
  deletion_policy = var.deletion_policy
}

output "database_name" {
  description = "The Firestore database name."
  value       = google_firestore_database.default.name
}
