#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

COMPOSE_FILE="${COMPOSE_FILE:-local.yml}"
DJANGO_ENV_DIR="${ROOT}/.envs/.local"
POSTGRES_ENV="${DJANGO_ENV_DIR}/.postgres"
DJANGO_ENV="${DJANGO_ENV_DIR}/.django"
HOST_POSTGRES_PORT="${HOST_POSTGRES_PORT:-5439}"
HOST_REDIS_PORT="${HOST_REDIS_PORT:-6399}"
RUNSERVER_HOST="${RUNSERVER_HOST:-0.0.0.0}"
RUNSERVER_PORT="${RUNSERVER_PORT:-8000}"
LLAMA_HOST="${LLAMA_HOST:-127.0.0.1:11434}"

if [ ! -f "$POSTGRES_ENV" ] || [ ! -f "$DJANGO_ENV" ]; then
  echo "Missing ${DJANGO_ENV_DIR}/.django or .postgres." >&2
  echo "Copy from .envs.example: cp -r .envs.example/.local .envs/.local" >&2
  exit 1
fi

pick_python() {
  if [ -x "${ROOT}/.venv/bin/python" ]; then
    echo "${ROOT}/.venv/bin/python"
    return
  fi
  if command -v python3.14 >/dev/null 2>&1; then
    command -v python3.14
    return
  fi
  command -v python3
}

PYTHON="$(pick_python)"
if ! "$PYTHON" -c "import django" 2>/dev/null; then
  echo "Django not found for ${PYTHON}." >&2
  echo "Create a venv and install deps: python3.14 -m venv .venv && .venv/bin/pip install -r requirements/local.txt" >&2
  exit 1
fi

docker compose -f "$COMPOSE_FILE" stop django 2>/dev/null || true
docker compose -f "$COMPOSE_FILE" up -d postgres redis mailhog celeryworker celerybeat

set -a
# shellcheck disable=SC1090
source "$POSTGRES_ENV"
# shellcheck disable=SC1090
source "$DJANGO_ENV"
set +a

export USE_DOCKER=no
export DJANGO_SETTINGS_MODULE=config.settings.local
export IPYTHONDIR="${IPYTHONDIR:-${ROOT}/.ipython}"
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT="${HOST_POSTGRES_PORT}"
export REDIS_URL="redis://127.0.0.1:${HOST_REDIS_PORT}/0"
export CELERY_BROKER_URL="${REDIS_URL}"
export DATABASE_URL="postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
export EMAIL_HOST=127.0.0.1
export REFERENCE_URL="http://${LLAMA_HOST}"
export FRONT_URL="http://${LLAMA_HOST}"
export BODY_URL="http://${LLAMA_HOST}"

PACKTOOLS_DIR="$(cd "${ROOT}/.." && pwd)/packtools"
if [ -f "${PACKTOOLS_DIR}/pyproject.toml" ] || [ -f "${PACKTOOLS_DIR}/setup.py" ]; then
  "$PYTHON" -m pip install -e "${PACKTOOLS_DIR}" --quiet --no-build-isolation
fi

postgres_ready() {
  "$PYTHON" <<END
import sys
import psycopg2

try:
    psycopg2.connect(
        dbname="${POSTGRES_DB}",
        user="${POSTGRES_USER}",
        password="${POSTGRES_PASSWORD}",
        host="${POSTGRES_HOST}",
        port=${POSTGRES_PORT},
    )
except psycopg2.OperationalError:
    sys.exit(-1)
sys.exit(0)
END
}

until postgres_ready; do
  echo "Waiting for PostgreSQL on ${POSTGRES_HOST}:${POSTGRES_PORT}..." >&2
  sleep 1
done
echo "PostgreSQL is available" >&2

"$PYTHON" manage.py migrate
exec "$PYTHON" manage.py runserver_plus "${RUNSERVER_HOST}:${RUNSERVER_PORT}"
