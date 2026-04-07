#!/usr/bin/env bash
set -euo pipefail

REMOTE="origin"
DEVELOP_BRANCH="${DEVELOP_BRANCH:-Develop}"
STAGING_BRANCH="${STAGING_BRANCH:-Staging}"
MAIN_BRANCH="${MAIN_BRANCH:-main}"
PUSH_CHANGES="true"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --no-push)
      PUSH_CHANGES="false"
      ;;
    --remote)
      if [ "$#" -lt 2 ]; then
        echo "--remote requires a value." >&2
        exit 1
      fi
      REMOTE="$2"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $(basename "$0") [--no-push] [--remote <name>]" >&2
      exit 1
      ;;
  esac
  shift
done

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

CURRENT_BRANCH="$(git branch --show-current || true)"

restore_branch() {
  if [ -n "${CURRENT_BRANCH:-}" ] && [ "$(git branch --show-current || true)" != "$CURRENT_BRANCH" ]; then
    git checkout "$CURRENT_BRANCH" >/dev/null 2>&1 || true
  fi
}

trap restore_branch EXIT

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Working tree is dirty. Commit or stash your changes before running git promote." >&2
  exit 1
fi

echo "Fetching latest refs from ${REMOTE}..."
git fetch "$REMOTE" "$DEVELOP_BRANCH" "$STAGING_BRANCH" "$MAIN_BRANCH" --prune

echo "Promoting ${DEVELOP_BRANCH} -> ${STAGING_BRANCH}..."
git checkout "$STAGING_BRANCH"
git pull --ff-only "$REMOTE" "$STAGING_BRANCH"
git merge --no-edit "${REMOTE}/${DEVELOP_BRANCH}"

if [ "$PUSH_CHANGES" = "true" ]; then
  git push "$REMOTE" "$STAGING_BRANCH"
fi

echo "Promoting ${STAGING_BRANCH} -> ${MAIN_BRANCH}..."
git checkout "$MAIN_BRANCH"
git pull --ff-only "$REMOTE" "$MAIN_BRANCH"
git merge --no-edit "$STAGING_BRANCH"

if [ "$PUSH_CHANGES" = "true" ]; then
  git push "$REMOTE" "$MAIN_BRANCH"
fi

echo "Promotion complete: ${DEVELOP_BRANCH} -> ${STAGING_BRANCH} -> ${MAIN_BRANCH}"
