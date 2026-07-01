#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.agent.yml"
PROJECT_NAME="${EMSA_AGENT_PROJECT:-emsarena-agent}"

usage() {
    cat <<'USAGE'
Usage: scripts/claude_pg_sandbox.sh <command> [args...]

Commands:
  up               Build/start PostgreSQL and Redis for the agent sandbox.
  shell            Open an interactive shell with DATABASE_URL already set.
  check            Run python manage.py check inside the agent container.
  migrate          Run Django migrations against the sandbox PostgreSQL DB.
  test [args...]   Run pytest against sandbox PostgreSQL.
                   Defaults to: pytest --ds=config.settings.test --ignore=tests/e2e
  postgres-tests   Run the PostgreSQL/RLS test subset.
  psql [args...]   Open psql against the sandbox PostgreSQL DB.
  down             Stop the sandbox containers.
  clean            Stop containers and remove sandbox volumes.

Environment overrides:
  AGENT_POSTGRES_PORT=55432
  AGENT_REDIS_PORT=56379
  AGENT_POSTGRES_DB=emsarena_agent
  AGENT_POSTGRES_USER=emsarena_agent
  AGENT_POSTGRES_PASSWORD=emsarena_agent_password
USAGE
}

compose() {
    docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" "$@"
}

ensure_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "Docker is required for the Claude PostgreSQL sandbox." >&2
        exit 1
    fi
    if ! docker compose version >/dev/null 2>&1; then
        echo "Docker Compose v2 is required. Install the Docker Compose plugin." >&2
        exit 1
    fi
}

ensure_services() {
    compose up -d postgres redis
}

run_agent() {
    ensure_services
    compose run --rm --build agent "$@"
}

command="${1:-shell}"
if [ "$#" -gt 0 ]; then
    shift
fi

ensure_docker
cd "$ROOT_DIR"

case "$command" in
    up)
        compose up -d --build postgres redis
        ;;
    shell)
        run_agent bash "$@"
        ;;
    check)
        run_agent python manage.py check "$@"
        ;;
    migrate)
        run_agent python manage.py migrate "$@"
        ;;
    test)
        if [ "$#" -eq 0 ]; then
            set -- --ignore=tests/e2e
        fi
        run_agent pytest --ds=config.settings.test "$@"
        ;;
    postgres-tests)
        run_agent pytest --ds=config.settings.test -m postgres \
            apps/organizations/tests/test_rls.py \
            apps/organizations/tests/test_rls_transaction_pooling.py \
            "$@"
        ;;
    psql)
        ensure_services
        compose exec postgres psql \
            -U "${AGENT_POSTGRES_USER:-emsarena_agent}" \
            -d "${AGENT_POSTGRES_DB:-emsarena_agent}" \
            "$@"
        ;;
    down)
        compose down
        ;;
    clean)
        compose down -v
        ;;
    help|-h|--help)
        usage
        ;;
    *)
        echo "Unknown command: $command" >&2
        usage >&2
        exit 2
        ;;
esac
