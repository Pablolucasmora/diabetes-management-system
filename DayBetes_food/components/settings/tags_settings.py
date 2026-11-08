"""Settings `Tags` (frontend_conventions.md §9.10).

The system tags are listed first and cannot be changed. The user's own tags can
be renamed, recolored and deleted, and new ones created. The search ignores case
and accents. Every action answers with what is stored, read by id (§6).
"""

from fasthtml.common import *

from DayBetes_food.components.food.tags import tag_pill_style
from DayBetes_food.components.modal import ConfirmActionModal, close_modal_js, modal_confirm_button, open_modal_js
from DayBetes_food.components.navigation import back_js
from DayBetes_food.domain.tag import TAG_NAME_MAX_LENGTH, TagRead

TAGS_LIST_ID = "settings-tags-list"
_PICKR_VERSION = "1.9.1"
_ROW_CLS = "web_container food_entry flex items-center justify-between gap-3"


def tag_settings_row(tag: TagRead):
    if tag.is_system:
        return Div(
            Span(tag.name, cls="inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold",
                 style=tag_pill_style(tag)),
            Span("System", cls="text-xs text-gray-500"),
            id=f"tag_row_{tag.id}",
            cls=_ROW_CLS,
        )
    delete_id = f"tag_delete_{tag.id}"
    return Form(
        Input(
            name="name",
            value=tag.name,
            maxlength=str(TAG_NAME_MAX_LENGTH),
            required=True,
            aria_label="Tag name",
            cls="web_input bg-transparent border-0 text-base font-semibold blur-none focus:shadow-none focus:scale-100 focus:outline-none w-full min-w-0",
            style="transition:none; transform:none; scale:1; box-shadow:none; outline:none;",
            # Only a real change is saved, not every blur.
            hx_post=f"/settings/tags/{tag.id}/update",
            hx_trigger="change",
            hx_target=f"#tag_row_{tag.id}",
            hx_swap="outerHTML",
            hx_include="closest form",
        ),
        Div(
            Input(type="hidden", name="color", value=tag.color, data_tag_color_value="true"),
            Button(
                "",
                type="button",
                data_tag_color_trigger="true",
                data_tag_color_preview="true",
                cls="block w-8 h-8 rounded-lg border border-gray-300 shrink-0 p-0 cursor-pointer",
                style=f"background:{tag.color};min-width:2rem;min-height:2rem;",
                title="Edit color",
                aria_label="Edit color",
            ),
            Button(
                "Delete",
                type="button",
                cls="web_button px-3 py-1 text-xs text-danger",
                onclick=open_modal_js(delete_id),
            ),
            cls="flex items-center justify-end gap-2",
        ),
        ConfirmActionModal(
            modal_id=delete_id,
            title="Delete tag",
            question=f"Delete {tag.name}? It is taken off every food that has it.",
            yes_button=modal_confirm_button(
                "Delete",
                danger=True,
                hx_post=f"/settings/tags/{tag.id}/delete",
                hx_target=f"#tag_row_{tag.id}",
                hx_swap="delete",
                onclick=close_modal_js(delete_id),
            ),
        ),
        id=f"tag_row_{tag.id}",
        # The color picker submits the form once a color is saved.
        hx_post=f"/settings/tags/{tag.id}/update",
        hx_target=f"#tag_row_{tag.id}",
        hx_swap="outerHTML",
        cls=_ROW_CLS,
    )


def tags_settings_list(tags: list[TagRead], searching: bool = False):
    if not tags:
        return P("No tags match that search." if searching else "No tags yet.", cls="text-sm text-gray-600")
    return Div(*(tag_settings_row(tag) for tag in tags), cls="flex flex-col gap-2 w-full")


def tags_settings_page(tags: list[TagRead]):
    return Div(
        Div(
            Button("Back", type="button", cls="web_button self-start px-3 py-1.5 text-sm", onclick=back_js("/settings")),
            cls="w-full flex justify-start",
        ),
        H1("Tags", cls="text-xl font-bold"),
        Form(
            Input(
                name="name",
                type="text",
                placeholder="New tag",
                aria_label="New tag",
                autocomplete="off",
                maxlength=str(TAG_NAME_MAX_LENGTH),
                required=True,
                cls="web_input min-w-0 flex-1 rounded-2xl border border-white px-4 py-2",
            ),
            Button("Add", type="submit", cls="web_button px-4 py-2 text-sm"),
            hx_post="/settings/tags",
            hx_target=f"#{TAGS_LIST_ID}",
            hx_swap="innerHTML",
            # The list comes back whole; the field is emptied for the next one.
            **{"hx-on::after-request": "if(event.detail.successful){this.reset();}"},
            cls="flex items-center gap-2 w-full",
        ),
        Input(
            type="search",
            id="settings_tags_search",
            name="q",
            placeholder="Search tag by name",
            autocomplete="off",
            cls="web_input rounded-2xl bg-gray-200/50 border-[0.6px] border-white p-4 w-full",
            hx_get="/settings/tags/list",
            hx_trigger="input changed delay:300ms, search",
            hx_target=f"#{TAGS_LIST_ID}",
            hx_swap="innerHTML",
        ),
        Div(tags_settings_list(tags), id=TAGS_LIST_ID, cls="w-full"),
        Link(rel="stylesheet", href=f"https://cdn.jsdelivr.net/npm/@simonwep/pickr@{_PICKR_VERSION}/dist/themes/classic.min.css"),
        Script(src=f"https://cdn.jsdelivr.net/npm/@simonwep/pickr@{_PICKR_VERSION}/dist/pickr.min.js"),
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
                  // #RRGGBB only: the server accepts no alpha (ck_tags_color).
                  var hex = color ? color.toHEXA().toString().slice(0, 7) : "";
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
