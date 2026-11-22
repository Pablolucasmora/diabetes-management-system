"""The saved restaurant menus, `Menus` (frontend_conventions.md §9.13): what DiaBot
kept of each menu photo (code_conventions.md §8.12, "Cartas"). They are not
edited by hand: a new photo of the menu updates them."""

import json
from urllib.parse import urlencode

from fasthtml.common import *

from DayBetes_food.components.modal import ConfirmActionModal, close_modal_js, modal_confirm_button, open_modal_js
from DayBetes_food.components.navigation import back_js
from DayBetes_food.domain.menu import MENU_SECTION_LABELS, menu_sections
from DayBetes_food.time_utils import to_local

MENUS_PATH = "/food/menus"

_TRASH_ICON = NotStr(
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="h-4 w-4">'
    '<path d="M4 6h12"/><path d="M8 6V4.5h4V6"/><path d="M5.5 6l.8 9.5h7.4l.8-9.5"/></svg>'
)


def menu_place_path(place: str) -> str:
    return f"{MENUS_PATH}/place?{urlencode({'place': place})}"


_MENU_ICON = NotStr(
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="h-5 w-5 md:h-6 md:w-6">'
    '<path d="M4 5.5C4 4.7 4.7 4 5.5 4H11v16H5.5C4.7 20 4 19.3 4 18.5z"/>'
    '<path d="M20 5.5c0-.8-.7-1.5-1.5-1.5H13v16h5.5c.8 0 1.5-.7 1.5-1.5z"/>'
    '<path d="M6.5 8h2.5M6.5 11h2.5M15 8h2.5M15 11h2.5M15 14h2.5"/></svg>'
)


def MenusButton():
    """In the middle of Food's header, between rescue and `+` (§9.13): always there,
    as solid as its neighbours, with its name so it reads at a glance."""
    return A(
        _MENU_ICON,
        Span("Menus", cls="text-sm md:text-base font-semibold"),
        href=MENUS_PATH,
        hx_get=MENUS_PATH,
        hx_target="#main_content",
        hx_push_url="true",
        id="food_menus_button",
        aria_label="Restaurant menus",
        cls="""
            h-12 md:h-14 px-4 md:px-5 rounded-3xl md:rounded-4xl
            bg-surface border border-line-soft text-gray-900
            shadow-[0_4px_14px_rgba(80,60,40,0.14)]
            flex items-center gap-2 cursor-pointer
            transition-transform duration-150 hover:scale-[1.04] active:scale-95
        """,
    )


def _header(back_path: str, back_label: str, title: str, *extra):
    return Div(
        Button(
            f"‹ {back_label}",
            type="button",
            cls="self-start text-sm font-medium text-gray-700 cursor-pointer px-1 py-1",
            onclick=back_js(back_path),
        ),
        H1(title, cls="text-2xl font-bold text-gray-900 px-1 break-words"),
        *extra,
        cls="sticky top-0 z-[600] w-full flex flex-col gap-2 px-5 pt-6 pb-4 web_glass_strong rounded-b-3xl",
    )


_HINT = "DiaBot saves a menu when you send it a photo. To update one, send the new menu."


def MenusPage(places: list):
    """Every place with a saved menu, the latest saved first."""
    if places:
        cards = [
            A(
                Span(place.place, cls="flex-1 min-w-0 truncate text-base font-semibold text-gray-900"),
                Span(
                    f"{place.item_count} dish" + ("es" if place.item_count != 1 else "")
                    + f" · {to_local(place.updated_at):%d %b}",
                    cls="shrink-0 text-xs text-muted",
                ),
                href=menu_place_path(place.place),
                hx_get=menu_place_path(place.place),
                hx_target="#main_content",
                hx_push_url="true",
                cls="web_container rounded-2xl px-4 py-3 flex items-center gap-3 cursor-pointer",
            )
            for place in places
        ]
    else:
        cards = [P("No menus yet. Send DiaBot a photo of a restaurant menu.", cls="text-sm text-muted px-1")]
    return Div(
        _header("/food", "Food", "Menus", P(_HINT, cls="text-xs text-muted px-1")),
        Div(*cards, cls="flex flex-col gap-2"),
        cls="w-full max-w-2xl mx-auto px-4 pb-36 flex flex-col gap-4",
    )


def _price(price: float | None) -> str:
    if price is None:
        return ""
    return f"{int(price)}" if price == int(price) else f"{price:.2f}"


def _item_row(item):
    modal_id = f"menu_item_delete_{item.id}"
    return Li(
        Div(
            Div(
                Span(item.name, cls="flex-1 min-w-0 text-sm font-semibold text-gray-900"),
                Span(_price(item.price), cls="shrink-0 text-sm text-gray-700 tabular-nums") if item.price is not None else None,
                cls="flex items-baseline gap-2",
            ),
            P(item.description, cls="text-xs text-muted") if item.description else None,
            cls="flex-1 min-w-0 flex flex-col gap-0.5",
        ),
        Button(
            _TRASH_ICON,
            type="button",
            aria_label=f"Delete {item.name}",
            onclick=open_modal_js(modal_id),
            cls="""
                shrink-0 h-9 w-9 rounded-full cursor-pointer text-muted
                hover:text-danger hover:bg-danger/5 active:scale-95 transition
                flex items-center justify-center
            """,
        ),
        ConfirmActionModal(
            modal_id=modal_id,
            title="Delete dish",
            question=f"{item.name} will be removed from this menu. This cannot be undone. Continue?",
            yes_button=modal_confirm_button(
                "Yes",
                danger=True,
                hx_post=f"{MENUS_PATH}/items/{item.id}/delete",
                hx_target=f"#menu_item_{item.id}",
                hx_swap="outerHTML",
                hx_on__after_request=close_modal_js(modal_id),
                data_skip_page_loading="true",
            ),
        ),
        id=f"menu_item_{item.id}",
        cls="flex items-start gap-2 py-2 border-b border-line-soft last:border-b-0",
    )


def MenuPlacePage(place: str, items: list):
    """The dishes of one place by section, each with its trash; the whole menu
    can be deleted at the end. Both ask first."""
    modal_id = "menu_place_delete"
    sections = [
        Div(
            Span(MENU_SECTION_LABELS[section], cls="web_section_label px-1"),
            Ul(*(_item_row(item) for item in section_items), cls="web_container rounded-2xl px-4 py-1"),
            cls="flex flex-col gap-1.5",
        )
        for section, section_items in menu_sections(items)
    ]
    return Div(
        _header(MENUS_PATH, "Menus", place, P(_HINT, cls="text-xs text-muted px-1")),
        *sections,
        Button(
            "Delete this menu",
            type="button",
            onclick=open_modal_js(modal_id),
            cls="self-center text-sm font-semibold text-danger cursor-pointer px-3 py-2 rounded-xl hover:bg-danger/5",
        ),
        ConfirmActionModal(
            modal_id=modal_id,
            title="Delete menu",
            question=f"Every dish saved of {place} will be deleted. This cannot be undone. Continue?",
            yes_button=modal_confirm_button(
                "Yes",
                danger=True,
                hx_post=f"{MENUS_PATH}/delete",
                hx_vals=json.dumps({"place": place}),
                hx_swap="none",
                hx_on__after_request=(
                    close_modal_js(modal_id)
                    + ";if(event.detail.successful&&window.dbShowAppNotice)window.dbShowAppNotice('Menu deleted');"
                ),
                data_skip_page_loading="true",
            ),
        ),
        cls="w-full max-w-2xl mx-auto px-4 pb-36 flex flex-col gap-4",
    )
