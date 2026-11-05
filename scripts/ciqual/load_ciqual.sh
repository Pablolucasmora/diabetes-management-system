#!/usr/bin/env bash
# Replaces ciqual_food with the file from clean_ciqual.py, in one transaction: on
# any failure the previous copy stays (measurement_conventions.md §12.3).
#
# Usage: sudo scripts/ciqual/load_ciqual.sh ciqual_foods.csv.gz
# Development: DB_CONTAINER=diabetes_db DB_SUPERUSER=<user> DB_NAME=<db> scripts/ciqual/load_ciqual.sh <file>
set -euo pipefail

DB_CONTAINER="${DB_CONTAINER:-deploy_db}"
DB_SUPERUSER="${DB_SUPERUSER:-plucmor}"
DB_NAME="${DB_NAME:-diabetes_db}"

if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo "Usage: $0 ciqual_foods.csv.gz" >&2
  exit 1
fi

columns="code, name_es, name_en, name_fr, category_hint, subtype, calories_100g, carbs_100g, sugars_100g,
  fats_100g, saturated_100g, proteins_100g, fiber_100g, alcohol, carbs_confidence, fats_confidence,
  proteins_confidence, value_notes, export_date"

{
  printf 'BEGIN;\nTRUNCATE ciqual_food;\nCOPY ciqual_food (%s) FROM STDIN WITH (FORMAT csv, HEADER);\n' "$columns"
  gunzip -c "$1"
  printf '\\.\nCOMMIT;\n'
} | docker exec -i "$DB_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$DB_SUPERUSER" -d "$DB_NAME"

docker exec "$DB_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$DB_SUPERUSER" -d "$DB_NAME" \
  -c "ANALYZE ciqual_food;" \
  -c "SELECT count(*) AS foods, max(export_date) AS export_date FROM ciqual_food;"
