#!/usr/bin/env bash
# Publish the site to GitHub Pages from the local build.
#
# The preferred path is CI: a push to `main` runs the Pages workflow, which
# builds the site and deploys it. Pages must be set to the GitHub Actions source
# for that to work.
#
# This script is the fallback. It builds the site and force-pushes it to the
# `gh-pages` branch, which Pages serves when its source is "Deploy from a
# branch". It needs only the `repo` token scope, so it works when a token cannot
# push a workflow file.
#
# Two details that broke earlier runs, both fixed here:
#
#   1. Pages serves the branch ROOT. Committing `site/dist/` puts the files
#      under a prefix, and every URL 404s while the build reports success. The
#      output is staged in a temporary directory first.
#   2. `git checkout --work-tree=...` still moves HEAD. That left the working
#      tree on a throwaway branch. This script builds the commit with plumbing
#      commands instead, so HEAD and the working tree never move.
#
# Usage: `bash site/publish.sh`

set -euo pipefail

cd "$(dirname "$0")/.."

BRANCH=gh-pages

# A token in an environment variable shadows the keyring login, so clear it and
# read the good token from `gh`. A GIT_ASKPASS helper is the one mechanism that
# works for both `git push` and a credential.helper set to a shell function.
if TOKEN=$(env -u GITHUB_TOKEN gh auth token 2>/dev/null); then
  ASKPASS=$(mktemp)
  cat > "$ASKPASS" <<ASKEOF
#!/bin/sh
case "\$1" in
  Username*) echo x-access-token ;;
  Password*) echo "$TOKEN" ;;
esac
ASKEOF
  chmod +x "$ASKPASS"
  export GIT_ASKPASS="$ASKPASS"
  export GIT_TERMINAL_PROMPT=0
  trap 'rm -f "$ASKPASS"' EXIT
else
  echo "note: no gh token, relying on your git credential helper" >&2
fi

echo "==> building"
make site

echo "==> staging the build output"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
cp -R site/dist/. "$STAGE/"

if [ ! -f "$STAGE/index.html" ]; then
  echo "error: no index.html in the build, so Pages would serve nothing" >&2
  exit 1
fi

echo "==> building the commit without touching HEAD"
# A fresh index file, so the current branch's staging area is untouched.
export GIT_INDEX_FILE="$STAGE/.git-index"
PARENT=$(git rev-parse --verify --quiet "refs/heads/$BRANCH" || true)
git --work-tree="$STAGE" add -A -f .
TREE=$(git write-tree)
if [ -n "$PARENT" ]; then
  COMMIT=$(git commit-tree "$TREE" -p "$PARENT" -m "Publish the docs site")
else
  COMMIT=$(git commit-tree "$TREE" -m "Publish the docs site")
fi
unset GIT_INDEX_FILE

count=$(git ls-tree -r --name-only "$COMMIT" | wc -l | tr -d ' ')
echo "==> $count files in the published tree"

if [ -n "$PARENT" ] && [ "$COMMIT" = "$PARENT" ]; then
  echo "==> nothing changed, already published"
  exit 0
fi

# Only output lives on this branch, so a force push is safe and keeps history small.
# `-c credential.helper=` clears the keychain helper for this one command: an
# empty helper list makes git use GIT_ASKPASS. Without it, a stale keychain entry
# answers first and the push fails with "Invalid username or token".
echo "==> pushing $BRANCH"
git -c credential.helper= push -f origin "$COMMIT:refs/heads/$BRANCH"

echo "==> done. https://raphaelmansuy.github.io/edgepii/"
