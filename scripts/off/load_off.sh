#!/usr/bin/env bash
# Replaces off_product with the file from clean_off.py, in one transaction: on
# any failure the previous copy stays (measurement_conventions.md §12.2).
#
# Usage: sudo scripts/off/load_off.sh off_products.csv.gz
# Development: DB_CONTAINER=diabetes_db DB_SUPERUSER=<user> DB_NAME=<db> scripts/off/load_off.sh <file>
set -euo pipefail

DB_CONTAINER="${DB_CONTAINER:-deploy_db}"
DB_SUPERUSER="${DB_SUPERUSER:-plucmor}"
DB_NAME="${DB_NAME:-diabetes_db}"

if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo "Usage: $0 off_products.csv.gz" >&2
  exit 1
fi

columns="code, name, brand, categories, calories_100g, carbs_100g, sugars_100g, fats_100g, saturated_100g,
  proteins_100g, fiber_100g, caffeine, alcohol_vol, default_portion, nutriscore, nova, ciqual_food_code,
  unique_scans_n, source_modified_at, export_date, name_is_store_brand"

{
  printf 'BEGIN;\nTRUNCATE off_product;\nCOPY off_product (%s) FROM STDIN WITH (FORMAT csv, HEADER);\n' "$columns"
  gunzip -c "$1"
  printf '\\.\nCOMMIT;\n'
} | docker exec -i "$DB_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$DB_SUPERUSER" -d "$DB_NAME"

docker exec "$DB_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$DB_SUPERUSER" -d "$DB_NAME" \
  -c "ANALYZE off_product;" \
  -c "SELECT count(*) AS products, max(export_date) AS export_date,
             pg_size_pretty(pg_total_relation_size('off_product')) AS size FROM off_product;"
