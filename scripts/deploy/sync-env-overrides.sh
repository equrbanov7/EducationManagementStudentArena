#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# sync-env-overrides.sh — Upsert key=value pairs into the server .env
#
# Usage:
#   ENV_OVERRIDES="KEY1=val1
#   KEY2=val2" bash scripts/deploy/sync-env-overrides.sh /opt/emsarena/app/.env
#
# Behaviour:
#   • If a key already exists in .env with a DIFFERENT value → update it.
#   • If a key does not exist → append it.
#   • If a key exists with the SAME value → skip (no-op).
#   • Blank lines and comment lines in ENV_OVERRIDES are ignored.
#   • The original .env is backed up to .env.bak before any write.
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

ENV_FILE="${1:-/opt/emsarena/app/.env}"

if [ -z "${ENV_OVERRIDES:-}" ]; then
  echo "[sync-env] ENV_OVERRIDES is empty — nothing to sync."
  exit 0
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "[sync-env] ${ENV_FILE} not found — creating it."
  touch "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

changed=0

while IFS= read -r line || [ -n "$line" ]; do
  # Skip blank lines and comments
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue

  key="${line%%=*}"
  value="${line#*=}"

  # Validate key format
  if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "[sync-env] Skipping invalid key: ${key}" >&2
    continue
  fi

  # Check current value in .env
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    current="$(grep "^${key}=" "$ENV_FILE" | head -1 | cut -d'=' -f2-)"
    if [ "$current" = "$value" ]; then
      continue
    fi
    # Back up before first change
    if [ "$changed" -eq 0 ]; then
      cp "$ENV_FILE" "${ENV_FILE}.bak"
    fi
    # Remove old line and append new value (safe with any characters)
    tmp="$(mktemp)"
    grep -v "^${key}=" "$ENV_FILE" > "$tmp"
    echo "${key}=${value}" >> "$tmp"
    mv "$tmp" "$ENV_FILE"
    echo "[sync-env] Updated: ${key}"
    changed=$((changed + 1))
  else
    if [ "$changed" -eq 0 ]; then
      cp "$ENV_FILE" "${ENV_FILE}.bak"
    fi
    echo "${key}=${value}" >> "$ENV_FILE"
    echo "[sync-env] Added:   ${key}"
    changed=$((changed + 1))
  fi
done <<< "$ENV_OVERRIDES"

if [ "$changed" -gt 0 ]; then
  chmod 600 "$ENV_FILE"
  echo "[sync-env] ${changed} variable(s) synced to ${ENV_FILE}."
else
  echo "[sync-env] All variables already up to date."
fi
