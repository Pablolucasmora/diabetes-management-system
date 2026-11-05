#!/usr/bin/env python3
"""Builds the file that fills `off_product` from an Open Food Facts export
(measurement_conventions.md §12.2).

Runs on the developer's computer, not on the server. The rules are the approved
filters of §12.2, and this script is also the method the ODbL asks to offer
before any public use of the copy.

Usage:
    python clean_off.py food.parquet off_products.csv.gz --export-date 2026-11-05
"""

import argparse
import tempfile
from datetime import date
from pathlib import Path

import duckdb

NUTRIENTS = {
    "kcal": "energy-kcal",
    "carbs": "carbohydrates",
    "sugars": "sugars",
    "fat": "fat",
    "saturated": "saturated-fat",
    "proteins": "proteins",
    "fiber": "fiber",
    "caffeine": "caffeine",
    "alcohol": "alcohol",
}
NAME_MAX_LENGTH = 255
BRAND_MAX_LENGTH = 255
# A name equal to a brand this big is a contributor's mistake, not a product name:
# "hacendado" is an error, while "Coca-Cola" or "Nesquik" are real names.
STORE_BRAND_MIN_PRODUCTS = 1000
# Filtering on the STRUCTs of `nutriments` crashes DuckDB 2.0, so each nutrient
# becomes plain columns first: <alias> ("100g", already normalized) and <alias>_unit.
FLATTEN_SQL = """
    COPY (
        WITH picked AS (
            SELECT code, product_name, brands, categories, categories_tags, countries_tags, serving_quantity, serving_size,
                   nutriscore_grade, nova_group, categories_properties.ciqual_food_code AS ciqual_food_code,
                   unique_scans_n, last_modified_t, {picked}
            FROM read_parquet('{source}')
        )
        SELECT * EXCLUDE ({picked_names}), {flattened} FROM picked
    ) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
"""
CANDIDATES_SQL = r"""
    CREATE TEMP TABLE candidates AS
    WITH named AS (
        SELECT *, coalesce(
            list_filter(product_name, lambda x: x.lang = 'es' AND trim(coalesce(x.text, '')) <> '')[1].text,
            list_filter(product_name, lambda x: x.lang = 'main' AND trim(coalesce(x.text, '')) <> '')[1].text,
            list_filter(product_name, lambda x: x.lang = 'en' AND trim(coalesce(x.text, '')) <> '')[1].text,
            list_filter(product_name, lambda x: trim(coalesce(x.text, '')) <> '')[1].text
        ) AS picked_name
        FROM read_parquet('{flat}')
    ), scoped AS (
        SELECT *,
            trim(regexp_replace(picked_name, '[[:cntrl:]\s]+', ' ', 'g')) AS clean_name,
            trim(regexp_replace(split_part(coalesce(brands, ''), ',', 1), '[[:cntrl:]\s]+', ' ', 'g')) AS clean_brand
        FROM named
        WHERE (coalesce(list_contains(countries_tags, 'en:spain'), false) OR (code LIKE '84%' AND length(code) = 13))
          AND regexp_full_match(code, '[0-9]{{8,48}}') AND picked_name IS NOT NULL
          AND carbs BETWEEN 0 AND 100 AND fat BETWEEN 0 AND 100 AND proteins BETWEEN 0 AND 100
          AND carbs_unit = 'g' AND fat_unit = 'g' AND proteins_unit = 'g'
          AND carbs + fat + proteins <= 105
          AND coalesce(sugars, 0) <= carbs + 0.01 AND coalesce(saturated, 0) <= fat + 0.01
    )
    SELECT code,
        clean_name AS name,
        CASE WHEN length(clean_brand) BETWEEN 1 AND {brand_max} THEN clean_brand END AS brand,
        -- The English tags first: the adapter's category rules look for English words.
        coalesce(
            nullif(array_to_string(list_transform(
                list_filter(categories_tags, lambda tag: tag LIKE 'en:%'),
                lambda tag: replace(tag[4:], '-', ' ')
            ), ', '), ''),
            nullif(regexp_replace(coalesce(categories, ''), '[[:cntrl:]]+', ' ', 'g'), '')
        ) AS categories,
        CASE WHEN kcal BETWEEN 0 AND 900 AND kcal_unit = 'kcal'
              AND abs(kcal - (4 * carbs + 9 * fat + 4 * proteins + 2 * coalesce(fiber, 0))) <= greatest(0.25 * kcal, 20)
             THEN round(kcal, 3) END AS calories_100g,
        round(carbs, 3) AS carbs_100g,
        CASE WHEN sugars IS NOT NULL THEN round(least(sugars, carbs), 3) END AS sugars_100g,
        round(fat, 3) AS fats_100g,
        CASE WHEN saturated IS NOT NULL THEN round(least(saturated, fat), 3) END AS saturated_100g,
        round(proteins, 3) AS proteins_100g,
        round(fiber, 3) AS fiber_100g,
        -- "100g" is in grams even when the contributor's unit says mg.
        CASE WHEN caffeine BETWEEN 0 AND 1 THEN round(caffeine * 1000, 3) END AS caffeine,
        CASE WHEN alcohol BETWEEN 0 AND 100 THEN round(alcohol, 3) END AS alcohol_vol,
        CASE WHEN regexp_matches(lower(coalesce(serving_size, '')), '[0-9] ?g\b')
             THEN TRY_CAST(serving_quantity AS DOUBLE) END AS default_portion,
        nullif(nullif(nullif(nutriscore_grade, 'unknown'), 'not-applicable'), '') AS nutriscore,
        nova_group AS nova,
        ciqual_food_code,
        unique_scans_n,
        to_timestamp(last_modified_t) AS source_modified_at,
        DATE '{export_date}' AS export_date
    FROM scoped
    WHERE length(clean_name) BETWEEN 1 AND {name_max}
    QUALIFY row_number() OVER (PARTITION BY code ORDER BY last_modified_t DESC NULLS LAST) = 1
"""


def flatten(con, source: Path, target: Path) -> None:
    picked = ", ".join(
        f"list_filter(nutriments, lambda x: x.name = '{off}')[1] AS n_{alias}" for alias, off in NUTRIENTS.items()
    )
    flattened = ", ".join(f'n_{alias}."100g" AS {alias}, n_{alias}.unit AS {alias}_unit' for alias in NUTRIENTS)
    con.execute(
        FLATTEN_SQL.format(
            picked=picked,
            picked_names=", ".join(f"n_{alias}" for alias in NUTRIENTS),
            flattened=flattened,
            source=source,
            target=target,
        )
    )


def report(con) -> None:
    total, no_kcal, no_brand, serving, ciqual = con.execute(
        "SELECT count(*), count(*) FILTER (calories_100g IS NULL), count(*) FILTER (brand IS NULL), "
        "count(default_portion), count(ciqual_food_code) FROM candidates"
    ).fetchone()
    print(f"products: {total}, without kcal: {no_kcal}, without brand: {no_brand}, "
          f"with serving: {serving}, with Ciqual code: {ciqual}")
    named_as_brand = con.execute(
        "SELECT lower(name), count(*) FROM candidates WHERE name_is_store_brand GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall()
    print(f"out of the text search, named as a store brand: {sum(n for _, n in named_as_brand)} {named_as_brand}")
    if total == 0:
        raise SystemExit("No product passed the filters: the export changed its shape.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="food.parquet from Open Food Facts")
    parser.add_argument("output", type=Path, help="target .csv.gz")
    parser.add_argument("--export-date", required=True, type=date.fromisoformat, help="date of the export, YYYY-MM-DD")
    args = parser.parse_args()

    con = duckdb.connect()
    con.execute("SET memory_limit='8GB'; SET preserve_insertion_order=false;")
    with tempfile.TemporaryDirectory(dir=args.output.parent) as work_dir:
        flat = Path(work_dir) / "flat.parquet"
        flatten(con, args.source, flat)
        con.execute(
            CANDIDATES_SQL.format(
                flat=flat,
                brand_max=BRAND_MAX_LENGTH,
                name_max=NAME_MAX_LENGTH,
                export_date=args.export_date.isoformat(),
            )
        )
        con.execute(
            f"""
            ALTER TABLE candidates ADD COLUMN name_is_store_brand BOOLEAN DEFAULT FALSE;
            UPDATE candidates SET name_is_store_brand = TRUE
            WHERE lower(name) IN (
                SELECT lower(brand) FROM candidates WHERE brand IS NOT NULL
                GROUP BY 1 HAVING count(*) >= {STORE_BRAND_MIN_PRODUCTS}
            );
            """
        )
        report(con)
        con.execute(f"COPY candidates TO '{args.output}' (FORMAT CSV, HEADER, COMPRESSION GZIP)")
    print(f"written: {args.output} ({args.output.stat().st_size / 1_000_000:.1f} MB)")


if __name__ == "__main__":
    main()
