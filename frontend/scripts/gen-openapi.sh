#!/usr/bin/env bash
#
# Generate the frontend's TypeScript types from the live FastAPI OpenAPI schema.
#
# Two steps, both committed so typecheck/tests never need Python:
#   1. Dump the live schema from the Python app -> frontend/openapi.json
#   2. Run openapi-typescript over it -> src/lib/api/types.gen.ts
#
# Run from anywhere: `bash scripts/gen-openapi.sh` (also wired as `npm run gen:openapi`).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "==> Dumping OpenAPI schema from api.main:app"
(
  cd "$REPO_ROOT" &&
    python -c "import json; from api.main import app; print(json.dumps(app.openapi()))" \
      >"$REPO_ROOT/frontend/openapi.json"
)

echo "==> Generating TypeScript types -> src/lib/api/types.gen.ts"
(
  cd "$REPO_ROOT/frontend" &&
    npx openapi-typescript openapi.json -o src/lib/api/types.gen.ts
)

echo "==> Done. Commit frontend/openapi.json and frontend/src/lib/api/types.gen.ts"
