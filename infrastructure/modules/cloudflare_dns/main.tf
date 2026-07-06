# CareerEngine — Cloudflare DNS records for custom domain.
#
# Manages two sets of records:
#   1. A TXT record for Google domain ownership verification (apply first,
#      complete verification, then apply the rest — see README §Custom domain).
#   2. A/AAAA records from the Cloud Run domain mapping (populated by the
#      cloud_run_domain_mapping module output after GCP provisions the mapping).
#
# All records use proxied = false (grey cloud / DNS-only) so that GCP can
# validate DNS and provision the managed TLS certificate.  Cloudflare proxy
# can be enabled after SSL is confirmed, but DNS-only is the recommended
# steady state (avoids WebSocket quirks with Streamlit).

terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = ">= 5.0, < 6.0"
    }
  }
}

# Step 1: TXT record for Google domain ownership verification.
# Value comes from Google Webmaster Central / Cloud Console domain verification.
# Apply this first (targeted apply), complete verification in Google Console,
# then run the full apply to create the A/AAAA records.
# Set google_verification_txt to "" (the default) after verification is complete
# to remove this record from management — it is not needed for steady-state operation.
resource "cloudflare_dns_record" "verification" {
  count   = var.google_verification_txt != "" ? 1 : 0
  zone_id = var.zone_id
  name    = var.subdomain
  type    = "TXT"
  content = var.google_verification_txt
  ttl     = 300
  proxied = false
  comment = "Google domain ownership verification for Cloud Run domain mapping"
}

# Step 2: A/AAAA records from Cloud Run domain mapping.
# resource_records is a list of { type, rrdata } objects returned by the
# cloud_run_domain_mapping module after GCP provisions the mapping.
resource "cloudflare_dns_record" "cloud_run" {
  for_each = { for r in var.resource_records : "${r.type}:${r.rrdata}" => r }

  zone_id = var.zone_id
  name    = var.subdomain
  type    = each.value.type
  content = each.value.rrdata
  ttl     = 300
  proxied = false
  comment = "Cloud Run custom domain mapping — managed by Terraform"

  depends_on = [cloudflare_dns_record.verification]
}
