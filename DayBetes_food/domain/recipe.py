"""Constants and pure rules of the `recipe` table.

See conventions/code_conventions.md §3.6. This module imports no psycopg,
routes or components.

The `recipe` audit is still pending: this module only holds what saving a
cart plate as a recipe needs (frontend_conventions.md §7.13, provisional).
"""

# Maximum length of recipe.name, equal to the column's VARCHAR(255)
# (database/schema.py). §7.3 requires declaring it once and rejecting the
# excess at the boundary with 422, never truncating it.
RECIPE_NAME_MAX_LENGTH = 255
