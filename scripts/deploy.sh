#!/usr/bin/env bash
# Production deploy (infra_conventions §13).
#
# Triggered by the GitHub Action: it logs in as `deploy`, whose key can only
# run `sudo /usr/local/sbin/daybetes-deploy`. It is not run from the
# repository: it is installed as a root-owned copy (§12).
#
# Updates /opt/daybetes to origin/main, applies schema migrations, rebuilds and
# starts production and checks that the app responds. Any failure exits non-zero, which marks the
# Action as failed.
set -euo pipefail

REPO_DIR=/opt/daybetes
WEB_CONTAINER=deploy_web
HEALTH_URL=http://127.0.0.1:8000/auth/login
HEALTH_TIMEOUT_SECONDS=60

cd "$REPO_DIR"

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

./scripts/prod.sh up -d --build --remove-orphans

# The app is checked from inside its own container: production publishes no
# port to check it from (§3).
deadline=$((SECONDS + HEALTH_TIMEOUT_SECONDS))
until docker exec "$WEB_CONTAINER" python -c \
  "import urllib.request; urllib.request.urlopen('$HEALTH_URL', timeout=3)" 2>/dev/null; do
  if (( SECONDS >= deadline )); then
    echo "The app is not responding after ${HEALTH_TIMEOUT_SECONDS}s. Latest web logs:" >&2
    ./scripts/prod.sh logs --tail 30 web >&2
    exit 1
  fi
  sleep 2
done

# Every build leaves the previous image untagged; without this the disk fills up.
docker image prune -f > /dev/null

echo "Deploy completed: $after"
