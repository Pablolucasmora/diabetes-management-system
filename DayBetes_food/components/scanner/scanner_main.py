from fasthtml.common import *
from DayBetes_food.components.navigation import back_js
from DayBetes_food.components.modal import ConfirmActionModal, modal_confirm_button, modal_secondary_button


def scanner_main():
    return Main(
        Div(
            Button(
                "Back",
                type="button",
                cls="web_button self-start px-3 py-1.5 text-sm",
                onclick="if(window.__dbStopScanner){window.__dbStopScanner();}" + back_js("/food"),
            ),
            Div(
                Video(
                    id="scanner_video",
                    autoplay=True,
                    playsinline=True,
                    muted=True,
                    cls="w-full h-full object-cover rounded-3xl bg-black relative z-0",
                ),
                Div(
                    id="scanner_border_overlay",
                    cls="absolute inset-0 border-[8px] border-white rounded-3xl pointer-events-none transition-colors duration-100 z-[1]",
                ),
                id="scanner_camera_frame",
                cls="web_container relative z-0 w-full aspect-[4/3] p-2 overflow-hidden",
            ),
            Div(
                P("Detected barcode", cls="text-xs font-semibold uppercase tracking-wide text-gray-600"),
                P("-", id="scanner_detected_code", cls="text-base font-semibold text-gray-900 break-all"),
                id="scanner_result",
                cls="web_container w-full p-3 rounded-2xl flex flex-col gap-1",
            ),
            Div(
                Label("Manual barcode", cls="text-xs font-semibold uppercase tracking-wide text-gray-600"),
                Div(
                    Input(
                        type="text",
                        id="scanner_manual_input",
                        name="barcode_manual",
                        placeholder="Enter barcode",
                        inputmode="numeric",
                        autocomplete="off",
                        cls="web_input w-full text-base focus:shadow-none focus:scale-100",
                    ),
                    Button("Use", id="scanner_manual_use_btn", type="button", cls="web_button px-3 py-1.5 text-sm shrink-0"),
                    cls="w-full flex items-center gap-2.5",
                ),
                cls="web_container w-full p-3 rounded-2xl flex flex-col gap-2.5",
            ),
            Form(
                Input(type="hidden", name="barcode", id="scanner_confirm_barcode", value=""),
                id="scanner_confirm_form",
                hx_post="/scanner/resolve",
                hx_target="#scanner_confirm_feedback",
                hx_swap="innerHTML",
            ),
            Div(id="scanner_confirm_feedback", cls="hidden"),
            # The buttons are wired in static/js/scanner.js, by id.
            ConfirmActionModal(
                modal_id="scanner_confirm_modal",
                title="Confirm barcode",
                question=Span(
                    "Are you sure this is the correct code: ",
                    Span("", id="scanner_confirm_code", cls="font-semibold"),
                    "?",
                ),
                yes_button=modal_confirm_button("Yes", id="scanner_confirm_yes"),
                no_button=modal_secondary_button("No", id="scanner_confirm_no"),
            ),
            cls="""
                min-h-screen
                flex flex-col items-center
                md:mt-7 lg:mt-7 mt-2
                md:w-md lg:w-md w-xs
                w-full mx-auto
                px-2 py-3
                gap-4
            """,
            data_hide_cart="true",
        ),
    )
