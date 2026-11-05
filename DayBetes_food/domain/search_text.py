"""The text that food searches compare with: lowercase and without accents
(code_conventions.md §11.7).

The same character map feeds the generated columns and the search terms, so a
stored value and a term can never be normalized differently.
"""

_ACCENTED = "ÁÀÂÄÃÅáàâäãåÉÈÊËéèêëÍÌÎÏíìîïÓÒÔÖÕóòôöõÚÙÛÜúùûüÑñÇç"
_PLAIN = "AAAAAAaaaaaaEEEEeeeeIIIIiiiiOOOOOoooooUUUUuuuuNnCc"
_TRANSLATION = str.maketrans(_ACCENTED, _PLAIN)


def normalize_search_text(raw) -> str:
    return " ".join(str(raw or "").translate(_TRANSLATION).lower().split())


def search_text_sql(expression: str) -> str:
    """SQL form of normalize_search_text, immutable so a generated column can use it."""
    return f"lower(translate({expression}, '{_ACCENTED}', '{_PLAIN}'))"
