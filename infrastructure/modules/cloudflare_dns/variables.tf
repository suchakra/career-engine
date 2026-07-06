variable "zone_id" {
  type        = string
  description = "Cloudflare zone ID for the bitcrafty.cloud domain (from Cloudflare Dashboard → Overview)."
}

variable "subdomain" {
  type        = string
  description = "DNS name for the app record within the zone (e.g. career-engine for career-engine.bitcrafty.cloud)."
  default     = "career-engine"
}

variable "google_verification_txt" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Google domain ownership verification TXT value (google-site-verification=...). One-time bootstrap only; obtain from Google Search Console or Cloud Run domain mapping console. Set to empty string to skip creating the TXT record (after verification is complete and the record can be removed)."
}

variable "resource_records" {
  type = list(object({
    type   = string
    rrdata = string
  }))
  description = "A/AAAA DNS records returned by the Cloud Run domain mapping (cloud_run_domain_mapping module output). Empty until GCP provisions the mapping."
}
