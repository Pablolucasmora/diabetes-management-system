from fasthtml.common import *


# Pop-ups live in a <dialog> opened with showModal(): the browser paints it in
# the top layer, above the whole page. A plain `fixed inset-0` overlay is not
# enough, because a glass ancestor (backdrop-filter) becomes the containing
# block of its fixed children and the dimmed layer only covered that card
# (frontend_conventions.md §8).

MODAL_CARD_CLS = "bg-surface border border-line-soft shadow-xl rounded-3xl"


def open_modal_js(modal_id: str) -> str:
    return f"dbOpenModal('{modal_id}');"


def close_modal_js(modal_id: str) -> str:
    return f"dbCloseModal('{modal_id}');"


# Every pop-up has the same buttons (frontend_conventions.md §8): the action
# in ink, or in red when it deletes or archives, and a light secondary one.
_MODAL_BUTTON_CLS = "px-4 py-2 rounded-xl text-sm font-semibold cursor-pointer transition-colors"


def modal_confirm_button(label: str, *, danger: bool = False, cls: str = "", **attrs):
    """Main action of a pop-up: red if it deletes something, ink otherwise."""
    colour = "bg-danger hover:bg-danger/90" if danger else "bg-ink hover:bg-ink/90"
    return Button(label, type="button", cls=f"{_MODAL_BUTTON_CLS} text-white {colour} {cls}", **attrs)


def modal_secondary_button(label: str, *, cls: str = "", **attrs):
    """Secondary action of a pop-up (No, Done...)."""
    return Button(
        label,
        type="button",
        cls=f"{_MODAL_BUTTON_CLS} bg-control border border-line text-stone-900 hover:bg-line-soft {cls}",
        **attrs,
    )


def ModalLayer(*content, modal_id: str, card_cls: str = "gap-4"):
    """Full-page dimmed and blurred layer with a solid card in the middle.

    `modal_id` names the layer, which is what `open_modal_js` and
    `close_modal_js` look up. A click outside the card closes it. Every
    pop-up has the same card; `card_cls` only adds spacing or scrolling.
    """
    return Dialog(
        Div(
            Div(
                *content,
                onclick="event.stopPropagation()",
                # showModal() focuses the first focusable element, and on a
                # phone a focused <select> opens its picker on its own. The
                # card takes the focus instead.
                tabindex="-1",
                autofocus=True,
                data_modal_card="true",
                cls=f"{MODAL_CARD_CLS} w-[92vw] max-w-md p-5 flex flex-col outline-none {card_cls}",
            ),
            id=modal_id,
            onclick=close_modal_js(modal_id),
            cls="""
                fixed inset-0
                flex items-center justify-center
                bg-ink/30 backdrop-blur-md
                px-4
                opacity-0
                transition-opacity duration-200
            """,
        ),
        cls="db_modal",
    )


def ConfirmActionModal(modal_id: str, title: str, question, yes_button, no_button=None):
    """Yes/No pop-up. `yes_button` is a `modal_confirm_button`; `question`
    can carry inline nodes (a code in bold). `no_button` replaces the default
    "No", which only closes the pop-up."""
    return ModalLayer(
        Div(
            P(title, cls="text-lg font-semibold"),
            P(question, cls="text-sm md:text-base text-gray-700"),
            cls="flex flex-col gap-1",
        ),
        Div(
            yes_button,
            no_button or modal_secondary_button("No", onclick=close_modal_js(modal_id)),
            cls="flex items-center gap-2 justify-end",
        ),
        modal_id=modal_id,
    )
