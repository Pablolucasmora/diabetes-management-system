from fasthtml.common import *


def scanner_main():
    return Main(
        Div(
            Button(
                "Back",
                type="button",
                cls="web_button self-start px-3 py-1.5 text-sm",
                hx_get="/menu",
                hx_target="#main_content",
                hx_push_url="true",
                **{"hx-on:click": "if(window.__dbStopScanner){window.__dbStopScanner();}"},
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
                        cls="web_input w-full text-sm",
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
            Div(
                Div(
                    P("Confirm barcode", cls="text-lg font-semibold text-gray-900"),
                    P(
                        "Are you sure this is the correct code: ",
                        Span("", id="scanner_confirm_code", cls="font-semibold"),
                        "?",
                        cls="text-sm text-gray-700",
                    ),
                    Div(
                        Button(
                            "Yes",
                            id="scanner_confirm_yes",
                            type="button",
                            cls="web_button px-4 py-2 text-sm bg-black text-white border-black",
                        ),
                        Button(
                            "No",
                            id="scanner_confirm_no",
                            type="button",
                            cls="web_button px-4 py-2 text-sm border-black text-black",
                        ),
                        cls="flex items-center justify-end gap-2",
                    ),
                    cls="web_container p-5 rounded-3xl w-[92vw] max-w-md flex flex-col gap-4",
                ),
                id="scanner_confirm_modal",
                cls="""
                    fixed inset-0 z-50
                    flex items-center justify-center
                    bg-black/35 backdrop-blur-xl
                    px-4
                    opacity-0 invisible pointer-events-none
                    transition-opacity duration-100
                """,
                style="z-index: 9999;",
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
