# CareerEngine — Artifact Registry (Docker) for container images.

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
  description = "Region for the Artifact Registry repository."
}

variable "repository_id" {
  type        = string
  description = "Repository ID for container images."
}

resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_id
  format        = "DOCKER"
  description   = "CareerEngine container images"
}

output "repository_id" {
  description = "Artifact Registry repository ID."
  value       = google_artifact_registry_repository.images.repository_id
}

output "repository_url" {
  description = "Docker repository URL prefix for pushing images."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}
