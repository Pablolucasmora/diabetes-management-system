"""Visible attribution of third-party data (measurement_conventions.md §12.2)."""

from fasthtml.common import *

from DayBetes_food.config import OPEN_FOOD_FACTS_BASE_URL

ODBL_URL = "https://opendatacommons.org/licenses/odbl/1-0/"


def _external_link(text: str, href: str):
    # A new tab keeps the draft of the form that links here.
    return A(text, href=href, target="_blank", rel="noopener noreferrer", cls="underline")


def off_attribution(barcode: str | None = None):
    """With a barcode, the link points to that product's page, as OFF asks."""
    source_url = f"{OPEN_FOOD_FACTS_BASE_URL}/product/{barcode}" if barcode else OPEN_FOOD_FACTS_BASE_URL
    return P(
        "Contains data from ",
        _external_link("Open Food Facts", source_url),
        ", available under the ",
        _external_link("Open Database License", ODBL_URL),
        ".",
        cls="text-xs text-gray-500 text-center",
    )


def ciqual_attribution():
    return P(
        "Source: ",
        _external_link("Anses. 2025. Ciqual French food composition table", "https://ciqual.anses.fr/"),
        ". Spanish names translated for DayBetes.",
        cls="text-xs text-gray-500 text-center",
    )
