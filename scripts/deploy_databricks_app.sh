#!/usr/bin/env bash
# Deploy the edgepii demo as a Databricks App, end to end.
#
# This exists because the README's hand-copied commands drift: a resource
# attached by hand, a model version bumped in the console, a branch renamed.
# The script is the procedure, and --verify proves the result rather than
# assuming it.
#
# Usage:
#   ./scripts/deploy_databricks_app.sh --profile opengenie-dev
#   ./scripts/deploy_databricks_app.sh --profile opengenie-dev --verify
#   ./scripts/deploy_databricks_app.sh --profile opengenie-dev --dry-run
#
# Environment:
#   PROFILE      Databricks CLI profile (default: DEFAULT)
#   APP_NAME     App name (default: edgepii-demo)
#   BRANCH       Git branch to deploy from (default: current branch)
#   REPO_URL     Repository URL (default: this repo's origin)
#   LLM_ENDPOINT Foundation-model endpoint for generation
#   ML_ENDPOINT  Served PII classifier; pass "none" to skip the ML lane
#   APP_PATH     Directory inside the repo holding the app
#
# Exit codes: 0 success, 1 a step failed, 2 bad usage.

set -euo pipefail

PROFILE="${PROFILE:-DEFAULT}"
APP_NAME="${APP_NAME:-edgepii-demo}"
APP_PATH="${APP_PATH:-apps/edgepii-databricks}"
LLM_ENDPOINT="${LLM_ENDPOINT:-databricks-gpt-oss-20b}"
ML_ENDPOINT="${ML_ENDPOINT:-edgepii-pii-ml}"
DRY_RUN=0
VERIFY=0

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 2
}

log()  { printf '\033[36m->\033[0m %s\n' "$*"; }
ok()   { printf '\033[32mok \033[0m %s\n' "$*"; }
die()  { printf '\033[31mxx \033[0m %s\n' "$*" >&2; exit 1; }

run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '\033[35m[dry-run]\033[0m %s\n' "$*"
  else
    "$@"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:?--profile needs a value}"; shift 2 ;;
    --app)     APP_NAME="${2:?--app needs a value}"; shift 2 ;;
    --branch)  BRANCH="${2:?--branch needs a value}"; shift 2 ;;
    --repo)    REPO_URL="${2:?--repo needs a value}"; shift 2 ;;
    --verify)  VERIFY=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

command -v databricks >/dev/null 2>&1 || die "the databricks CLI is not on PATH"

# Resolve the branch and repo so a deploy never silently ships the wrong commit.
if [[ -z "${BRANCH:-}" ]]; then
  BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
fi
if [[ -z "${REPO_URL:-}" ]]; then
  REPO_URL="$(git -C "$REPO_ROOT" remote get-url origin | sed -E 's#\.git$##; s#^git@github\.com:#https://github.com/#')"
fi
COMMIT="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"

log "profile      $PROFILE"
log "app          $APP_NAME"
log "branch       $BRANCH"
log "commit       $COMMIT"
log "repo         $REPO_URL"
log "app path     $APP_PATH"
log "llm          $LLM_ENDPOINT"
log "ml detector  $ML_ENDPOINT"

# ---------------------------------------------------------------- preflight

log "checking credentials"
if [[ $DRY_RUN -eq 0 ]]; then
  databricks current-user me --profile "$PROFILE" -o json >/dev/null 2>&1 \
    || die "profile '$PROFILE' is not authenticated. Run: databricks auth login --profile $PROFILE"
fi
ok "credentials work"

log "checking the branch is pushed"
if [[ $DRY_RUN -eq 0 ]]; then
  LOCAL="$(git -C "$REPO_ROOT" rev-parse HEAD)"
  REMOTE="$(git -C "$REPO_ROOT" rev-parse "origin/$BRANCH" 2>/dev/null || echo none)"
  if [[ "$LOCAL" != "$REMOTE" ]]; then
    die "origin/$BRANCH is not at HEAD. A Git deploy reads the remote, so push first:
    git push -u origin $BRANCH"
  fi
  ok "origin/$BRANCH is at $COMMIT"
fi

# ------------------------------------------------------------------ resources

# The app's service principal needs CAN_QUERY on every endpoint it calls. Build
# the list here rather than by hand, because a missing entry fails at runtime
# with a 403 that does not name the cause.
RESOURCES=$(python3 - "$LLM_ENDPOINT" "$ML_ENDPOINT" <<'PY'
import json, sys
llm, ml = sys.argv[1], sys.argv[2]
rows = [{"name": "edgepii-model",
         "serving_endpoint": {"name": llm, "permission": "CAN_QUERY"}}]
if ml and ml.lower() != "none":
    rows.append({"name": "edgepii-ml-detector",
                 "serving_endpoint": {"name": ml, "permission": "CAN_QUERY"}})
print(json.dumps(rows))
PY
)

# --------------------------------------------------------------------- deploy

EXISTS=$(databricks apps get "$APP_NAME" --profile "$PROFILE" -o json 2>/dev/null \
         | python3 -c 'import json,sys; print(json.load(sys.stdin).get("name",""))' 2>/dev/null || true)

if [[ -z "$EXISTS" ]]; then
  log "creating app $APP_NAME"
  CREATE=$(python3 - "$APP_NAME" "$REPO_URL" "$BRANCH" "$APP_PATH" <<'PY'
import json, sys
name, url, branch, path = sys.argv[1:5]
print(json.dumps({
    "name": name,
    "description": "edgepii: mask PII before a Databricks model reads the prompt, then restore the answer",
    "git_repository": {"provider": "gitHub", "url": url, "branch": branch},
    "path": path,
}))
PY
)
  run databricks apps create --profile "$PROFILE" --json "$CREATE" --timeout 20m -o json >/dev/null
  ok "app created"
else
  log "app $APP_NAME exists"
fi

log "attaching endpoint resources"
UPDATE=$(python3 - "$APP_NAME" "$REPO_URL" "$RESOURCES" <<'PY'
import json, sys
name, url, resources = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
print(json.dumps({
    "name": name,
    "git_repository": {"provider": "gitHub", "url": url},
    "resources": resources,
}))
PY
)
# `apps update` insists on the git repository alongside the resources in this
# workspace, so both go in one payload.
run databricks apps update "$APP_NAME" --profile "$PROFILE" --json "$UPDATE" -o json >/dev/null
ok "resources attached"

# The app must be RUNNING before a deploy is accepted.
STATE=$(databricks apps get "$APP_NAME" --profile "$PROFILE" -o json 2>/dev/null \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["compute_status"]["state"])' 2>/dev/null || echo UNKNOWN)
if [[ "$STATE" != "ACTIVE" ]]; then
  log "starting compute (was $STATE)"
  run databricks apps start "$APP_NAME" --profile "$PROFILE" >/dev/null || true
  for _ in $(seq 1 40); do
    STATE=$(databricks apps get "$APP_NAME" --profile "$PROFILE" -o json 2>/dev/null \
            | python3 -c 'import json,sys; print(json.load(sys.stdin)["compute_status"]["state"])' 2>/dev/null || echo UNKNOWN)
    [[ "$STATE" == "ACTIVE" ]] && break
    sleep 15
  done
fi
[[ "$STATE" == "ACTIVE" ]] || die "compute did not reach ACTIVE (last: $STATE)"
ok "compute ACTIVE"

log "deploying commit $COMMIT from $BRANCH"
DEPLOY=$(printf '{"git_source":{"branch":"%s","source_code_path":"%s"}}' "$BRANCH" "$APP_PATH")
run databricks apps deploy "$APP_NAME" --profile "$PROFILE" --json "$DEPLOY" -o json >/dev/null
ok "deployment succeeded"

URL=$(databricks apps get "$APP_NAME" --profile "$PROFILE" -o json 2>/dev/null \
      | python3 -c 'import json,sys; print(json.load(sys.stdin).get("url",""))')
ok "app url: $URL"

# --------------------------------------------------------------------- verify

if [[ $VERIFY -eq 0 ]]; then
  log "skipping verification (pass --verify to run it)"
  exit 0
fi

log "verifying the deployment"

TOKEN=$(databricks auth token --profile "$PROFILE" -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

check() {
  local path="$1" want="$2" label="$3" code
  code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" \
              --max-time 60 "$URL$path" || echo 000)
  if [[ "$code" == "$want" ]]; then
    ok "$label ($path -> $code)"
  else
    die "$label: expected $want, got $code at $path"
  fi
}

check "/api/health"   200 "health"
check "/"             200 "demo page"
check "/tutorial"     200 "tutorial page"
check "/architecture" 200 "architecture page"

# The lanes the app advertises must match what was deployed, so a forgotten env
# var is caught here rather than by a reader.
LANES=$(curl -s -H "Authorization: Bearer $TOKEN" --max-time 60 "$URL/api/config" \
        | python3 -c 'import json,sys; print(",".join(l["name"] for l in json.load(sys.stdin)["lanes"]))')
if [[ -n "$ML_ENDPOINT" && "$ML_ENDPOINT" != "none" && "$LANES" != *ml* ]]; then
  die "ML endpoint set but lanes are: $LANES"
fi
ok "lanes: $LANES"

# One real run, through the ML lane when it is configured. This is the only
# check that proves the service principal can reach both endpoints.
BODY=$(python3 - "$ML_ENDPOINT" <<'PY'
import json, sys
ml = sys.argv[1]
lane = "hybrid" if ml and ml.lower() != "none" else "rules"
print(json.dumps({
    "source": "Ada Lovelace called from +852 5555 0101. Email ada@example.com.",
    "model": "databricks-gpt-oss-20b",
    "lane": lane,
}))
PY
)
RESULT=$(curl -s -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
              -X POST --max-time 240 -d "$BODY" "$URL/api/run")
printf '%s' "$RESULT" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
if not payload.get("ok"):
    raise SystemExit("run failed: %s %s" % (payload.get("error"), str(payload.get("message"))[:160]))
print("  lane=%s spans=%s gate=%s" % (payload["lane"], payload["span_count"], payload["restore_ok"]))
print("  masked: %s" % payload["masked"][:96])
'
ok "end-to-end run succeeded"

printf '\n\033[32mDeployed.\033[0m %s\n' "$URL"
