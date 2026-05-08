from fasthtml.common import *
from DayBetes_food.database.queries.crud import get_all_tags
from DayBetes_food.components.injection_zone import (
    BASE_INJECTION_ZONE_IMAGE,
    INJECTION_ZONE_IMAGE_BY_KEY,
    INJECTION_ZONE_LABEL_BY_KEY,
    asset_busted,
)
from DayBetes_food.time_utils import utc_naive_to_local


def settings_main(connection, current_user=None):
    username = (current_user or {}).get("username") or "Usuario"
    email = (current_user or {}).get("email") or ""
    return Div(
        Div(
            H1("Settings", cls="text-xl font-bold text-center"),
            Div(
                H2(username, cls="text-3xl font-extrabold text-center text-gray-900"),
                P(email, cls="text-xs text-gray-500 text-center"),
                cls="mt-2 flex flex-col items-center gap-1",
            ),
            P(
                "Configure profile, targets, and app preferences.",
                cls="text-sm text-gray-600 text-center",
            ),
            Form(
                Input(type="hidden", name="csrf_token", value=""),
                Button(
                    "Cerrar sesion",
                    type="submit",
                    cls="web_button px-4 py-2 text-sm text-white",
                    style="background-color:#b91c1c;border-color:#b91c1c;",
                ),
                action="/auth/logout",
                method="post",
                cls="mt-3",
                onsubmit=(
                    "var m=document.cookie.match(/(?:^|; )daybetes_csrf=([^;]+)/);"
                    "if(m){this.querySelector(\"input[name='csrf_token']\").value=decodeURIComponent(m[1]);}"
                ),
            ),
            Button(
                "Tags",
                type="button",
                cls="web_button food_entry flex items-center justify-between cursor-pointer text-left mt-2",
                hx_get="/settings/tags",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            Button(
                "Injection log",
                type="button",
                cls="web_button food_entry flex items-center justify-between cursor-pointer text-left",
                hx_get="/settings/injections",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            cls="web_container p-6 flex flex-col items-center gap-3",
        ),
        cls="flex flex-col items-center justify-center gap-6 md:mt-7 lg:mt-7 mt-2",
    )


def _tag_color_swatch(color: str):
    return Button(
        "",
        type="button",
        data_tag_color_trigger="true",
        cls="block w-8 h-8 rounded-lg border border-gray-300 shrink-0 p-0",
        style=f"background:{color};min-width:2rem;min-height:2rem;",
        title="Edit color",
        aria_label="Edit color",
        data_tag_color_preview="true",
    )


def tag_settings_row(tag: dict):
    tag_id = int(tag.get("id") or 0)
    if not tag_id:
        return ""
    color = str(tag.get("color") or "hsl(0 80% 90%)")
    return Form(
        Input(type="hidden", name="tag_id", value=str(tag_id)),
        Input(
            name="name",
            value=str(tag.get("name") or ""),
            cls="web_input bg-transparent border-0 text-base font-semibold blur-none focus:shadow-none focus:scale-100 focus:outline-none w-full",
            style="transition:none; transform:none; scale:1; box-shadow:none; outline:none;",
            hx_post="/settings/tags/update",
            hx_trigger="blur, change",
            hx_target=f"#tag_row_{tag_id}",
            hx_swap="outerHTML",
            hx_include="closest form",
        ),
        Div(
            Input(type="hidden", name="color", value=color, data_tag_color_value="true"),
            _tag_color_swatch(color),
            cls="flex items-center justify-end",
        ),
        Div(id=f"tag_msg_{tag_id}", cls="sr-only"),
        id=f"tag_row_{tag_id}",
        hx_post="/settings/tags/update",
        hx_target=f"#tag_row_{tag_id}",
        hx_swap="outerHTML",
        hx_include="closest form",
        cls="web_container food_entry flex items-center justify-between gap-3",
    )


def tags_settings_list(tags: list[dict]):
    if not tags:
        return Div(P("No tags found.", cls="text-sm text-gray-600"))
    return Div(*(tag_settings_row(tag) for tag in tags if int(tag.get("id") or 0)), cls="flex flex-col gap-2 w-full")


def tags_settings_page(connection):
    tags = get_all_tags(connection, search="", limit=1000)
    return Div(
        Div(
            Button(
                "Back",
                type="button",
                cls="web_button self-start px-3 py-1.5 text-sm",
                hx_get="/settings",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            cls="w-full flex justify-start",
        ),
        H1("Tags", cls="text-xl font-bold"),
        Input(
            type="text",
            name="q",
            placeholder="Search tag by name",
            autocomplete="off",
            cls="web_input rounded-2xl bg-gray-200/50 border-[0.6px] border-white p-4 w-full",
            hx_get="/settings/tags/list",
            hx_trigger="input changed delay:500ms",
            hx_target="#settings-tags-list",
            hx_swap="innerHTML",
        ),
        Div(tags_settings_list(tags), id="settings-tags-list", cls="w-full"),
        Link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/@simonwep/pickr/dist/themes/classic.min.css"),
        Script(src="https://cdn.jsdelivr.net/npm/@simonwep/pickr/dist/pickr.min.js"),
        Script(
            """
            (function(){
              if (window.__dbTagColorPickerBootstrapped) return;
              window.__dbTagColorPickerBootstrapped = true;

              var active = { form: null, hidden: null, preview: null };
              var pickr = null;

              function cleanupPicker() {
                if (!pickr) return;
                try { pickr.hide(); } catch(_) {}
                try { pickr.destroyAndRemove && pickr.destroyAndRemove(); } catch(_) {}
                pickr = null;
              }

              function cssColorToHex(color) {
                var value = String(color || "").trim();
                if (!value) return "#dbeafe";
                if (value[0] === "#") return value;
                var probe = document.createElement("span");
                probe.style.color = value;
                probe.style.position = "absolute";
                probe.style.left = "-9999px";
                document.body.appendChild(probe);
                var computed = window.getComputedStyle(probe).color || "";
                document.body.removeChild(probe);
                var m = computed.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/i);
                if (!m) return "#dbeafe";
                var toHex = function(n) {
                  var x = Math.max(0, Math.min(255, parseInt(n, 10) || 0));
                  return x.toString(16).padStart(2, "0");
                };
                return "#" + toHex(m[1]) + toHex(m[2]) + toHex(m[3]);
              }

              function ensurePickr(defaultColor) {
                if (pickr) return pickr;
                if (!window.Pickr) return null;
                var host = document.createElement("div");
                host.id = "db_tag_color_picker_host";
                document.body.appendChild(host);
                pickr = window.Pickr.create({
                  el: "#db_tag_color_picker_host",
                  theme: "classic",
                  default: defaultColor || "#dbeafe",
                  useAsButton: true,
                  appClass: "db-tag-picker",
                  components: {
                    preview: true,
                    opacity: false,
                    hue: true,
                    interaction: {
                      hex: true,
                      input: true,
                      save: true,
                      cancel: true
                    }
                  }
                });
                pickr.on("save", function(color){
                  if(!active.form || !active.hidden || !active.preview) return;
                  var hex = color ? color.toHEXA().toString() : "";
                  if(!hex) return;
                  active.hidden.value = hex;
                  active.preview.style.background = hex;
                  if(window.htmx) htmx.trigger(active.form, "submit");
                  cleanupPicker();
                });
                pickr.on("cancel", function(){
                  cleanupPicker();
                });
                pickr.on("hide", function(){
                  if (pickr) cleanupPicker();
                });
                return pickr;
              }

              document.addEventListener("click", function(ev){
                var trigger = ev.target && ev.target.closest ? ev.target.closest("[data-tag-color-trigger='true']") : null;
                if(!trigger) return;
                ev.preventDefault();
                var form = trigger.closest("form");
                if(!form) return;
                var hidden = form.querySelector("[data-tag-color-value='true']");
                var preview = form.querySelector("[data-tag-color-preview='true']");
                active = { form: form, hidden: hidden, preview: preview };
                var current = cssColorToHex(hidden && hidden.value ? hidden.value : "#dbeafe");
                ensurePickr(current);
                if(!pickr) return;
                try { pickr.setColor(current, true); } catch(_) {}
                pickr.show();
              }, true);

              document.addEventListener("mousedown", function(ev){
                if (!pickr) return;
                var app = document.querySelector(".pcr-app");
                if (app && !app.contains(ev.target) && !(ev.target && ev.target.closest && ev.target.closest("[data-tag-color-trigger='true']"))) {
                  cleanupPicker();
                }
              }, true);
            })();
            """
        ),
        cls="flex flex-col items-center gap-4 md:mt-7 lg:mt-7 mt-2 md:w-md lg:w-md w-xs w-full mx-auto md:mb-28 lg:mb-28 mb-24",
        data_hide_cart="true",
    )


def _format_injection_day(dt):
    return f"{dt.strftime('%b')} {dt.day}, {dt.year}"


def _format_injection_hour(dt):
    return dt.strftime("%H:%M")


def _open_modal_js(modal_id: str):
    return (
        f"const m=document.getElementById('{modal_id}');"
        "if(!m) return;"
        "m.classList.remove('invisible','opacity-0','pointer-events-none');"
        "m.classList.add('opacity-100');"
    )


def _close_modal_js(modal_id: str):
    return (
        f"const m=document.getElementById('{modal_id}');"
        "if(!m) return;"
        "m.classList.remove('opacity-100');"
        "m.classList.add('opacity-0','invisible','pointer-events-none');"
    )


def _injection_delete_modal(item: dict):
    injection_id = int(item.get("id") or 0)
    modal_id = f"settings_injection_delete_{injection_id}"
    refresh_js = "htmx.ajax('GET','/settings/injections',{target:'#main_content',swap:'innerHTML'});"
    return Div(
        Div(
            Div(
                P("Delete injection", cls="text-lg font-semibold"),
                P("Are you sure you want to delete this injection log?", cls="text-sm md:text-base text-gray-700"),
                cls="flex flex-col gap-1",
            ),
            Div(
                Button(
                    "Yes",
                    type="button",
                    cls="web_button px-4 py-2 text-sm text-white",
                    style="background-color:#b91c1c;border-color:#b91c1c;",
                    hx_post=f"/settings/injections/{injection_id}/delete",
                    hx_swap="none",
                    **{"hx-on:htmx:after-request": refresh_js},
                    onclick=_close_modal_js(modal_id),
                ),
                Button(
                    "No",
                    type="button",
                    cls="web_button px-4 py-2 text-sm",
                    onclick=_close_modal_js(modal_id),
                ),
                cls="flex items-center gap-2 justify-end",
            ),
            onclick="event.stopPropagation()",
            cls="web_container p-5 md:p-6 rounded-3xl w-[92vw] max-w-md flex flex-col gap-4",
        ),
        id=modal_id,
        onclick=_close_modal_js(modal_id),
        cls="""
            fixed inset-0 z-[70]
            flex items-center justify-center
            bg-slate-800/30 backdrop-blur-lg
            px-4
            opacity-0 invisible pointer-events-none
            transition-opacity duration-200
        """,
    )


def _injection_edit_modal(item: dict):
    injection_id = int(item.get("id") or 0)
    modal_id = f"settings_injection_edit_{injection_id}"
    local_dt = utc_naive_to_local(item.get("shot_time"))
    shot_hour = local_dt.strftime("%H:%M") if local_dt else ""
    shot_date = local_dt.strftime("%Y-%m-%d") if local_dt else ""
    insulin_type = str(item.get("insulin_type") or "").strip().lower() or "rapid"
    selected_zone = str(item.get("injection_zone") or "").strip()
    basal_units = item.get("basal_units")
    base_image = asset_busted(BASE_INJECTION_ZONE_IMAGE)
    image = asset_busted(INJECTION_ZONE_IMAGE_BY_KEY.get(selected_zone)) if selected_zone in INJECTION_ZONE_IMAGE_BY_KEY else base_image
    selector_js = (
        f"const mid='{modal_id}';"
        "const box=document.getElementById(mid);"
        "if(!box) return;"
        "const zone=this.getAttribute('data-zone')||'';"
        "const img=box.querySelector('[data-settings-injection-image]');"
        "const hidden=box.querySelector('[data-settings-injection-zone-input]');"
        "if(hidden){hidden.value=zone;}"
        "if(img){img.src=this.getAttribute('data-zone-img')||img.src;}"
        "box.querySelectorAll('[data-zone]').forEach(function(el){"
        "el.classList.remove('ring-2','ring-cyan-500','bg-cyan-50');"
        "});"
        "this.classList.add('ring-2','ring-cyan-500','bg-cyan-50');"
    )
    switch_type_js = (
        f"const box=document.getElementById('{modal_id}');"
        "if(!box) return;"
        "const sel=box.querySelector('[data-settings-insulin-type]');"
        "const basal=box.querySelector('[data-settings-basal-wrap]');"
        "if(!sel||!basal) return;"
        "if(sel.value==='basal'){basal.classList.remove('hidden');}"
        "else{basal.classList.add('hidden');}"
    )
    zone_buttons = [
        Button(
            INJECTION_ZONE_LABEL_BY_KEY[zone_key],
            type="button",
            cls=(
                "web_button px-3 py-2 text-xs "
                + ("ring-2 ring-cyan-500 bg-cyan-50" if selected_zone == zone_key else "")
            ),
            **{
                "data-zone": zone_key,
                "data-zone-img": asset_busted(INJECTION_ZONE_IMAGE_BY_KEY[zone_key]),
                "onclick": selector_js,
            },
        )
        for zone_key in INJECTION_ZONE_IMAGE_BY_KEY.keys()
    ]
    refresh_js = "htmx.ajax('GET','/settings/injections',{target:'#main_content',swap:'innerHTML'});"
    return Div(
        Div(
            P("Insulin injection", cls="text-lg font-semibold"),
            Form(
                Input(type="hidden", name="injection_id", value=str(injection_id)),
                Div(
                    Div(
                        Label("Type", cls="text-xs text-gray-600"),
                        Select(
                            Option("Rapid", value="rapid", selected=insulin_type != "basal"),
                            Option("Basal", value="basal", selected=insulin_type == "basal"),
                            name="insulin_type",
                            cls="web_input border border-white rounded-lg px-2 py-1 text-base",
                            data_settings_insulin_type="true",
                            onchange=switch_type_js,
                        ),
                        cls="flex flex-col gap-1 flex-1 min-w-0",
                    ),
                    Div(
                        Label("Injection hour", cls="text-xs text-gray-600"),
                        Div(
                            Input(
                                type="time",
                                name="shot_hour",
                                value=shot_hour,
                                aria_label="Injection hour",
                                cls="web_input border border-white rounded-lg px-2 py-1 text-base",
                            ),
                            Button(
                                "Date",
                                type="button",
                                cls="web_button px-2 py-1 text-xs",
                                onclick=(
                                    f"const el=document.getElementById('settings_shot_date_wrap_{injection_id}');"
                                    "if(el){el.classList.toggle('hidden');}"
                                ),
                            ),
                            cls="flex items-center gap-2",
                        ),
                        Div(
                            Label("Injection date", cls="text-xs text-gray-600"),
                            Input(
                                type="date",
                                name="shot_date",
                                value=shot_date,
                                aria_label="Injection date",
                                cls="web_input border border-white rounded-lg px-2 py-1 text-base",
                            ),
                            id=f"settings_shot_date_wrap_{injection_id}",
                            cls="hidden flex-col gap-1 mt-1",
                        ),
                        cls="flex flex-col gap-1 flex-1 min-w-0",
                    ),
                    cls="grid grid-cols-2 gap-3",
                ),
                Div(
                    Label("Basal dose", cls="text-xs text-gray-600"),
                    Input(
                        type="number",
                        name="basal_units",
                        step="0.5",
                        min="0.5",
                        inputmode="decimal",
                        pattern="[0-9]+([\\.,][0-9]+)?",
                        placeholder="e.g. 8.5",
                        value=(f"{float(basal_units):g}" if basal_units is not None else ""),
                        cls="web_input border border-white rounded-lg px-2 py-1 text-base",
                    ),
                    data_settings_basal_wrap="true",
                    cls=f"{'hidden ' if insulin_type != 'basal' else ''}flex flex-col gap-1",
                ),
                Div(
                    Img(
                        src=image,
                        alt="Injection zones map",
                        cls="w-full max-h-[38vh] md:max-h-[46vh] object-contain rounded-2xl border border-gray-200 bg-white",
                        data_settings_injection_image="true",
                    ),
                    cls="w-full",
                ),
                Div(*zone_buttons, cls="flex flex-wrap gap-2"),
                Input(type="hidden", name="zone", value=selected_zone, data_settings_injection_zone_input="true"),
                Div(
                    Button(
                        "OK",
                        type="button",
                        cls="web_button px-4 py-2 text-sm text-white ml-auto",
                        style="background-color:#111111;border-color:#111111;",
                        hx_post=f"/settings/injections/{injection_id}/update",
                        hx_include="closest form",
                        hx_swap="none",
                        **{"hx-on:htmx:after-request": refresh_js},
                        onclick=(
                            "const form=this.form;"
                            "const z=form?form.querySelector('[data-settings-injection-zone-input]'):null;"
                            "if(!z||!z.value){alert('Select a zone first.');return false;}"
                            "const t=form?form.querySelector('[data-settings-insulin-type]'):null;"
                            "const b=form?form.querySelector('input[name=basal_units]'):null;"
                            "if(t&&t.value==='basal'&&(!b||!b.value)){alert('Enter basal dose.');return false;}"
                            + _close_modal_js(modal_id)
                        ),
                    ),
                ),
                cls="flex flex-col gap-3",
            ),
            onclick="event.stopPropagation()",
            cls="web_container p-4 md:p-5 rounded-3xl w-72 md:w-[88vw] max-w-md flex flex-col gap-3",
        ),
        id=modal_id,
        onclick=_close_modal_js(modal_id),
        cls="""
            fixed inset-0 z-[70]
            flex items-center justify-center
            bg-slate-800/30 backdrop-blur-lg
            px-4
            opacity-0 invisible pointer-events-none
            transition-opacity duration-200
        """,
    )


def _injection_row(item: dict):
    injection_id = int(item.get("id") or 0)
    if not injection_id:
        return ""
    actions_id = f"settings_injection_actions_{injection_id}"
    insulin_type = str(item.get("insulin_type") or "").strip().lower()
    insulin_label = "Basal" if insulin_type == "basal" else "Rapid"
    zone_key = str(item.get("injection_zone") or "").strip()
    zone_label = INJECTION_ZONE_LABEL_BY_KEY.get(zone_key, zone_key.replace("_", " ").title() or "-")
    local_dt = utc_naive_to_local(item.get("shot_time"))
    hour = _format_injection_hour(local_dt) if local_dt else "--:--"
    basal_units = item.get("basal_units")
    basal_text = ""
    if insulin_type == "basal" and basal_units is not None:
        basal_text = f"Basal units: {float(basal_units):g}u"

    return Div(
        Div(
            Div(
                P(insulin_label, cls="text-sm font-semibold text-gray-900"),
                P(hour, cls="text-xs text-gray-600"),
                cls="flex items-center justify-between gap-3",
            ),
            Div(
                P(f"Zone: {zone_label}", cls="text-xs text-gray-700"),
                P(basal_text, cls=f"text-xs text-gray-700 {'hidden' if not basal_text else ''}"),
                cls="flex items-center justify-between gap-3",
            ),
            onclick=(
                f"const el=document.getElementById('{actions_id}');"
                "if(el){el.classList.toggle('hidden');}"
            ),
            cls="flex flex-col gap-1 cursor-pointer",
        ),
        Div(
            Button(
                "Edit",
                type="button",
                cls="web_button px-3 py-1 text-xs",
                onclick=f"event.stopPropagation();{_open_modal_js(f'settings_injection_edit_{injection_id}')}",
            ),
            Button(
                "Delete",
                type="button",
                cls="web_button px-3 py-1 text-xs text-white",
                style="background-color:#b91c1c;border-color:#b91c1c;",
                onclick=f"event.stopPropagation();{_open_modal_js(f'settings_injection_delete_{injection_id}')}",
            ),
            id=actions_id,
            cls="hidden flex items-center justify-end gap-2 pt-2",
        ),
        cls="web_container food_entry flex flex-col gap-1",
    )


def _injection_row_modals(item: dict):
    return Div(
        _injection_edit_modal(item),
        _injection_delete_modal(item),
    )


def _injection_day_header(day_text: str):
    return P(day_text, cls="text-xs font-semibold uppercase tracking-wide text-gray-600 pt-2")


def injections_settings_chunk(
    rows: list[dict],
    offset: int,
    page_size: int,
    previous_day=None,
):
    if not rows and offset == 0:
        return Div(P("No injections found.", cls="text-sm text-gray-600"), cls="w-full")

    items = []
    modals = []
    current_day = previous_day
    for row in rows:
        local_dt = utc_naive_to_local(row.get("shot_time"))
        if not local_dt:
            continue
        day_value = local_dt.date()
        if current_day != day_value:
            items.append(_injection_day_header(_format_injection_day(local_dt)))
            current_day = day_value
        items.append(_injection_row(row))
        modals.append(_injection_row_modals(row))

    has_more = len(rows) >= page_size
    next_offset = offset + len(rows)
    if has_more:
        items.append(
            Div(
                Button(
                    "Load more",
                    type="button",
                    cls="web_button px-4 py-2 text-sm",
                    hx_get=f"/settings/injections/list?offset={next_offset}",
                    hx_target="#settings-injections-more",
                    hx_swap="outerHTML",
                ),
                id="settings-injections-more",
                cls="w-full flex justify-center pt-2",
            )
        )
    else:
        items.append(Div(id="settings-injections-more", cls="w-full"))

    return Div(
        Div(*items, cls="flex flex-col gap-2 w-full"),
        Div(*modals),
        cls="w-full",
    )


def injections_settings_page(first_chunk):
    return Div(
        Div(
            Button(
                "Back",
                type="button",
                cls="web_button self-start px-3 py-1.5 text-sm",
                hx_get="/settings",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            cls="w-full flex justify-start",
        ),
        H1("Injection log", cls="text-xl font-bold"),
        Div(first_chunk, id="settings-injections-list", cls="w-full"),
        cls="flex flex-col items-center gap-4 md:mt-7 lg:mt-7 mt-2 md:w-md lg:w-md w-xs w-full mx-auto md:mb-28 lg:mb-28 mb-24",
        data_hide_cart="true",
    )
