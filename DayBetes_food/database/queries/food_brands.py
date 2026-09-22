"""Queries para la tabla `food_brands`."""

from typing import Optional

from DayBetes_food.database.queries.crud import _execute_query, _execute_query_many, _build_fuzzy_search


def clean_brand_label(brand_name: str) -> str:
    """Etiqueta visible: solo trim y colapso de espacios (decisión 0.1)."""
    return " ".join((brand_name or "").strip().split())


def brand_code(brand_name: str) -> str:
    """Clave estable. Debe coincidir con ck_food_brands_code_normalized."""
    return clean_brand_label(brand_name).lower()


def create_food_brand(connection, label: str, created_by: int = None, commit: bool = True) -> int:
    """Create a food brand and return its ID. Raises ValidationError if validation fails."""
    from DayBetes_food.errors import ValidationError
    
    clean_label = clean_brand_label(label)
    code = brand_code(label)
    if not code:
        raise ValidationError("Brand name is required.")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO food_brands (code, label, created_by, created_at, updated_at)
                VALUES (%(code)s, %(label)s, %(created_by)s, NOW(), NOW())
                ON CONFLICT (code) DO NOTHING
                RETURNING id;
                """,
                {"code": code, "label": clean_label, "created_by": created_by},
            )
            row = cursor.fetchone()
            if row is None:  # ya existía: se conserva su label original
                cursor.execute("SELECT id FROM food_brands WHERE code = %(code)s;", {"code": code})
                row = cursor.fetchone()
        if commit:
            connection.commit()
        return int(row["id"])
    except Exception:
        if commit:
            connection.rollback()
        raise


def get_food_brand_id_by_label(connection, label: str) -> Optional[int]:
    """Get the ID of a food brand by its label text. Returns None if not found."""
    code = brand_code(label)
    if not code:
        return None
    row = _execute_query(
        connection,
        "SELECT id FROM food_brands WHERE code = %(code)s;",
        {"code": code},
        commit=False,
    )
    return int(row["id"]) if row else None


def get_food_brand_suggestions(connection, search: str = "", limit: int = 50) -> list[str]:
    search_condition, search_params, search_order = _build_fuzzy_search(connection, "label", search)
    params = {**search_params, "limit": max(1, min(int(limit or 50), 500))}
    query = """
        SELECT label
        FROM food_brands
        WHERE is_active = TRUE
          AND {search_condition}
        ORDER BY {search_order}
        LIMIT %(limit)s;
    """.format(
        search_condition=search_condition or "TRUE",
        search_order=search_order if search_condition else "label",
    )
    rows = _execute_query_many(connection, query, params, commit=False)
    return [str(row["label"]) for row in rows if row and row.get("label")]
