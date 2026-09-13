#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════
# EMS Arena — image build-info (P1-07, Codex audit 2026-09-13)
# ═══════════════════════════════════════════════════════════════════════════
# Image qurulanda BİR DƏFƏ işləyir (docker/Dockerfile.prod) və /app/build-info.json
# yazır: hansı commit-dən qurulub (sha), hansı Django ilə, nə vaxt. /health/
# bunu `build` açarı altında oxuyur (core/health_build_info.py) ki, işləyən
# image mənbədən geri qaldıqda (image drift) sahib bunu dərhal görsün;
# remote_deploy.sh isə deploy sonunda `build.sha`-nı qurduğu SHA ilə tutuşdurur.
# Sirr yoxdur: yalnız SHA, versiya və vaxt.
set -eu

OUT="${1:-/app/build-info.json}"
SHA="${BUILD_GIT_SHA:-unknown}"
case "$SHA" in
  "" ) SHA="unknown" ;;
esac

python - "$OUT" "$SHA" <<'PY'
import datetime
import json
import platform
import sys

import django

out, sha = sys.argv[1], sys.argv[2]
payload = {
    "sha": sha,
    "django": django.get_version(),
    "python": platform.python_version(),
    "built_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2, sort_keys=True)
    fh.write("\n")
print(f"build-info: {out} <- {payload}")
PY
