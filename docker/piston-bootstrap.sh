#!/bin/sh
# ─────────────────────────────────────────────────────────────────────────────
# piston-bootstrap.sh
#
# Installs the runtimes EMSArena's practical/coding exams support into a
# running Piston container. Piston starts with NO languages installed — they
# must be fetched via its `/api/v2/packages` endpoint.
#
# Run this AFTER the piston container is healthy:
#
#     docker compose -f docker-compose.prod.yml exec piston \
#         sh -c "wget -qO- http://localhost:2000/api/v2/packages | head"
#     ./docker/piston-bootstrap.sh
#
# Or, on the host (any machine that can reach the piston container):
#
#     PISTON_URL=http://localhost:2000/api/v2 ./docker/piston-bootstrap.sh
#
# The script is idempotent — installing an already-installed runtime is a
# no-op on Piston's side, so it is safe to re-run after upgrades.
# ─────────────────────────────────────────────────────────────────────────────
set -eu

PISTON_URL="${PISTON_URL:-http://piston:2000/api/v2}"

# Languages EMSArena exposes in the exam UI (must stay in sync with the
# PISTON_LANGUAGES mapping in apps/exams/services/coding_runtime.py).
# Format: "language=version" — use "*" to install the latest available.
PACKAGES="
python=3.12.0
javascript=20.11.1
c++=10.2.0
java=15.0.2
"

echo "Bootstrapping Piston at ${PISTON_URL}"

for pkg in $PACKAGES; do
    language="${pkg%=*}"
    version="${pkg#*=}"
    echo "  → installing ${language} ${version}"
    # Piston accepts simple JSON {"language": "...", "version": "..."} on
    # POST /packages. A 200 means installed; 400 with "already installed"
    # is also fine.
    response=$(
        wget --quiet \
             --header="Content-Type: application/json" \
             --post-data="{\"language\":\"${language}\",\"version\":\"${version}\"}" \
             -O - "${PISTON_URL}/packages" 2>&1 || true
    )
    echo "    ${response}"
done

echo "Done. Installed runtimes:"
wget -qO- "${PISTON_URL}/runtimes" || true
