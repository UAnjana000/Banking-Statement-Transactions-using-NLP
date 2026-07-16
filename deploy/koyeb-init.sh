#!/usr/bin/env sh
# Create (or recreate) the FinUnderWrite web service on Koyeb from this repo's Dockerfile.
# Prerequisites: koyeb CLI logged in (`koyeb login`), GitHub connected in the Koyeb control panel.
#
# Usage:
#   export FINUNDERWRITE_DATABASE_URL='postgresql+psycopg://user:pass@host/db'
#   sh deploy/koyeb-init.sh
#
# Or set REPO / APP_NAME overrides:
#   REPO=github.com/you/your-fork APP_NAME=finunderwrite sh deploy/koyeb-init.sh

set -eu

REPO="${REPO:-github.com/UAnjana000/Banking-Statement-Transactions-using-NLP}"
APP_NAME="${APP_NAME:-finunderwrite}"
BRANCH="${BRANCH:-main}"

if [ -z "${FINUNDERWRITE_DATABASE_URL:-}" ]; then
  echo "Set FINUNDERWRITE_DATABASE_URL to an external Postgres URL (Neon/Supabase) before deploying." >&2
  exit 1
fi

koyeb app init "${APP_NAME}" \
  --git "${REPO}" \
  --git-branch "${BRANCH}" \
  --git-builder docker \
  --git-docker-dockerfile Dockerfile \
  --instance-type free \
  --ports "8000:http" \
  --routes "/:8000" \
  --checks "8000:http:/health" \
  --env "PORT=8000" \
  --env "WEB_CONCURRENCY=2" \
  --env "PYTHONPATH=/app/src" \
  --env "FINUNDERWRITE_LOG_LEVEL=INFO" \
  --env "FINUNDERWRITE_LLM_ENRICH_ENABLED=false" \
  --env "FINUNDERWRITE_ENRICHER=null" \
  --env "FINUNDERWRITE_DATABASE_URL=${FINUNDERWRITE_DATABASE_URL}"

echo "Deploy started. Watch status with: koyeb service get ${APP_NAME}/${APP_NAME}"
