"""Tags of a food, dish or recipe on its detail page (frontend_conventions.md §9.4.1).

The user's tags on the entry are pills with a × to take them off. `+ Tag`
opens a native <details> with the other tags they can use (the system ones
and their own) and a field to create a new one. Every action answers with the
whole block, painted from what is stored (§6).
"""

import json
import re

from fasthtml.common import *

from DayBetes_food.domain.tag import TAG_NAME_MAX_LENGTH, TagRead

_HEX_RE = re.compile(r"^#([0-9A-Fa-f]{6})$")


def tag_text_color(color: str) -> str:
    """Dark text on light colors, white on dark ones. The pastel hsl() of
    tag_color_from_name is always light."""
    match = _HEX_RE.match(color or "")
    if not match:
        return "#111827"
    value = match.group(1)
    r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#111827" if luminance > 0.6 else "#FFFFFF"


def tag_pill_style(tag: TagRead) -> str:
    """The color is validated before it is stored (ck_tags_color), so it is safe
    inside a style attribute."""
    return f"background:{tag.color};color:{tag_text_color(tag.color)};border-color:rgba(0,0,0,0.15);"


_PILL_CLS = "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold"


def entry_tags_id(entry_type: str, entry_id: int) -> str:
    return f"entry_tags_{entry_type}_{entry_id}"


def _action_attrs(entry_type: str, entry_id: int, tag_id: int, linked: bool, keep_open: bool) -> dict:
    return {
        "hx_post": f"/food/tags/{entry_type}/{entry_id}",
        "hx_vals": json.dumps({"tag_id": str(tag_id), "linked": "true" if linked else "false",
                               "open": "true" if keep_open else "false"}),
        "hx_target": f"#{entry_tags_id(entry_type, entry_id)}",
        "hx_swap": "outerHTML",
        "data_skip_page_loading": "true",
        "hx-disabled-elt": "this",
    }


def EntryTags(entry_type: str, entry_id: int, linked: list[TagRead], available: list[TagRead], open_panel: bool = False):
    linked_ids = {tag.id for tag in linked}
    others = [tag for tag in available if tag.id not in linked_ids]
    block_id = entry_tags_id(entry_type, entry_id)
    pills = [
        Span(
            tag.name,
            Button(
                "×",
                type="button",
                aria_label=f"Remove tag {tag.name}",
                cls="leading-none text-sm opacity-70 hover:opacity-100 cursor-pointer",
                **_action_attrs(entry_type, entry_id, tag.id, linked=False, keep_open=False),
            ),
            cls=_PILL_CLS,
            style=tag_pill_style(tag),
        )
        for tag in linked
    ]
    panel = Div(
        (
            Div(
                *[
                    Button(
                        f"+ {tag.name}",
                        type="button",
                        aria_label=f"Add tag {tag.name}",
                        cls=f"{_PILL_CLS} cursor-pointer opacity-80 hover:opacity-100",
                        style=tag_pill_style(tag),
                        **_action_attrs(entry_type, entry_id, tag.id, linked=True, keep_open=True),
                    )
                    for tag in others
                ],
                cls="flex flex-wrap gap-1.5",
            )
            if others
            else ""
        ),
        Form(
            Input(
                name="name",
                type="text",
                placeholder="New tag",
                aria_label="New tag",
                autocomplete="off",
                maxlength=str(TAG_NAME_MAX_LENGTH),
                required=True,
                cls="web_input min-w-0 flex-1 rounded-lg border border-line px-2 py-1 text-sm",
            ),
            Button("Add", type="submit", cls="web_button px-3 py-1 text-sm rounded-lg"),
            hx_post=f"/food/tags/{entry_type}/{entry_id}/new",
            hx_target=f"#{block_id}",
            hx_swap="outerHTML",
            data_skip_page_loading="true",
            cls="flex items-center gap-2",
        ),
        cls="flex flex-col gap-2 pt-2",
    )
    return Div(
        Div(*pills, cls="flex flex-wrap items-center gap-1.5 empty:hidden"),
        Details(
            Summary(
                "+ Tag",
                cls=f"{_PILL_CLS} w-fit cursor-pointer list-none border-dashed border-gray-400 text-gray-700 bg-white/70",
            ),
            panel,
            open=open_panel,
        ),
        id=block_id,
        cls="flex flex-col gap-1.5 pt-1",
    )
