#!/usr/bin/env bash
# Report work that exists only in this clone: local branches with commits no remote
# has, local tags missing on origin, stashes, and uncommitted changes.
# Exit 0 = everything is on the remote. Exit 1 = something is only here.
# Usage: scripts/unpushed-check.sh [--fetch]
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
[[ "${1:-}" == "--fetch" ]] && git fetch --quiet --tags origin
problems=0
note() { echo "ONLY HERE: $*"; problems=1; }

while read -r branch; do
  n="$(git rev-list --count "refs/heads/$branch" --not --remotes)"
  [[ "$n" -eq 0 ]] || note "branch '$branch' has $n commit(s) no remote branch contains"
done < <(git for-each-ref --format='%(refname:short)' refs/heads)

remote_tags="$(git ls-remote --tags origin 2>/dev/null | sed -n 's#.*refs/tags/\([^^]*\)$#\1#p' | sort -u)"
while read -r tag; do
  [[ -n "$tag" ]] || continue
  grep -qxF "$tag" <<<"$remote_tags" || note "tag '$tag' is not on origin"
done < <(git tag)

[[ -z "$(git stash list)" ]] || note "$(git stash list | wc -l) stash entr(ies) (stashes are never pushed)"
[[ -z "$(git status --porcelain)" ]] || note "uncommitted changes ($(git status --porcelain | wc -l) path(s))"

if [[ "$problems" -eq 0 ]]; then echo "OK: everything in this clone is on a remote."; fi
exit "$problems"
