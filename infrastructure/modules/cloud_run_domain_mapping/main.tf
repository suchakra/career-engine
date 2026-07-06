# CareerEngine — Cloud Run domain mapping.
#
# Creates a google_cloud_run_domain_mapping resource that instructs GCP to
# serve the named Cloud Run service at the given custom domain and provision
# a managed TLS certificate.  After apply, the `resource_records` output
# contains the A/AAAA records that must be added to DNS before SSL
# provisioning can complete.

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0, < 7.0"
    }
  }
}

resource "google_cloud_run_domain_mapping" "custom" {
  project  = var.project_id
  location = var.region
  name     = var.domain

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = var.service_name
  }

  lifecycle {
    ignore_changes = [metadata[0].annotations]
  }
}

output "resource_records" {
  description = "DNS records to add to Cloudflare (populated after GCP provisions the mapping)."
  value       = google_cloud_run_domain_mapping.custom.status[0].resource_records
}
