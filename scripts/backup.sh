#!/usr/bin/env bash
# Daily production backup (infra_conventions §12).
#
# Dumps Postgres data and roles, encrypts them with the age public key (the
# server can encrypt but not decrypt), keeps the latest copies locally and
# uploads them to R2, which deletes them after 90 days.
#
# It is not run from the repository: it is installed as root in
# /usr/local/sbin/daybetes-backup and started by the systemd timer with the
# configuration in /etc/daybetes/backup.env.

# pipefail: without it, if pg_dump fails, `pg_dump | age` still succeeds
# because only the last command counts, leaving an empty encrypted backup.
set -euo pipefail

: "${AGE_RECIPIENT:?AGE_RECIPIENT is not set}"
: "${BACKUP_REMOTE:?BACKUP_REMOTE is not set}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/daybetes}"
KEEP_LOCAL_DAYS="${KEEP_LOCAL_DAYS:-7}"

# Must match docker-compose.prod.yml and the owner role (§6).
DB_CONTAINER="${DB_CONTAINER:-deploy_db}"
DB_SUPERUSER=plucmor
DB_NAME=diabetes_db

# Healthchecks.io signal (§12): /start when starting and the exit code when
# finishing (0 = success; anything else = failure). If no signal arrives one
# day, the service sends an email. A failed signal never fails the backup.
HEALTHCHECK_URL="${HEALTHCHECK_URL:-}"
ping_healthcheck() {
  [ -n "$HEALTHCHECK_URL" ] || return 0
  curl -fsS -m 10 --retry 3 -o /dev/null "$HEALTHCHECK_URL$1" || true
}
trap 'ping_healthcheck "/$?"' EXIT
ping_healthcheck /start

umask 077
mkdir -p "$BACKUP_DIR"
# Leftovers from a run that failed halfway.
find "$BACKUP_DIR" -name '*.tmp' -delete

stamp="$(date +%Y-%m-%d_%H%M)"
data="$BACKUP_DIR/daybetes_${stamp}.dump.age"
roles="$BACKUP_DIR/daybetes_roles_${stamp}.sql.age"

# Written to .tmp and renamed when done: a half-written file never has the
# name of a valid backup.
docker exec "$DB_CONTAINER" pg_dump -U "$DB_SUPERUSER" -Fc "$DB_NAME" \
  | age -r "$AGE_RECIPIENT" > "$data.tmp"
docker exec "$DB_CONTAINER" pg_dumpall -U "$DB_SUPERUSER" --roles-only \
  | age -r "$AGE_RECIPIENT" > "$roles.tmp"
mv "$data.tmp" "$data"
mv "$roles.tmp" "$roles"

rclone copy "$data" "$BACKUP_REMOTE"
rclone copy "$roles" "$BACKUP_REMOTE"

find "$BACKUP_DIR" -name 'daybetes_*.age' -mtime +"$KEEP_LOCAL_DAYS" -delete

echo "Backup completed: $(basename "$data") ($(du -h "$data" | cut -f1)), uploaded to $BACKUP_REMOTE"
