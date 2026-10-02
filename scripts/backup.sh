#!/usr/bin/env bash
# Copia de seguridad diaria de producción (infra_conventions §12).
#
# Vuelca datos y roles de Postgres, los cifra con la clave pública de age
# (el servidor puede cifrar pero no descifrar), guarda las últimas copias en
# local y las sube a R2, que las borra a los 90 días.
#
# No se ejecuta desde el repositorio: se instala como root en
# /usr/local/sbin/daybetes-backup y lo lanza el timer de systemd con la
# configuración de /etc/daybetes/backup.env.

# pipefail: sin él, si pg_dump falla, `pg_dump | age` termina bien porque
# solo cuenta el último comando, y quedaría una copia cifrada vacía.
set -euo pipefail

: "${AGE_RECIPIENT:?falta AGE_RECIPIENT}"
: "${BACKUP_REMOTE:?falta BACKUP_REMOTE}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/daybetes}"
KEEP_LOCAL_DAYS="${KEEP_LOCAL_DAYS:-7}"

# Deben coincidir con docker-compose.prod.yml y con el rol propietario (§6).
DB_CONTAINER="${DB_CONTAINER:-deploy_db}"
DB_SUPERUSER=plucmor
DB_NAME=diabetes_db

# Aviso a Healthchecks.io (§12): /start al empezar y el código de salida al
# terminar (0 = bien; otro = fallo). Si un día no llega ninguna señal, el
# servicio avisa por email. Un fallo del aviso nunca hace fallar la copia.
HEALTHCHECK_URL="${HEALTHCHECK_URL:-}"
ping_healthcheck() {
  [ -n "$HEALTHCHECK_URL" ] || return 0
  curl -fsS -m 10 --retry 3 -o /dev/null "$HEALTHCHECK_URL$1" || true
}
trap 'ping_healthcheck "/$?"' EXIT
ping_healthcheck /start

umask 077
mkdir -p "$BACKUP_DIR"
# Restos de una ejecución que falló a medias.
find "$BACKUP_DIR" -name '*.tmp' -delete

stamp="$(date +%Y-%m-%d_%H%M)"
data="$BACKUP_DIR/daybetes_${stamp}.dump.age"
roles="$BACKUP_DIR/daybetes_roles_${stamp}.sql.age"

# Se escribe en .tmp y se renombra al terminar: un archivo a medio escribir
# nunca tiene el nombre de una copia válida.
docker exec "$DB_CONTAINER" pg_dump -U "$DB_SUPERUSER" -Fc "$DB_NAME" \
  | age -r "$AGE_RECIPIENT" > "$data.tmp"
docker exec "$DB_CONTAINER" pg_dumpall -U "$DB_SUPERUSER" --roles-only \
  | age -r "$AGE_RECIPIENT" > "$roles.tmp"
mv "$data.tmp" "$data"
mv "$roles.tmp" "$roles"

rclone copy "$data" "$BACKUP_REMOTE"
rclone copy "$roles" "$BACKUP_REMOTE"

find "$BACKUP_DIR" -name 'daybetes_*.age' -mtime +"$KEEP_LOCAL_DAYS" -delete

echo "Copia completada: $(basename "$data") ($(du -h "$data" | cut -f1)), subida a $BACKUP_REMOTE"
