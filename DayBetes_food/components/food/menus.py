"""The saved restaurant menus, `Menus` (frontend_conventions.md §9.13): what DiaBot
kept of each menu photo (code_conventions.md §8.12, "Cartas"). They are not
edited by hand: a new photo of the menu updates them.

One page, `/food/menus`, filtered by its URL: `q` (search), `place` (one menu)
and `section`. The places are picked in a pop-up with its own search, so the
page holds however many menus pile up."""

import json
from urllib.parse import urlencode

from fasthtml.common import *

from DayBetes_food.components.modal import (
    ConfirmActionModal,
    ModalLayer,
    close_modal_js,
    modal_confirm_button,
    open_modal_js,
)
from DayBetes_food.components.navigation import back_js
from DayBetes_food.components.settings.subpage import SearchField
from DayBetes_food.domain.constants import MenuSection
from DayBetes_food.domain.menu import MENU_PLACE_PREVIEW, MENU_SECTION_LABELS, menu_sections
from DayBetes_food.time_utils import to_local

MENUS_PATH = "/food/menus"
MENUS_LIST_ID = "menus_list"
_PLACE_PICKER_ID = "menus_place_picker"
# From this many places on, the pop-up gets its own search box.
_PLACE_SEARCH_FROM = 8

_TRASH_ICON = NotStr(
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="h-4 w-4">'
    '<path d="M4 6h12"/><path d="M8 6V4.5h4V6"/><path d="M5.5 6l.8 9.5h7.4l.8-9.5"/></svg>'
)
_MENU_ICON = NotStr(
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="h-5 w-5">'
    '<path d="M4 5.5C4 4.7 4.7 4 5.5 4H11v16H5.5C4.7 20 4 19.3 4 18.5z"/>'
    '<path d="M20 5.5c0-.8-.7-1.5-1.5-1.5H13v16h5.5c.8 0 1.5-.7 1.5-1.5z"/>'
    '<path d="M6.5 8h2.5M6.5 11h2.5M15 8h2.5M15 11h2.5M15 14h2.5"/></svg>'
)

# The pills of Food's header (frontend §9.3): ink when chosen, bare otherwise.
_PILL_CLS = "shrink-0 px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap cursor-pointer transition-colors"
_PILL_ON = "bg-black text-white shadow-md"
_PILL_OFF = "bg-transparent text-gray-700 hover:bg-white/60"


def menus_url(query: str = "", place: str = "", section: str = "") -> str:
    params = {key: value for key, value in (("q", query), ("place", place), ("section", section)) if value}
    return f"{MENUS_PATH}?{urlencode(params)}" if params else MENUS_PATH


def _nav(url: str, **attrs) -> dict:
    """A link that opens another state of the page, in place, with its URL."""
    return {"href": url, "hx_get": url, "hx_target": "#main_content", "hx_push_url": "true", **attrs}


def _price(price: float | None) -> str:
    if price is None:
        return ""
    return f"{int(price)}" if price == int(price) else f"{price:.2f}"


def MenusIconButton():
    """Right of Food's search box (§9.13): small, always there, out of the pills."""
    return A(
        _MENU_ICON,
        **_nav(MENUS_PATH),
        id="food_menus_button",
        aria_label="Restaurant menus",
        title="Restaurant menus",
        cls="""
            shrink-0 w-12 h-12 rounded-2xl
            web_container text-gray-800
            flex items-center justify-center cursor-pointer
            transition-transform duration-150 active:scale-95
        """,
    )


# ============================================
# In Food's search (§9.3, §9.13)
# ============================================


def FoodMenuResults(items: list, query: str, has_more: bool) -> list:
    """Dishes of the user's menus that match a Food search, after the user's own
    results and before Ciqual: a few rows like the others, and the rest in Menus."""
    if not items:
        return []
    rows = []
    for item in items:
        meta = " · ".join(
            part
            for part in (item.place, MENU_SECTION_LABELS[item.section].rstrip("s"), _price(item.price))
            if part
        )
        rows.append(
            A(
                Div(
                    H1(Span(item.name), cls="text-left text-[15px] font-semibold leading-snug"),
                    Div(Span(meta, cls="truncate"), cls="flex items-center text-xs text-gray-500 min-w-0"),
                    P(item.description, cls="text-xs text-gray-700 mt-0.5") if item.description else "",
                    cls="flex flex-col min-w-0",
                ),
                **_nav(menus_url(item.name, item.place)),
                cls="web_container food_entry rounded-2xl flex items-center justify-between cursor-pointer",
            )
        )
    see_all = (
        A(
            "See all in Menus ›",
            **_nav(menus_url(query)),
            cls="md:w-md lg:w-md w-xs text-right text-xs font-semibold text-gray-700 px-1",
        )
        if has_more
        else None
    )
    return [H2("From your menus", cls="web_section_label md:w-md lg:w-md w-xs mt-2"), *rows, *([see_all] if see_all else [])]


# ============================================
# The Menus page
# ============================================


def _place_picker(places: list, query: str, place: str):
    """The places in a pop-up: a list that grows with the menus, searchable from
    _PLACE_SEARCH_FROM places on. Choosing one keeps the search, not the section."""
    rows = [("All places", "", sum(p.item_count for p in places), None)] + [
        (p.place, p.place, p.item_count, p.updated_at) for p in places
    ]
    items = []
    for label, value, count, updated in rows:
        chosen = value.lower() == (place or "").lower()
        meta = f"{count} dish" + ("es" if count != 1 else "") + (f" · {to_local(updated):%d %b}" if updated else "")
        items.append(
            Li(
                A(
                    Span(label, cls=f"flex-1 min-w-0 truncate text-sm {'font-bold' if chosen else 'font-medium'}"),
                    Span(meta, cls="shrink-0 text-xs text-muted"),
                    Span("✓", aria_hidden="true", cls="shrink-0 w-4 text-sm") if chosen else Span(cls="shrink-0 w-4"),
                    **_nav(menus_url(query, value), onclick=close_modal_js(_PLACE_PICKER_ID)),
                    cls="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-line-soft cursor-pointer",
                ),
                data_place_name=label.lower(),
            )
        )
    search = (
        SearchField(
            "menus_place_search",
            "Search places",
            oninput=(
                "var q=this.value.trim().toLowerCase();"
                f"document.querySelectorAll('#{_PLACE_PICKER_ID} [data-place-name]').forEach(function(li){{"
                "li.hidden=q&&li.dataset.placeName.indexOf(q)<0;});"
            ),
        )
        if len(places) >= _PLACE_SEARCH_FROM
        else None
    )
    return ModalLayer(
        P("Places", cls="text-lg font-semibold"),
        search,
        Ul(*items, cls="flex flex-col max-h-[55dvh] overflow-y-auto overscroll-contain -mx-2"),
        modal_id=_PLACE_PICKER_ID,
        card_cls="gap-3",
    )


def _controls(places: list, sections: list, query: str, place: str, section: str):
    place_label = next((p.place for p in places if p.place.lower() == (place or "").lower()), "All places")
    return Div(
        Button(
            Span(place_label, cls="truncate"),
            Span("▾", aria_hidden="true", cls="text-xs text-muted"),
            type="button",
            onclick=open_modal_js(_PLACE_PICKER_ID),
            aria_label=f"Place: {place_label}",
            cls="""
                shrink-0 max-w-[45%] flex items-center gap-1.5 cursor-pointer
                rounded-full bg-control border border-line px-3 py-1.5 text-sm font-semibold text-gray-900
            """,
        ),
        Span(cls="shrink-0 w-px h-5 bg-line"),
        Div(
            *(
                A(label, **_nav(menus_url(query, place, value)), cls=f"{_PILL_CLS} {_PILL_ON if value == section else _PILL_OFF}")
                for label, value in [("All", "")] + [(MENU_SECTION_LABELS[s], s.value) for s in sections]
            ),
            cls="flex items-center gap-1 overflow-x-auto overscroll-x-contain [scrollbar-width:none]",
        ),
        cls="flex items-center gap-2 min-w-0",
    )


def _dish_row(item, *, deletable: bool, show_section: bool):
    detail = " · ".join(
        part for part in (MENU_SECTION_LABELS[item.section].rstrip("s") if show_section else "", item.description or "") if part
    )
    trash = None
    modal = None
    if deletable:
        modal_id = f"menu_item_delete_{item.id}"
        trash = Button(
            _TRASH_ICON,
            type="button",
            aria_label=f"Delete {item.name}",
            onclick=open_modal_js(modal_id),
            cls="""
                shrink-0 h-9 w-9 -mr-2 rounded-full cursor-pointer text-muted
                hover:text-danger hover:bg-danger/5 active:scale-95 transition
                flex items-center justify-center
            """,
        )
        modal = ConfirmActionModal(
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
        )
    return Li(
        Div(
            Div(
                Span(item.name, cls="flex-1 min-w-0 text-[15px] font-semibold text-gray-900 leading-snug"),
                Span(_price(item.price), cls="shrink-0 text-sm text-gray-700 tabular-nums") if item.price is not None else None,
                cls="flex items-baseline gap-2",
            ),
            P(detail, cls="text-xs text-gray-500") if detail else None,
            cls="flex-1 min-w-0 flex flex-col gap-0.5",
        ),
        trash,
        modal,
        id=f"menu_item_{item.id}",
        cls="flex items-start gap-2 py-2.5 border-b border-line-soft last:border-b-0",
    )


def _group(title, rows, *, aside=None):
    return Div(
        Div(Span(title, cls="web_section_label px-1"), aside, cls="flex items-center justify-between gap-2"),
        Ul(*rows, cls="web_container rounded-2xl px-4 py-0.5"),
        cls="flex flex-col gap-1.5",
    )


def _one_place(place: str, items: list):
    """One menu: its dishes by section, each with its trash, and the whole menu's
    delete at the end. Both ask first."""
    modal_id = "menu_place_delete"
    return [
        *(
            _group(MENU_SECTION_LABELS[section], [_dish_row(item, deletable=True, show_section=False) for item in dishes])
            for section, dishes in menu_sections(items)
        ),
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
    ]


def _all_places(items: list, query: str, section: str, filtered: bool):
    """Every menu, one group per place. Without a search or a section, each shows
    MENU_PLACE_PREVIEW dishes and a link to the rest."""
    groups: dict[str, list] = {}
    for item in items:
        groups.setdefault(item.place, []).append(item)
    nodes = []
    for place, dishes in groups.items():
        shown = dishes if filtered else dishes[:MENU_PLACE_PREVIEW]
        open_link = A(
            f"{len(dishes)} ›" if filtered else f"All {len(dishes)} ›",
            **_nav(menus_url(query, place, section)),
            cls="shrink-0 text-xs font-semibold text-gray-700 px-1",
        )
        nodes.append(_group(place, [_dish_row(item, deletable=False, show_section=not section) for item in shown], aside=open_link))
    return nodes


def MenusList(places: list, items: list, *, query: str, place: str, section: str):
    """The part of the page the search box swaps (MENUS_LIST_ID)."""
    shown = [item for item in items if not section or item.section.value == section]
    if not places:
        body = [P("No menus yet. Send DiaBot a photo of a restaurant menu and it saves it here.", cls="text-sm text-muted px-1")]
    elif not shown:
        what = f"“{query}”" if query else "this filter"
        body = [P(f"No dishes match {what}.", cls="text-sm text-muted px-1")]
    elif place:
        body = _one_place(shown[0].place, shown)
    else:
        body = _all_places(shown, query, section, filtered=bool(query or section))
    return Div(*body, id=MENUS_LIST_ID, cls="flex flex-col gap-4")


def MenusPage(places: list, items: list, *, query: str = "", place: str = "", section: str = ""):
    """`items`: the dishes of the chosen place, or of all, already searched; the
    section filters them here, so its pills only offer sections that have any."""
    present = {item.section for item in items}
    sections = [s for s in MenuSection if s in present]
    return Div(
        Div(
            Button(
                "‹ Food",
                type="button",
                cls="self-start text-sm font-medium text-gray-700 cursor-pointer px-1 py-1",
                onclick=back_js("/food"),
            ),
            H1("Menus", cls="text-2xl font-bold text-gray-900 px-1"),
            SearchField(
                "menus_search",
                "Search dishes: arroz, bravas…",
                name="q",
                value=query,
                hx_get=MENUS_PATH,
                hx_trigger="input changed delay:300ms, search",
                hx_include="#menus_place, #menus_section",
                hx_target=f"#{MENUS_LIST_ID}",
                hx_select=f"#{MENUS_LIST_ID}",
                hx_swap="outerHTML",
                hx_replace_url="true",
                data_skip_page_loading="true",
            ),
            Input(type="hidden", id="menus_place", name="place", value=place),
            Input(type="hidden", id="menus_section", name="section", value=section),
            _controls(places, sections, query, place, section) if places else None,
            P("DiaBot saves a menu when you send it a photo; a new photo updates it.", cls="text-xs text-muted px-1"),
            cls="sticky top-0 z-[600] w-full flex flex-col gap-2.5 px-5 pt-6 pb-4 web_glass_strong rounded-b-3xl",
        ),
        MenusList(places, items, query=query, place=place, section=section),
        _place_picker(places, query, place) if places else None,
        cls="w-full max-w-2xl mx-auto px-4 pb-36 flex flex-col gap-4",
    )
