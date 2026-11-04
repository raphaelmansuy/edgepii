#!/usr/bin/env bash
# Publish the site to GitHub Pages from the local build.
#
# The preferred path is CI: a push to `main` runs `.github/workflows/site.yml`,
# which builds the site and deploys it with `actions/deploy-pages`. Pages must be
# set to the GitHub Actions source for that to work.
#
# This script is the fallback. It builds the site and force-pushes it to the
# `gh-pages` branch, which Pages serves when its source is "Deploy from a
# branch". It needs only the `repo` token scope, so it works when a token cannot
# push a workflow file.
#
# The build output must land at the branch root, not under `site/dist`. Pages
# serves the branch root, so a nested path makes every URL a 404.
#
# Usage: `bash site/publish.sh`

set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> building"
make site

echo "==> publishing to gh-pages"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
cp -R site/dist/. "$STAGE/"

# Build the branch in a temporary index, so the working tree and the current
# branch are untouched. A force push is correct here: gh-pages holds only output.
git --work-tree="$STAGE" --git-dir=.git checkout -f --orphan gh-pages-tmp >/dev/null 2>&1 || true
git --work-tree="$STAGE" --git-dir=.git add -A -f . >/dev/null

echo "==> files staged: $(git --git-dir=.git diff --cached --name-only | wc -l | tr -d ' ')"
git --work-tree="$STAGE" --git-dir=.git commit -q -m "Publish the docs site" || echo "==> nothing new to publish"

echo "==> push (needs the repo scope)"
git --git-dir=.git push -f origin gh-pages

echo "==> done. https://raphaelmansuy.github.io/edgepii/"
