from fasthtml.common import *
from DayBetes_food.database.queries.crud import get_all_tags


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
