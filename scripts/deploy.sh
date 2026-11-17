#!/usr/bin/env bash
# Production deploy (infra_conventions §13).
#
# Triggered by the GitHub Action: it logs in as `deploy`, whose key can only
# run `sudo /usr/local/sbin/daybetes-deploy`. It is not run from the
# repository: it is installed as a root-owned copy (§12).
#
# Updates /opt/daybetes to origin/main, applies schema migrations, rebuilds and
# starts production and checks that the app responds. If the new version does
# not respond, the previous image and code are brought back (infra_conventions
# §13). Any failure exits non-zero, which marks the Action as failed.
set -euo pipefail

REPO_DIR=/opt/daybetes
WEB_CONTAINER=deploy_web
# Image that Compose builds for web (project name + service).
WEB_IMAGE=diabetes_deploy-web
ROLLBACK_IMAGE="$WEB_IMAGE:rollback"
HEALTH_URL=http://127.0.0.1:8000/auth/login
HEALTH_TIMEOUT_SECONDS=60

cd "$REPO_DIR"

# The app answers from inside its own container: production publishes no port
# to check it from (§3).
wait_until_healthy() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT_SECONDS))
  until docker exec "$WEB_CONTAINER" python -c \
    "import urllib.request; urllib.request.urlopen('$HEALTH_URL', timeout=3)" 2>/dev/null; do
    if (( SECONDS >= deadline )); then
      return 1
    fi
    sleep 2
  done
}

before="$(git rev-parse --short HEAD)"
git fetch --quiet origin main
# --ff-only: if something was changed by hand on the server, the deploy stops
# instead of overwriting or merging it.
git merge --ff-only --quiet origin/main
after="$(git rev-parse --short HEAD)"
echo "Code: $before -> $after"

# Migrate first, as a separate one-shot container. If it fails, the script
# stops here and the running web is never touched: `up` would remove the old
# web container before a dependency finished, even with depends_on.
./scripts/prod.sh run --rm --build migrate

# The image running now is kept under its own tag, to bring it back if the new
# one does not start. Valid while migrations add before they remove (§14): the
# previous code still works on the migrated schema.
has_rollback=false
if docker image inspect "$WEB_IMAGE:latest" > /dev/null 2>&1; then
  docker image tag "$WEB_IMAGE:latest" "$ROLLBACK_IMAGE"
  has_rollback=true
fi

./scripts/prod.sh up -d --build --remove-orphans

if ! wait_until_healthy; then
  echo "The app is not responding after ${HEALTH_TIMEOUT_SECONDS}s. Latest web logs:" >&2
  ./scripts/prod.sh logs --tail 30 web >&2
  if [[ "$has_rollback" != true ]]; then
    echo "No previous image to roll back to." >&2
    exit 1
  fi
  echo "Rolling back to $before." >&2
  # Code and image back to the previous version, so that a manual `up --build`
  # does not bring the broken one again. The next deploy fast-forwards from here.
  git reset --hard --quiet "$before"
  docker image tag "$ROLLBACK_IMAGE" "$WEB_IMAGE:latest"
  ./scripts/prod.sh up -d --no-build web
  if wait_until_healthy; then
    echo "Rolled back: $before is running. The deploy of $after failed." >&2
  else
    echo "The rollback does not respond either: manual intervention needed." >&2
  fi
  exit 1
fi

# Every build leaves the previous image untagged; without this the disk fills up.
docker image prune -f > /dev/null

echo "Deploy completed: $after"
