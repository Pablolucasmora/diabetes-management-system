#!/usr/bin/env bash
# Daily production backup (infra_conventions §12).
#
# Dumps Postgres data and roles, encrypts them with the age public key (the
# server can encrypt but not decrypt), keeps the latest copies locally and
# uploads them to R2, which deletes them after 90 days.
#
# The assistant's photos (assistant_photo) are left out of the nightly dump and
# copied on their own every PHOTO_EVERY_DAYS days: each copy is complete and
# the photos take far more room than the rest of the data.
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
PHOTO_EVERY_DAYS=10
KEEP_LOCAL_PHOTO_COPIES=2

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
# off_product and ciqual_food keep their structure but not their rows: they are public and can be
# loaded again from scripts/off and scripts/ciqual (measurement_conventions.md §12).
# assistant_photo keeps its structure too: its rows go in the photo copy below.
docker exec "$DB_CONTAINER" pg_dump -U "$DB_SUPERUSER" -Fc \
  --exclude-table-data=off_product --exclude-table-data=ciqual_food --exclude-table-data=assistant_photo "$DB_NAME" \
  | age -r "$AGE_RECIPIENT" > "$data.tmp"
docker exec "$DB_CONTAINER" pg_dumpall -U "$DB_SUPERUSER" --roles-only \
  | age -r "$AGE_RECIPIENT" > "$roles.tmp"
mv "$data.tmp" "$data"
mv "$roles.tmp" "$roles"

rclone copy "$data" "$BACKUP_REMOTE"
rclone copy "$roles" "$BACKUP_REMOTE"

find "$BACKUP_DIR" -name 'daybetes_*.age' -mtime +"$KEEP_LOCAL_DAYS" -delete

# Photo copy: when the latest one here is PHOTO_EVERY_DAYS days old, or there is
# none. Going by its age and not by the date, a night the server was off only
# delays it to the next run. One hour of slack, so the run of day 10 counts.
photo_minutes=$(( PHOTO_EVERY_DAYS * 24 * 60 - 60 ))
if [ -z "$(find "$BACKUP_DIR" -name 'daybetes-photos_*.dump.age' -mmin -"$photo_minutes" -print -quit)" ]; then
  photos="$BACKUP_DIR/daybetes-photos_${stamp}.dump.age"
  docker exec "$DB_CONTAINER" pg_dump -U "$DB_SUPERUSER" -Fc --data-only --table=assistant_photo "$DB_NAME" \
    | age -r "$AGE_RECIPIENT" > "$photos.tmp"
  mv "$photos.tmp" "$photos"
  rclone copy "$photos" "$BACKUP_REMOTE/photos"
  # Keep the latest copies here, oldest removed first.
  ls -1t "$BACKUP_DIR"/daybetes-photos_*.dump.age | tail -n +"$((KEEP_LOCAL_PHOTO_COPIES + 1))" | xargs -r rm --
  echo "Photo backup completed: $(basename "$photos") ($(du -h "$photos" | cut -f1)), uploaded to $BACKUP_REMOTE/photos"
fi

echo "Backup completed: $(basename "$data") ($(du -h "$data" | cut -f1)), uploaded to $BACKUP_REMOTE"
