variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  description = "Region where the Cloud Run service is deployed."
}

variable "domain" {
  type        = string
  description = "Custom domain to map (e.g. career-engine.bitcrafty.cloud)."
}

variable "service_name" {
  type        = string
  description = "Cloud Run service name (not the URL) to route traffic for the domain."
}
