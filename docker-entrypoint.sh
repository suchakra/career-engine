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
  cat > .streamlit/secrets.toml <<EOF
[auth]
redirect_uri = "${CE_AUTH_REDIRECT_URI}"
cookie_secret = "${CE_AUTH_COOKIE_SECRET}"
client_id = "${CE_AUTH_CLIENT_ID}"
client_secret = "${CE_AUTH_CLIENT_SECRET}"
server_metadata_url = "${CE_AUTH_METADATA_URL:-https://accounts.google.com/.well-known/openid-configuration}"
EOF
fi

exec "$@"
