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

variable "custom_domain" {
  type        = string
  description = "Custom domain for the web app (e.g. career-engine.bitcrafty.cloud)."
  default     = "career-engine.bitcrafty.cloud"
}

variable "auth_redirect_uri" {
  type        = string
  description = "OAuth2 redirect URI sent to Google and handled by the app. Defaults to the custom domain /_stcore/oauth2callback (correct for current code). Override to the *.run.app URL when the custom domain TLS cert is not yet ready, or when running an older image that uses /oauth2callback instead of /_stcore/oauth2callback."
  default     = ""
}

variable "cloudflare_zone_id" {
  type        = string
  description = "Cloudflare zone ID for the bitcrafty.cloud domain (from Cloudflare Dashboard → Overview). Set via TF_VAR_cloudflare_zone_id."
}

variable "cloudflare_api_token" {
  type        = string
  sensitive   = true
  description = "Cloudflare API token scoped to bitcrafty.cloud DNS Edit. Set via TF_VAR_cloudflare_api_token — never commit or store in state."
}

variable "google_domain_verification_txt" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Google domain ownership verification TXT value (google-site-verification=...). One-time bootstrap only — apply module.cloudflare_dns.cloudflare_dns_record.verification first, complete verification, then run full apply. Set via TF_VAR_google_domain_verification_txt. Leave empty (the default) for steady-state applies after verification is complete."
}

variable "dns_resource_records" {
  type = list(object({
    type   = string
    rrdata = string
  }))
  default     = []
  description = "A/AAAA records from the Cloud Run domain mapping — paste from `terraform output domain_mapping_resource_records` after Phase 1 apply. Empty on first apply (Terraform can't derive for_each keys from apply-time values). See README §Custom domain Phase 2."
}
