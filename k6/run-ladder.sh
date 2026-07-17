#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# EMSArena k6 STRESS LADDER runner
# Runs one env-driven scenario at escalating VU levels, exporting a per-stage
# JSON summary + a consolidated markdown report, and capturing server load
# (via ssh wcuserver) after each stage so we can see the box degrade.
#
# Usage:
#   k6/run-ladder.sh <scenario.js> <VU_ENV_VAR> <label> [vus_csv] [duration]
# Example:
#   k6/run-ladder.sh k6/login-load-test.js LOGIN_VUS login-stampede
#
# Env overrides: BASE_URL, K6_USERS_FILE, SSH_HOST, K6_INSECURE_SKIP_TLS_VERIFY
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail
cd "$(dirname "$0")/.."   # repo root

SCENARIO="${1:?scenario js path (e.g. k6/login-load-test.js)}"
VU_ENV="${2:?VU env var name (e.g. LOGIN_VUS)}"
LABEL="${3:?report label (e.g. login-stampede)}"
VUS_CSV="${4:-50,100,200,300,400,500,750,1000}"
DURATION="${5:-60s}"

export BASE_URL="${BASE_URL:-https://10.0.2.42}"
export K6_INSECURE_SKIP_TLS_VERIFY="${K6_INSECURE_SKIP_TLS_VERIFY:-true}"
export K6_USERS_FILE="${K6_USERS_FILE:-$(pwd)/k6/data/stress-users.json}"
SSH_HOST="${SSH_HOST:-wcuserver}"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="k6/reports/${LABEL}_${STAMP}"
mkdir -p "$OUT"
MD="$OUT/REPORT.md"

srv_load() {
  ssh -o BatchMode=yes -o ConnectTimeout=6 "$SSH_HOST" \
    'read a b c rest < /proc/loadavg; mem=$(free -m | awk "/Mem:/{printf \"%d/%dMB\", \$3, \$2}"); echo "$a $b $c | $mem"' \
    2>/dev/null || echo "n/a"
}

{
  echo "# k6 stress ladder — ${LABEL}"
  echo
  echo "- **Scenario:** \`${SCENARIO}\`"
  echo "- **Target:** \`${BASE_URL}\` (wcuserver — 80 cores / 62 GiB)"
  echo "- **Ladder:** ${VUS_CSV} VUs, ${DURATION} hold each"
  echo "- **Started:** ${STAMP}"
  echo "- **Baseline server load (pre-test):** \`$(srv_load)\`"
  echo
  echo "| VUs | iters | RPS | reqs | fail % | p95 ms | p99 ms | max ms | checks % | srv load(1m) | thresholds |"
  echo "|----:|------:|----:|-----:|-------:|-------:|-------:|-------:|---------:|:-------------|:-----------|"
} > "$MD"

echo "=== Ladder ${LABEL} -> ${BASE_URL} | stages: ${VUS_CSV} | ${DURATION}/stage ==="

IFS=',' read -ra STAGES <<< "$VUS_CSV"
for VUS in "${STAGES[@]}"; do
  VUS="$(echo "$VUS" | tr -d ' ')"
  echo ">>> [${LABEL}] ${VUS} VUs for ${DURATION} ..."
  JSON="$OUT/vus-${VUS}.json"
  LOG="$OUT/vus-${VUS}.log"

  k6 run --quiet --no-color \
    --summary-export="$JSON" \
    --summary-trend-stats="min,avg,med,p(90),p(95),p(99),max" \
    -e "${VU_ENV}=${VUS}" \
    -e LOGIN_DURATION="$DURATION" -e DASHBOARD_DURATION="$DURATION" -e FINAL_DURATION="$DURATION" \
    "$SCENARIO" > "$LOG" 2>&1
  RC=$?

  LOAD="$(srv_load)"

  if [ -f "$JSON" ]; then
    row="$(jq -r '
      .metrics as $m |
      def g(x): (x // 0);
      def d(k): (g($m.http_req_duration[k]) | .*10 | round / 10);
      [ (g($m.iterations.count) | floor),
        (g($m.http_reqs.rate)   | .*10 | round / 10),
        (g($m.http_reqs.count)  | floor),
        (g($m.http_req_failed.value) * 100 | .*100 | round / 100),
        d("p(95)"), d("p(99)"), d("max"),
        (g($m.checks.value) * 100 | .*10 | round / 10)
      ] | @tsv' "$JSON" 2>/dev/null)"
    crossed="$(jq '[.. | objects | select(has("ok")) | .ok] | any(. == false)' "$JSON" 2>/dev/null)"
    if [ "$crossed" = "true" ] || grep -q "have been crossed" "$LOG" 2>/dev/null; then
      verdict="❌ CROSSED"
    else
      verdict="✅ ok"
    fi
    IFS=$'\t' read -r c_it c_rps c_req c_fail c_p95 c_p99 c_max c_chk <<< "$row"
    printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
      "$VUS" "$c_it" "$c_rps" "$c_req" "$c_fail" "$c_p95" "$c_p99" "$c_max" "$c_chk" "$LOAD" "$verdict" >> "$MD"
    echo "    VUs=$VUS rps=$c_rps fail%=$c_fail p95=${c_p95}ms p99=${c_p99}ms checks%=$c_chk load=[$LOAD] $verdict"
  else
    printf '| %s | — | — | — | ERR | — | — | — | — | %s | ⚠ no summary (rc=%s) |\n' "$VUS" "$LOAD" "$RC" >> "$MD"
    echo "    VUs=$VUS -> NO summary (rc=$RC). See $LOG"
    echo "    (tail) $(tail -3 "$LOG" | tr '\n' ' ')"
  fi
done

{
  echo
  echo "**Finished:** $(date +%Y%m%d-%H%M%S)"
  echo
  echo "_Legend: fail% = non-2xx/3xx HTTP responses; checks% = assertion pass rate; ❌ CROSSED = a k6 threshold was violated at this stage (breaking point signal)._"
} >> "$MD"

echo "=== DONE. Report: $MD ==="
cat "$MD"
