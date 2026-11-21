"""The header of a Settings subpage (frontend_conventions.md §9.10, §9.12): a
glass bar fixed at the very top, with `Back`, the title and, when the page has
one, its search box. The guide and Tags share it."""

from fasthtml.common import Button, Div, H1, Input, Label, NotStr, P, Span

from DayBetes_food.components.navigation import back_js

_SEARCH_ICON = NotStr(
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true" '
    'class="h-4 w-4"><circle cx="9" cy="9" r="5.5"/><path d="m13.5 13.5 3.5 3.5" stroke-linecap="round"/></svg>'
)

# The page body under the header: no top margin, so the bar touches the top.
SUBPAGE_CLS = "flex flex-col items-start gap-4 md:w-md lg:w-md w-full px-4 md:px-0 mx-auto md:mb-28 lg:mb-28 mb-24"


def SearchField(input_id: str, placeholder: str, **input_attrs):
    """The search box of a subpage: magnifier, field, and the browser's clear button."""
    return Label(
        Span(_SEARCH_ICON, cls="text-muted"),
        Input(
            type="search",
            id=input_id,
            placeholder=placeholder,
            autocomplete="off",
            aria_label=placeholder,
            cls="flex-1 min-w-0 bg-transparent text-sm outline-none placeholder:text-gray-400",
            **input_attrs,
        ),
        cls="flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2",
    )


def SubpageHeader(title: str, *extra, back_path: str = "/settings", status_id: str | None = None):
    """`Back` and the title, then whatever the page adds (its search box)."""
    return Div(
        Div(
            Button("Back", type="button", cls="web_button px-3 py-1.5 text-sm", onclick=back_js(back_path)),
            H1(title, cls="text-lg font-semibold text-stone-900"),
            cls="flex items-center justify-between",
        ),
        *extra,
        P("", id=status_id, role="status", cls="text-xs text-muted empty:hidden") if status_id else None,
        cls="sticky top-0 z-10 w-full flex flex-col gap-3 px-4 pt-4 pb-3 web_glass_strong rounded-b-3xl",
    )
