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
GIT_DIR="$(git rev-parse --absolute-git-dir)"
cd "$REPO_ROOT"

PROMOTE_WORKTREE=""

cleanup() {
  if [ -n "$PROMOTE_WORKTREE" ]; then
    git -C "$REPO_ROOT" worktree remove --force "$PROMOTE_WORKTREE" >/dev/null 2>&1 || rm -rf "$PROMOTE_WORKTREE"
  fi
}

trap cleanup EXIT

if [ -e "$GIT_DIR/index.lock" ]; then
  echo "Git index is locked at $GIT_DIR/index.lock." >&2
  echo "Close any running Git operation, then remove the stale lock only if no Git process is active." >&2
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Working tree is dirty. Commit or stash your changes before running git promote." >&2
  exit 1
fi

echo "Fetching latest refs from ${REMOTE}..."
git fetch --prune "$REMOTE" \
  "+refs/heads/${DEVELOP_BRANCH}:refs/remotes/${REMOTE}/${DEVELOP_BRANCH}" \
  "+refs/heads/${STAGING_BRANCH}:refs/remotes/${REMOTE}/${STAGING_BRANCH}" \
  "+refs/heads/${MAIN_BRANCH}:refs/remotes/${REMOTE}/${MAIN_BRANCH}"

PROMOTE_WORKTREE="$(mktemp -d "${TMPDIR:-/tmp}/emsarena-promote.XXXXXX")"
rm -rf "$PROMOTE_WORKTREE"
git worktree add --detach "$PROMOTE_WORKTREE" "${REMOTE}/${STAGING_BRANCH}"

echo "Promoting ${DEVELOP_BRANCH} -> ${STAGING_BRANCH}..."
git -C "$PROMOTE_WORKTREE" merge --no-edit \
  -m "Merge remote-tracking branch '${REMOTE}/${DEVELOP_BRANCH}' into ${STAGING_BRANCH}" \
  "${REMOTE}/${DEVELOP_BRANCH}"
STAGING_HEAD="$(git -C "$PROMOTE_WORKTREE" rev-parse HEAD)"

if [ "$PUSH_CHANGES" = "true" ]; then
  git -C "$PROMOTE_WORKTREE" push "$REMOTE" "HEAD:${STAGING_BRANCH}"
fi

echo "Promoting ${STAGING_BRANCH} -> ${MAIN_BRANCH}..."
git -C "$PROMOTE_WORKTREE" switch --detach "${REMOTE}/${MAIN_BRANCH}"
git -C "$PROMOTE_WORKTREE" merge --no-edit \
  -m "Merge branch '${STAGING_BRANCH}' into ${MAIN_BRANCH}" \
  "$STAGING_HEAD"

if [ "$PUSH_CHANGES" = "true" ]; then
  git -C "$PROMOTE_WORKTREE" push "$REMOTE" "HEAD:${MAIN_BRANCH}"
  git fetch --prune "$REMOTE" \
    "+refs/heads/${STAGING_BRANCH}:refs/remotes/${REMOTE}/${STAGING_BRANCH}" \
    "+refs/heads/${MAIN_BRANCH}:refs/remotes/${REMOTE}/${MAIN_BRANCH}"
fi

echo "Promotion complete: ${DEVELOP_BRANCH} -> ${STAGING_BRANCH} -> ${MAIN_BRANCH}"
