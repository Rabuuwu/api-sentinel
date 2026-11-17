#!/usr/bin/env bash
# Isolated account verification. Never connects to Neon or the application database.
set -euo pipefail
cd "$(dirname "$0")/.."
repo_dir="$PWD"
pg_data="$repo_dir/.local/accounts-test-postgres"
pg_started=0
api_pid=''
cleanup() {
  if [[ -n "$api_pid" ]]; then kill "$api_pid" 2>/dev/null || true; fi
  if [[ "$pg_started" == 1 ]]; then pg_ctl -D "$pg_data" -m fast stop; fi
}
trap cleanup EXIT
for tool in initdb pg_ctl createdb psql curl npm; do
  command -v "$tool" >/dev/null || { echo "Missing required tool: $tool"; exit 1; }
done
[[ -x .venv/bin/python ]] || { echo 'Install Python dependencies in .venv first'; exit 1; }
mkdir -p .local
if ! pg_ctl -D "$pg_data" status >/dev/null 2>&1; then
  if pg_isready -h 127.0.0.1 -p 54339 >/dev/null 2>&1; then
    echo 'Port 54339 belongs to another PostgreSQL instance; refusing to use it.'; exit 1
  fi
  if [[ ! -f "$pg_data/PG_VERSION" ]]; then
    initdb -D "$pg_data" -A trust -U sentinel_test -E UTF8 --no-locale
  fi
  pg_ctl -D "$pg_data" -l .local/accounts-test-postgres.log -o '-h 127.0.0.1 -p 54339' start
  pg_started=1
fi
if ! psql -h 127.0.0.1 -p 54339 -U sentinel_test -d postgres -Atc \
  "SELECT 1 FROM pg_database WHERE datname = 'sentinel_test'" | grep -q '^1$'; then
  createdb -h 127.0.0.1 -p 54339 -U sentinel_test sentinel_test
fi
export DATABASE_URL='postgresql+asyncpg://sentinel_test@127.0.0.1:54339/sentinel_test'
export DATABASE_URL_UNPOOLED="$DATABASE_URL"
export SENTINEL_TEST_DATABASE_URL="$DATABASE_URL"
export SENTINEL_API_KEY='isolated-account-test-key-not-for-production'
export GMAIL_CLIENT_ID=''
export GMAIL_CLIENT_SECRET=''
export GMAIL_REFRESH_TOKEN=''
export RENDER=false
export ALLOWED_HOSTS='localhost,127.0.0.1,[::1]'
export WEBHOOK_ENCRYPTION_KEY=''
export DISCORD_WEBHOOK_URL=''
export SECRETS_DIR="$repo_dir/.local/accounts-test-secrets"
export FRONTEND_DIR="$repo_dir/frontend/dist"
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m alembic check
.venv/bin/python tests/integration/cleanup_e2e.py
.venv/bin/python -m pytest -q
npm test --prefix frontend
npm run build
export SENTINEL_E2E_ISOLATED=1
export SENTINEL_E2E_URL='http://127.0.0.1:54349'
export SENTINEL_E2E_KEY="$SENTINEL_API_KEY"
.venv/bin/python -m uvicorn api_sentinel.app:create_app --factory --host 127.0.0.1 \
  --port 54349 --no-access-log > .local/accounts-test-api.log 2>&1 &
api_pid=$!
ready=0
for attempt in {1..30}; do
  kill -0 "$api_pid" 2>/dev/null || { echo 'API startup failed; see .local/accounts-test-api.log'; exit 1; }
  if curl -fsS "$SENTINEL_E2E_URL/health/ready" >/dev/null; then ready=1; break; fi
  sleep 1
done
[[ "$ready" == 1 ]] || { echo 'Test API did not become ready'; exit 1; }
npm run test:e2e --prefix frontend
.venv/bin/python tests/integration/cleanup_e2e.py
