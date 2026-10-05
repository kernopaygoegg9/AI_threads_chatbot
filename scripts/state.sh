#!/usr/bin/env bash
# Sync the bot state directory with the `state` branch.
#   scripts/state.sh pull          check out the branch into $STATE_DIR (creates it on first run)
#   scripts/state.sh push "<msg>"  commit and push any changes in $STATE_DIR
set -euo pipefail

BRANCH="${STATE_BRANCH:-state}"
DIR="${STATE_DIR:-state}"

case "${1:-}" in
  pull)
    if [ -e "$DIR/.git" ]; then
      # already checked out (local dashboard): just fast-forward to the latest bot state
      git -C "$DIR" pull -q --rebase origin "$BRANCH"
    elif git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
      git fetch --depth 1 origin "+$BRANCH:refs/remotes/origin/$BRANCH"
      git worktree add -B "$BRANCH" "$DIR" "origin/$BRANCH"
    else
      # first run: start an empty orphan branch (works on old git without `worktree add --orphan`)
      git worktree add --detach "$DIR"
      git -C "$DIR" checkout -q --orphan "$BRANCH"
      git -C "$DIR" rm -rfq --ignore-unmatch .
    fi
    ;;
  push)
    cd "$DIR"
    git add -A
    if git diff --cached --quiet; then
      echo "state: no changes"
      exit 0
    fi
    git -c user.name="threads-bot" -c user.email="threads-bot@users.noreply.github.com" \
      commit -q -m "${2:-bot: update state}"
    git push -q origin "HEAD:$BRANCH"
    ;;
  *)
    echo "usage: $0 pull|push [message]" >&2
    exit 2
    ;;
esac
