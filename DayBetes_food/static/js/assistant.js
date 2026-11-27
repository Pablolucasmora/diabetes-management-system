// Assistant composer (frontend_conventions.md §9.11). Presentation only: the
// server returns the `/` suggestions and the answers, and re-reads every
// mentioned entry with its visibility rule (code_conventions.md §8.12).
//
// Typing `/` at the start or after a space or line break opens the
// suggestions above the composer; the text after it filters them. ↑ ↓ move,
// Tab or Enter pick, Esc closes, a tap picks. A picked entry replaces
// `/query` with `/Name ` and becomes a pill above the text box. Mentions
// travel as entry_type + entry_id in the hidden `mentions` field.
// Up to four photos, each reduced here before it is sent (§8.12, cost). The composer is
// cleared only after a successful send: on an error the toast explains it and
// the message stays to send again.
// The meal of the chat travels in the bar's hidden `intake_event_id`; the list
// of chats loads the page with each chat's URL (§9.11). Nothing goes to
// browser storage and no field takes the focus on its own.
(function () {
  if (window.__dbAssistantBootstrapped) return;
  window.__dbAssistantBootstrapped = true;

  var DEBOUNCE_MS = 150;
  var MAX_QUERY_LENGTH = 80;
  var TEXTAREA_MAX_PX = 160;
  var CART_CARD_MARGIN_PX = 96; // room for the fixed logo above a cart card
  var PHOTO_MAX_SIDE_PX = 1568; // larger sides are scaled down by the API anyway
  var PHOTO_JPEG_QUALITY = 0.85;

  var mentions = []; // [{type, id, name}]
  var activeSlash = -1; // index of the `/` whose suggestions are open
  var dismissedSlash = -1; // a `/` closed with Esc or with no results
  var lastQuery = null;
  var timer = null;

  function byId(id) {
    return document.getElementById(id);
  }
  function input() {
    return byId("assistant_input");
  }
  function popup() {
    return byId("assistant_mentions_popup");
  }
  function list() {
    return byId("assistant_mentions");
  }
  function options() {
    var el = list();
    return el ? Array.prototype.slice.call(el.querySelectorAll("[role='option']")) : [];
  }
  function isOpen() {
    var p = popup();
    return !!p && !p.hidden;
  }

  // ---- Send button and photo ----

  // The chosen photos live here, not in the file input: the picker can add more
  // one by one, and each is replaced by its reduced copy when that is ready.
  // They are added to the request in htmx:configRequest.
  var photos = []; // [{id, file, url, ready}]
  var nextPhotoId = 1;

  function photoInput() {
    return byId("assistant_photo");
  }

  function photosMax() {
    var form = byId("assistant_composer");
    return parseInt((form && form.getAttribute("data-photos-max")) || "4", 10);
  }

  function hasPhoto() {
    return photos.length > 0;
  }

  function photosPending() {
    return photos.some(function (photo) {
      return !photo.ready;
    });
  }

  function updateSend() {
    var button = byId("assistant_send");
    var el = input();
    if (!button || !el) return;
    button.disabled = !(el.value.trim() || mentions.length || hasPhoto()) || photosPending();
  }

  function renderPhotos() {
    var box = byId("assistant_photos");
    if (!box) return;
    box.textContent = "";
    photos.forEach(function (photo, index) {
      var item = document.createElement("div");
      item.className = "relative h-14 w-14 shrink-0" + (photo.ready ? "" : " opacity-50");
      var img = document.createElement("img");
      img.src = photo.url;
      img.alt = "Photo " + (index + 1);
      img.className = "h-14 w-14 rounded-xl object-cover border border-line";
      var remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "×";
      remove.setAttribute("data-assistant-remove-photo", String(photo.id));
      remove.setAttribute("aria-label", "Remove photo " + (index + 1));
      remove.className =
        "absolute -top-1.5 -right-1.5 h-5 w-5 rounded-full bg-white border border-line " +
        "text-xs leading-none text-gray-600 shadow-sm cursor-pointer";
      item.appendChild(img);
      item.appendChild(remove);
      box.appendChild(item);
    });
  }

  function removePhoto(id) {
    photos = photos.filter(function (photo) {
      if (photo.id === id) URL.revokeObjectURL(photo.url);
      return photo.id !== id;
    });
    renderPhotos();
    updateSend();
  }

  function clearPhotos() {
    photos.forEach(function (photo) {
      URL.revokeObjectURL(photo.url);
    });
    photos = [];
    var el = photoInput();
    if (el) el.value = "";
    renderPhotos();
    updateSend();
  }

  // Scales the photo down and re-encodes it as JPEG, so the form sends the small
  // one. If the browser cannot, it sends the original and the server checks its size.
  function shrinkPhoto(file) {
    if (!window.createImageBitmap) return Promise.resolve(file);
    return createImageBitmap(file)
      .then(function (bitmap) {
        var scale = Math.min(1, PHOTO_MAX_SIDE_PX / Math.max(bitmap.width, bitmap.height));
        var canvas = document.createElement("canvas");
        canvas.width = Math.round(bitmap.width * scale);
        canvas.height = Math.round(bitmap.height * scale);
        canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        return new Promise(function (resolve) {
          canvas.toBlob(resolve, "image/jpeg", PHOTO_JPEG_QUALITY);
        });
      })
      .then(function (blob) {
        return blob ? new File([blob], "photo.jpg", { type: "image/jpeg" }) : file;
      })
      .catch(function () {
        return file;
      });
  }

  function addPhotos(files) {
    var room = photosMax() - photos.length;
    if (files.length > room && window.dbShowAppToast) {
      window.dbShowAppToast("You can attach up to " + photosMax() + " photos.");
    }
    Array.prototype.slice.call(files, 0, Math.max(room, 0)).forEach(function (file) {
      var photo = { id: nextPhotoId++, file: file, url: URL.createObjectURL(file), ready: false };
      photos.push(photo);
      shrinkPhoto(file).then(function (small) {
        photo.file = small;
        photo.ready = true;
        renderPhotos();
        updateSend();
      });
    });
    renderPhotos();
    updateSend();
  }

  function resetComposer() {
    var el = input();
    if (el) el.value = "";
    mentions = [];
    activeSlash = -1;
    dismissedSlash = -1;
    renderChips();
    clearPhotos();
    close();
    autoGrow();
    updateSend();
  }

  // A new turn glides into view; a conversation that is opened or reloaded
  // shows its end at once, with no scrolling down to it (frontend §9.11,
  // user's request of 2026-11-27).
  function scrollToLatest(instant) {
    var thread = byId("assistant_thread");
    var last = thread && thread.lastElementChild;
    while (last && last.tagName === "INPUT") last = last.previousElementSibling;
    if (last) last.scrollIntoView({ block: "start", behavior: instant ? "auto" : "smooth" });
  }

  // ---- Query under the caret ----

  // The `/` that starts a mention already picked is not a query.
  function startsPickedMention(text, slash) {
    return mentions.some(function (m) {
      return text.substr(slash + 1, m.name.length) === m.name;
    });
  }

  // {slash, query} for the `/` before the caret, or null.
  function queryAtCaret() {
    var el = input();
    if (!el || el.selectionStart !== el.selectionEnd) return null;
    var text = el.value;
    var caret = el.selectionStart;
    var slash = text.lastIndexOf("/", caret - 1);
    if (slash < 0) return null;
    var before = slash === 0 ? "" : text.charAt(slash - 1);
    if (slash > 0 && !/\s/.test(before)) return null;
    var query = text.slice(slash + 1, caret);
    if (query.indexOf("\n") >= 0 || query.length > MAX_QUERY_LENGTH) return null;
    if (startsPickedMention(text, slash)) return null;
    return { slash: slash, query: query };
  }

  // ---- Popup ----

  function open(slash) {
    var p = popup();
    if (!p) return;
    activeSlash = slash;
    p.hidden = false;
  }

  function close() {
    var p = popup();
    if (p) p.hidden = true;
    activeSlash = -1;
    lastQuery = null;
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function fetchSuggestions(query) {
    if (query === lastQuery || !window.htmx) return;
    lastQuery = query;
    // The list carries hx-sync="this:replace": a newer request aborts the
    // previous one, so a late answer never paints over a newer query.
    window.htmx.ajax("GET", "/assistant/mentions?q=" + encodeURIComponent(query), {
      source: list(),
      target: "#assistant_mentions",
      swap: "innerHTML",
    });
  }

  function refresh() {
    var found = queryAtCaret();
    if (!found || found.slash === dismissedSlash) {
      if (isOpen()) close();
      return;
    }
    if (!isOpen()) open(found.slash);
    activeSlash = found.slash;
    if (timer) clearTimeout(timer);
    timer = setTimeout(function () {
      timer = null;
      fetchSuggestions(found.query);
    }, DEBOUNCE_MS);
  }

  function selectedIndex() {
    var opts = options();
    for (var i = 0; i < opts.length; i += 1) {
      if (opts[i].getAttribute("aria-selected") === "true") return i;
    }
    return -1;
  }

  function select(index) {
    var opts = options();
    if (!opts.length) return;
    var next = (index + opts.length) % opts.length;
    opts.forEach(function (opt, i) {
      opt.setAttribute("aria-selected", i === next ? "true" : "false");
    });
    opts[next].scrollIntoView({ block: "nearest" });
    var el = input();
    if (el) el.setAttribute("aria-activedescendant", opts[next].id);
  }

  // ---- Mentions ----

  function syncHidden() {
    var hidden = byId("assistant_mentions_value");
    if (hidden) {
      hidden.value = JSON.stringify(
        mentions.map(function (m) {
          return { entry_type: m.type, entry_id: m.id };
        })
      );
    }
  }

  function renderChips() {
    var box = byId("assistant_mention_chips");
    if (!box) return;
    box.textContent = "";
    mentions.forEach(function (m, i) {
      var chip = document.createElement("span");
      chip.className =
        "inline-flex items-center gap-1 rounded-full bg-control border border-line pl-2.5 pr-1 py-0.5 text-xs text-gray-800 max-w-full";
      var label = document.createElement("span");
      label.className = "truncate";
      label.textContent = m.name;
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "shrink-0 h-5 w-5 rounded-full text-gray-500 hover:bg-line-soft cursor-pointer";
      remove.setAttribute("aria-label", "Remove " + m.name);
      remove.setAttribute("data-assistant-remove-mention", String(i));
      remove.textContent = "×";
      chip.appendChild(label);
      chip.appendChild(remove);
      box.appendChild(chip);
    });
    syncHidden();
    updateSend();
  }

  function autoGrow() {
    var el = input();
    if (!el) return;
    el.style.height = "auto";
    // scrollHeight leaves out the border, which border-box sizing counts.
    var border = el.offsetHeight - el.clientHeight;
    el.style.height = Math.min(el.scrollHeight + border, TEXTAREA_MAX_PX) + "px";
  }

  function pick(option) {
    var el = input();
    if (!el || !option || activeSlash < 0) return;
    var name = option.getAttribute("data-mention-name") || "";
    var type = option.getAttribute("data-mention-type");
    var id = parseInt(option.getAttribute("data-mention-id"), 10);
    if (!name || !type || !id) return;
    var caret = el.selectionStart;
    var text = el.value;
    var inserted = "/" + name + " ";
    el.value = text.slice(0, activeSlash) + inserted + text.slice(caret);
    var position = activeSlash + inserted.length;
    el.setSelectionRange(position, position);
    var exists = mentions.some(function (m) {
      return m.type === type && m.id === id;
    });
    if (!exists) mentions.push({ type: type, id: id, name: name });
    close();
    renderChips();
    autoGrow();
  }

  // Deleting a `/Name` from the text drops its mention.
  function dropMissingMentions() {
    var el = input();
    if (!el) return;
    var before = mentions.length;
    mentions = mentions.filter(function (m) {
      return el.value.indexOf("/" + m.name) >= 0;
    });
    if (mentions.length !== before) renderChips();
  }

  function removeMention(index) {
    var m = mentions[index];
    var el = input();
    if (!m || !el) return;
    var token = "/" + m.name;
    var at = el.value.indexOf(token);
    if (at >= 0) {
      var end = at + token.length;
      if (el.value.charAt(end) === " ") end += 1;
      el.value = el.value.slice(0, at) + el.value.slice(end);
    }
    mentions.splice(index, 1);
    renderChips();
    autoGrow();
  }

  // ---- Events ----

  document.addEventListener("input", function (event) {
    if (event.target !== input()) return;
    // A `/` that was dismissed stops counting once it is deleted.
    var el = input();
    if (dismissedSlash >= 0 && el.value.charAt(dismissedSlash) !== "/") dismissedSlash = -1;
    dropMissingMentions();
    autoGrow();
    updateSend();
    refresh();
  });

  document.addEventListener("change", function (event) {
    if (event.target !== photoInput()) return;
    if (event.target.files && event.target.files.length) addPhotos(event.target.files);
    // Emptied so that choosing the same photo again fires `change`.
    event.target.value = "";
  });

  // Sending (§9.11): the button, or Enter on a computer; Shift+Enter is a line
  // break there, and on a phone Enter is always a line break. A send while a
  // photo is being prepared waits for it.
  var POINTER_FINE = window.matchMedia ? window.matchMedia("(hover: hover) and (pointer: fine)") : null;

  document.addEventListener("keydown", function (event) {
    if (event.target !== input() || event.key !== "Enter") return;
    if (event.shiftKey || event.isComposing || !(POINTER_FINE && POINTER_FINE.matches)) return;
    // With the `/` list open, Enter picks a food (handled below).
    if (isOpen() && options().length) return;
    event.preventDefault();
    var send = byId("assistant_send");
    var form = byId("assistant_composer");
    if (send && !send.disabled && form) form.requestSubmit(send);
  });

  // The message shows in the chat as soon as it is sent (§9.11), and the box
  // empties; on a failed send it goes back to the box to send again.
  var sentDraft = null;

  function pendingBubble(text, photoCount) {
    var bubble = document.createElement("div");
    bubble.setAttribute("data-pending-turn", "true");
    bubble.className =
      "self-end max-w-[85%] rounded-2xl rounded-br-md bg-control border border-line px-3 py-2 flex flex-col gap-1 db_pending_turn";
    if (photoCount) {
      var pill = document.createElement("span");
      pill.className = "inline-block text-[11px] rounded-full bg-white/70 border border-line px-2 py-0.5 w-fit";
      pill.textContent = photoCount === 1 ? "Photo" : photoCount + " photos";
      bubble.appendChild(pill);
    }
    if (text) {
      var p = document.createElement("p");
      p.className = "text-sm whitespace-pre-wrap break-words";
      p.textContent = text;
      bubble.appendChild(p);
    }
    return bubble;
  }

  function removePendingBubble() {
    var pending = document.querySelector("[data-pending-turn]");
    if (pending) pending.remove();
  }

  document.addEventListener("htmx:beforeRequest", function (event) {
    var form = byId("assistant_composer");
    if (!form || event.detail.elt !== form) return;
    if (photosPending()) {
      event.preventDefault();
      return;
    }
    close();
    syncHidden();
    setThinkingFailed(false);
    // The request already holds the text and the mentions (htmx:configRequest
    // runs first), so the box can empty now.
    var el = input();
    sentDraft = { text: el ? el.value : "", mentions: mentions.slice() };
    var thread = byId("assistant_thread");
    if (thread) {
      removePendingBubble();
      var intro = thread.querySelector("[data-intro]");
      if (intro) intro.remove();
      thread.appendChild(pendingBubble(sentDraft.text.trim(), photos.length));
      scrollToLatest();
    }
    if (el) el.value = "";
    mentions = [];
    renderChips();
    autoGrow();
    Array.prototype.forEach.call(document.querySelectorAll("[data-quick-replies], [data-usual-row]"), function (row) {
      row.remove();
    });
  });

  // Quick answers (§9.11): a tap sends the option as the user's message. They
  // belong to the latest question only, so any send takes them away.
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-quick-reply]");
    if (!button) return;
    var el = input();
    var form = byId("assistant_composer");
    var send = byId("assistant_send");
    if (!el || !form || !send) return;
    el.value = button.getAttribute("data-quick-reply");
    updateSend();
    if (!send.disabled) form.requestSubmit(send);
  });

  // "Usual now" (§9.11): a tap writes `/Name 150 g` as a mention, at the end of
  // the box, so several can go in one message.
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-usual-id]");
    if (!button) return;
    var el = input();
    if (!el) return;
    var type = button.getAttribute("data-usual-type");
    var id = parseInt(button.getAttribute("data-usual-id"), 10);
    var name = button.getAttribute("data-usual-name") || "";
    var grams = button.getAttribute("data-usual-grams") || "";
    if (!type || !id || !name) return;
    var text = el.value.replace(/\s+$/, "");
    el.value = (text ? text + ", " : "") + "/" + name + " " + grams + " g";
    var exists = mentions.some(function (m) {
      return m.type === type && m.id === id;
    });
    if (!exists) mentions.push({ type: type, id: id, name: name });
    renderChips();
    syncHidden();
    autoGrow();
    updateSend();
  });

  // The answer brings the message again, in its turn: the pending one goes.
  document.addEventListener("htmx:beforeSwap", function (event) {
    var form = byId("assistant_composer");
    // `detail.elt` is the target of this event, so the form is the one that asked.
    var config = event.detail.requestConfig;
    if (form && config && config.elt === form) removePendingBubble();
  });

  // The photos travel as repeated `photo` parts of the multipart body.
  document.addEventListener("htmx:configRequest", function (event) {
    var form = byId("assistant_composer");
    if (!form || event.detail.elt !== form) return;
    var data = event.detail.formData;
    if (!data) return;
    data.delete("photo");
    photos.forEach(function (photo) {
      data.append("photo", photo.file, photo.file.name || "photo.jpg");
    });
  });

  document.addEventListener("htmx:afterRequest", function (event) {
    var form = byId("assistant_composer");
    if (!form || event.detail.elt !== form) return;
    if (event.detail.successful) {
      sentDraft = null;
      resetComposer();
      // The answer comes later, in its own block: the face turns normal then.
      scrollToLatest();
      return;
    }
    setThinkingFailed(true);
    removePendingBubble();
    if (sentDraft) {
      var el = input();
      if (el && !el.value) el.value = sentDraft.text;
      if (!mentions.length) mentions = sentDraft.mentions;
      sentDraft = null;
      renderChips();
      syncHidden();
      autoGrow();
      updateSend();
    }
    // A failed send may have done part of its work before failing (the rounds
    // already stored, code_conventions.md §8.12): reload the conversation so
    // what reached the cart shows before the message is sent again.
    reloadThread();
  });

  // ---- DiaBot's avatar (§9.11) ----

  // A failed send keeps the thinking row with the confused face until the next send.
  function setThinkingFailed(failed) {
    var row = byId("assistant_thinking");
    if (!row) return;
    row.classList.toggle("db_failed", failed);
    var avatar = row.querySelector("[data-avatar]");
    if (avatar) avatar.setAttribute("data-avatar", failed ? "confused" : "thinking");
  }

  // The new turn's avatar starts on the thinking face and turns normal, so the
  // face changes in place of the thinking row instead of jumping.
  function arriveNormal() {
    var thread = byId("assistant_thread");
    var avatars = thread ? thread.querySelectorAll("[data-avatar]") : [];
    var avatar = avatars[avatars.length - 1];
    if (!avatar) return;
    avatar.setAttribute("data-avatar", "thinking");
    void avatar.offsetWidth;
    requestAnimationFrame(function () {
      avatar.setAttribute("data-avatar", "normal");
    });
  }
  // A message answered in the background (code_conventions.md §8.12): its block
  // asks every 2 s and is replaced by the answer, or by the failed block.
  document.addEventListener("htmx:afterRequest", function (event) {
    var elt = event.detail && event.detail.elt;
    if (!elt || !elt.id || elt.id.indexOf("assistant_turn_") !== 0) return;
    if (event.detail.xhr && event.detail.xhr.status === 200) {
      setTimeout(function () {
        scrollToLatest();
        arriveNormal();
      }, 0);
    }
  });

  // A failed message stored nothing: its text goes back to an empty composer
  // to send it again (the photos do not: they are attached again).
  function restoreFailedText(root) {
    if (!root || !root.querySelectorAll) return;
    var failed = root.matches && root.matches("[data-assistant-failed-text]")
      ? [root]
      : Array.prototype.slice.call(root.querySelectorAll("[data-assistant-failed-text]"));
    var el = input();
    if (!failed.length || !el || el.value.trim()) return;
    el.value = failed[failed.length - 1].getAttribute("data-assistant-failed-text") || "";
    autoGrow();
    updateSend();
  }

  document.addEventListener("htmx:load", function (event) {
    restoreFailedText(event.detail && event.detail.elt);
  });

  function reloadThread() {
    var conversation = byId("assistant_conversation_id");
    var select = mealSelect();
    var params = new URLSearchParams();
    if (conversation && conversation.value) params.set("conversation_id", conversation.value);
    else if (select) params.set("intake_event_id", select.value);
    if (!window.htmx) return;
    window.htmx.ajax("GET", "/assistant/thread?" + params.toString(), {
      target: "#assistant_thread_box",
      swap: "innerHTML",
    });
  }

  // The meal of the chat (§9.11): the bar's hidden field, a meal id, `none` or empty.
  function mealSelect() {
    return byId("assistant_meal");
  }

  // The cart opens at the top of the chosen meal's card, so its time and name
  // show (frontend_conventions.md §5, user's request of 2026-11-15). Without a
  // meal (`New meal`, `No meal`), or if the card is not there, at the top.
  window.dbOpenCartFromAssistant = function () {
    window.scrollTo({ top: 0, behavior: "auto" });
    var select = mealSelect();
    var eventId = select && /^[0-9]+$/.test(select.value) ? select.value : null;
    if (!eventId) return;
    document.body.addEventListener(
      "htmx:afterSettle",
      function onSettle(event) {
        if (!event.detail.target || event.detail.target.id !== "main_content") return;
        document.body.removeEventListener("htmx:afterSettle", onSettle);
        var card = byId("cart_card_event_" + eventId);
        if (!card) return;
        // Below the fixed logo at the top of the page.
        var top = card.getBoundingClientRect().top + window.scrollY - CART_CARD_MARGIN_PX;
        window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
      }
    );
  };

  // A reloaded conversation shows its end.
  document.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail && event.detail.target && event.detail.target.id === "assistant_thread_box") scrollToLatest(true);
  });

  document.addEventListener("keydown", function (event) {
    if (event.target !== input() || !isOpen()) return;
    var opts = options();
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!opts.length) return;
      event.preventDefault();
      select(selectedIndex() + (event.key === "ArrowDown" ? 1 : -1));
    } else if (event.key === "Tab" || event.key === "Enter") {
      if (!opts.length) return;
      event.preventDefault();
      pick(opts[Math.max(0, selectedIndex())]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      dismissedSlash = activeSlash;
      close();
    }
  });

  // Moving the caret out of the query (arrows, a tap elsewhere) closes it.
  document.addEventListener("selectionchange", function () {
    if (document.activeElement === input()) refresh();
  });

  document.addEventListener("click", function (event) {
    var option = event.target.closest && event.target.closest("#assistant_mentions [role='option']");
    if (option) {
      event.preventDefault();
      pick(option);
      var el = input();
      if (el) el.focus();
      return;
    }
    // A card that asks the assistant something on a tap (Save as recipe, §9.11).
    var promptButton = event.target.closest && event.target.closest("[data-assistant-prompt]");
    if (promptButton) {
      var field = input();
      var form = byId("assistant_composer");
      if (!field || !form) return;
      field.value = promptButton.getAttribute("data-assistant-prompt");
      autoGrow();
      updateSend();
      promptButton.disabled = true;
      form.requestSubmit();
      return;
    }
    var removePhotoButton = event.target.closest && event.target.closest("[data-assistant-remove-photo]");
    if (removePhotoButton) {
      removePhoto(parseInt(removePhotoButton.getAttribute("data-assistant-remove-photo"), 10));
      return;
    }
    var remove = event.target.closest && event.target.closest("[data-assistant-remove-mention]");
    if (remove) {
      removeMention(parseInt(remove.getAttribute("data-assistant-remove-mention"), 10));
      return;
    }
    // A tap outside the composer closes the suggestions.
    if (isOpen() && !(event.target.closest && event.target.closest("#assistant_composer"))) close();
  });

  // Keep the focus in the text box when a row is pressed, so the phone
  // keyboard does not close and reopen.
  // The same for a +1 chip and its menu: the keyboard closing mid-press moved the
  // composer under the finger.
  document.addEventListener("mousedown", function (event) {
    if (event.target.closest && event.target.closest("#assistant_mentions [role='option'], [data-plus-url], #assistant_plus_menu")) event.preventDefault();
  });

  // After a query with a space stops matching, the `/` stays as plain text.
  document.addEventListener("htmx:afterSwap", function (event) {
    if (!event.detail || event.detail.target !== list()) return;
    var empty = !!list().querySelector("[data-mentions-empty='true']");
    var found = queryAtCaret();
    if (empty && found && /\s/.test(found.query)) {
      dismissedSlash = found.slash;
      close();
      return;
    }
    var el = input();
    var first = options()[0];
    if (el) {
      if (first) el.setAttribute("aria-activedescendant", first.id);
      else el.removeAttribute("aria-activedescendant");
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    restoreFailedText(document);
    autoGrow();
    updateSend();
    scrollToLatest(true);
  });

  // A preloaded page (frontend §12, §13) drew turns without marking them seen:
  // it does so now that it is shown (code_conventions.md §9.2).
  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-cookie-name"]');
    var name = ((meta && meta.content) || "daybetes_csrf") + "=";
    var cookies = document.cookie ? document.cookie.split(";") : [];
    for (var i = 0; i < cookies.length; i += 1) {
      var cookie = cookies[i].trim();
      if (cookie.indexOf(name) === 0) return decodeURIComponent(cookie.slice(name.length));
    }
    return "";
  }

  function markShownSeen(root) {
    if (!root || !root.querySelectorAll) return;
    var pages = root.matches && root.matches("[data-mark-seen]") ? [root] : root.querySelectorAll("[data-mark-seen]");
    for (var i = 0; i < pages.length; i += 1) {
      var page = pages[i];
      if (!document.body.contains(page) || page.closest(".db_swipe_ghost")) continue;
      var ids = (page.getAttribute("data-mark-seen") || "").split(",");
      page.removeAttribute("data-mark-seen");
      for (var j = 0; j < ids.length; j += 1) {
        if (!/^[0-9]+$/.test(ids[j])) continue;
        fetch("/assistant/turn/" + ids[j] + "/seen", {
          method: "POST",
          credentials: "same-origin",
          headers: { "HX-Request": "true", "X-CSRF-Token": csrfToken() },
        }).catch(function () {});
      }
    }
  }

  // A new page of the assistant starts with no mentions.
  document.addEventListener("htmx:load", function (event) {
    markShownSeen(event.detail && event.detail.elt);
    if (event.detail && event.detail.elt && event.detail.elt.querySelector && event.detail.elt.querySelector("#assistant_input")) {
      mentions = [];
      activeSlash = -1;
      dismissedSlash = -1;
      lastQuery = null;
      mealExpanded = false;
      autoGrow();
      updateSend();
      scrollToLatest(true);
    }
  });

  // ---- The meal's foods (§9.11) ----
  // Folded into one line as soon as they take more than their share of the chat's
  // height (data-meal-fold), with two foods or more; opened only while the user
  // wants, also across the bar's swaps after each message.
  var mealExpanded = false;

  function fitMealFoods() {
    var details = document.querySelector("[data-meal-fold]");
    if (!details) return;
    var rows = details.querySelector("[data-meal-rows]");
    if (!rows) return;
    var share = parseFloat(details.getAttribute("data-meal-fold")) || 0.1;
    // Measuring it unfolded loses the scroll of the box.
    var scroll = mealScroll();
    details.removeAttribute("data-foldable");
    details.open = true;
    var count = parseInt(rows.getAttribute("data-meal-count"), 10) || 0;
    var foldable = count > 1 && rows.offsetHeight > window.innerHeight * share;
    if (foldable) details.setAttribute("data-foldable", "");
    details.open = !foldable || mealExpanded;
    setMealScroll(scroll);
  }

  // A repaint of the bar keeps where its foods were scrolled to and which plates
  // were open (frontend_conventions.md §7.11).
  var MEAL_BAR_ID = "assistant_meal_bar";
  var mealView = null;

  function mealScroll() {
    var box = document.querySelector("[data-meal-scroll]");
    return box ? box.scrollTop : 0;
  }

  function setMealScroll(top) {
    var box = document.querySelector("[data-meal-scroll]");
    if (box) box.scrollTop = top;
  }

  function mealPlates() {
    return Array.prototype.slice.call(document.querySelectorAll("[data-meal-rows] details"));
  }

  function keepMealView(event) {
    var target = event.detail && event.detail.target;
    if (!target || target.id !== MEAL_BAR_ID) return;
    mealView = {
      meal: mealSelect() ? mealSelect().value : "",
      scroll: mealScroll(),
      plates: mealPlates().map(function (plate) { return plate.open; }),
    };
  }

  function restoreMealView() {
    var view = mealView;
    // Another meal's bar starts as it comes.
    if (!view || !mealSelect() || mealSelect().value !== view.meal) return;
    var plates = mealPlates();
    if (plates.length === view.plates.length) {
      plates.forEach(function (plate, index) { plate.open = view.plates[index]; });
    }
    fitMealFoods();
    setMealScroll(view.scroll);
  }

  document.addEventListener("htmx:beforeSwap", keepMealView);
  document.addEventListener("htmx:oobBeforeSwap", keepMealView);
  document.addEventListener("htmx:afterSwap", restoreMealView);
  document.addEventListener("htmx:oobAfterSwap", restoreMealView);

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest && event.target.closest("[data-meal-fold-toggle]");
    if (!toggle) return;
    var details = toggle.closest("[data-meal-fold]");
    if (details) mealExpanded = !details.open;
  });

  document.addEventListener("htmx:afterSettle", function () {
    fitMealFoods();
    restoreMealView();
    mealView = null;
  });
  document.addEventListener("DOMContentLoaded", fitMealFoods);
  window.addEventListener("resize", function () {
    clearTimeout(fitMealFoods.timer);
    fitMealFoods.timer = setTimeout(fitMealFoods, 150);
  });

  // ---- +1 buttons (§9.11) ----
  // A tap adds one more at once, without the assistant. Held 500 ms (as a Food
  // row, §9.3.1), a small menu offers +½, +2 and −1 (−1 only with more than one).

  var PLUS_HOLD_MS = 500;
  var plusTimer = null;
  var plusHeld = false;
  // One +1 at a time, in order: htmx keeps only the last of several requests of one
  // element, so quick taps on different chips would lose the ones in between.
  var plusQueue = Promise.resolve();

  function plusRow() {
    return byId("assistant_plus_row");
  }

  function sendPlus(chip, step) {
    var row = plusRow();
    if (!chip || !row || !window.htmx) return;
    closePlusMenu();
    chip.disabled = true;
    var url = chip.getAttribute("data-plus-url");
    var values = { step: String(step), conversation_id: row.getAttribute("data-conversation-id") || "" };
    function enable() {
      chip.disabled = false;
    }
    plusQueue = plusQueue.then(function () {
      // Each answer replaces the row, so the row is looked up when its turn comes.
      var current = plusRow();
      if (!current || current.getAttribute("data-conversation-id") !== row.getAttribute("data-conversation-id")) return;
      return window.htmx.ajax("POST", url, {
        source: current,
        target: current,
        swap: "outerHTML",
        values: values,
      });
    }).then(enable, enable);
  }

  function closePlusMenu() {
    var menu = byId("assistant_plus_menu");
    if (menu) menu.remove();
  }

  function openPlusMenu(chip) {
    closePlusMenu();
    var count = parseFloat(chip.getAttribute("data-plus-count") || "0");
    var menu = document.createElement("div");
    menu.id = "assistant_plus_menu";
    menu.setAttribute("role", "menu");
    menu.className = "absolute bottom-full mb-2 z-50 flex gap-1 rounded-2xl bg-white border border-line shadow-lg p-1";
    [["+½", 0.5], ["+2", 2], ["−1", -1]].forEach(function (pair) {
      if (pair[1] < 0 && count <= 1) return;
      var item = document.createElement("button");
      item.type = "button";
      item.setAttribute("role", "menuitem");
      item.className = "web_button rounded-full px-3 py-1.5 text-xs";
      item.textContent = pair[0];
      item.addEventListener("click", function (event) {
        event.stopPropagation();
        sendPlus(chip, pair[1]);
      });
      menu.appendChild(item);
    });
    // The wrapper is sticky, which already places the menu: setting it relative
    // unstuck the composer and made it jump up.
    var wrapper = plusRow() && plusRow().parentElement;
    if (!wrapper) return;
    wrapper.appendChild(menu);
    var left = chip.getBoundingClientRect().left - wrapper.getBoundingClientRect().left;
    var maxLeft = wrapper.clientWidth - menu.offsetWidth;
    menu.style.left = Math.max(0, Math.min(left, maxLeft)) + "px";
    if (navigator.vibrate) navigator.vibrate(10);
  }

  document.addEventListener("pointerdown", function (event) {
    var chip = event.target.closest && event.target.closest("[data-plus-url]");
    if (!chip) return;
    plusHeld = false;
    clearTimeout(plusTimer);
    plusTimer = setTimeout(function () {
      plusHeld = true;
      openPlusMenu(chip);
    }, PLUS_HOLD_MS);
  });

  ["pointerup", "pointercancel", "pointerleave"].forEach(function (name) {
    document.addEventListener(name, function () {
      clearTimeout(plusTimer);
    }, true);
  });

  document.addEventListener("click", function (event) {
    var chip = event.target.closest && event.target.closest("[data-plus-url]");
    if (!chip) {
      if (!(event.target.closest && event.target.closest("#assistant_plus_menu"))) closePlusMenu();
      return;
    }
    event.preventDefault();
    if (plusHeld) {
      plusHeld = false;
      return;
    }
    sendPlus(chip, 1);
  });

  // Holding a chip selects no text and opens no iOS callout.
  document.addEventListener("contextmenu", function (event) {
    if (event.target.closest && event.target.closest("[data-plus-url]")) event.preventDefault();
  });
})();
