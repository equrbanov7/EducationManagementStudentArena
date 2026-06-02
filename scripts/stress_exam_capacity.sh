#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1}"
HOST_HEADER="${HOST_HEADER:-localhost}"
STAGES="${STAGES:-200,300,500}"
PATHS="${PATHS:-/ping/,/health/}"
REQUESTS_PER_USER="${REQUESTS_PER_USER:-1}"
FORWARDED_PROTO="${FORWARDED_PROTO:-https}"
CONNECT_TIMEOUT_SECONDS="${CONNECT_TIMEOUT_SECONDS:-5}"
MAX_TIME_SECONDS="${MAX_TIME_SECONDS:-30}"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required." >&2
  exit 1
fi

run_stage() {
  local concurrency="$1"
  local path="$2"
  local total_requests=$((concurrency * REQUESTS_PER_USER))
  local url="${BASE_URL%/}${path}"
  local start
  local end
  local elapsed
  local tmp

  tmp="$(mktemp)"
  start="$(date +%s)"

  seq 1 "$total_requests" | xargs -P "$concurrency" -I{} sh -c '
    curl -sS \
      --connect-timeout "$1" \
      --max-time "$2" \
      -H "Host: $3" \
      -H "X-Forwarded-Proto: $4" \
      -o /dev/null \
      -w "%{http_code}\n" \
      "$5"
  ' sh "$CONNECT_TIMEOUT_SECONDS" "$MAX_TIME_SECONDS" "$HOST_HEADER" "$FORWARDED_PROTO" "$url" >"$tmp"

  end="$(date +%s)"
  elapsed=$((end - start))
  if [ "$elapsed" -lt 1 ]; then
    elapsed=1
  fi

  echo
  echo "stage=${concurrency} path=${path} total=${total_requests} elapsed=${elapsed}s rps=$((total_requests / elapsed))"
  sort "$tmp" | uniq -c
  rm -f "$tmp"
}

IFS=',' read -r -a stage_list <<<"$STAGES"
IFS=',' read -r -a path_list <<<"$PATHS"

for stage in "${stage_list[@]}"; do
  stage="$(echo "$stage" | tr -d '[:space:]')"
  if ! [[ "$stage" =~ ^[0-9]+$ ]] || [ "$stage" -lt 1 ]; then
    echo "Invalid stage: ${stage}" >&2
    exit 1
  fi

  for path in "${path_list[@]}"; do
    path="$(echo "$path" | tr -d '[:space:]')"
    [ -n "$path" ] || continue
    run_stage "$stage" "$path"
  done
done
