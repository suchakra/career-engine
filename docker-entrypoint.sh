#!/bin/sh
# CareerEngine container entrypoint.
#
# Streamlit native OIDC auth (st.login) reads its config from
# .streamlit/secrets.toml. On Cloud Run we don't bake that file into the image;
# instead we materialize it at startup from env vars (client_secret + cookie_secret
# sourced from Secret Manager via the Cloud Run service config). If no auth env is
# provided, the file is left as-is (local dev uses a checked-out secrets.toml).
set -e

if [ -n "${CE_AUTH_CLIENT_ID:-}" ]; then
  mkdir -p .streamlit
  # Write via Python so every value is safely escaped (json.dumps emits a valid
  # TOML basic string) — a secret containing a quote/backslash/newline cannot
  # corrupt the file or inject config.
  python3 - <<'PY'
import json, os

def s(name, default=""):
    return json.dumps(os.environ.get(name) or default)

meta = "https://accounts.google.com/.well-known/openid-configuration"
lines = [
    "[auth]",
    f"redirect_uri = {s('CE_AUTH_REDIRECT_URI')}",
    f"cookie_secret = {s('CE_AUTH_COOKIE_SECRET')}",
    f"client_id = {s('CE_AUTH_CLIENT_ID')}",
    f"client_secret = {s('CE_AUTH_CLIENT_SECRET')}",
    f"server_metadata_url = {s('CE_AUTH_METADATA_URL', meta)}",
]
with open(".streamlit/secrets.toml", "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
PY
fi

exec "$@"
