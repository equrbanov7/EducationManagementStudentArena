/* =========================================================================
   «İmtahan zalları» — dialoq/çekmecə formalarının AJAX göndərişi (2026-10-21).

   SAHİB ŞİKAYƏTİ: «Kompüter əlavə edərkən səhv edəndə səhvi göstərmir, yazdığım
   tabdan atır — deyirsə yer var, modalda göstərsin, bütöv atır.» Əvvəl formalar
   adi POST idi: xətada server redirect edirdi → səhifə yenidən yüklənir, dialoq
   bağlanır, yazılanlar itir, zalın çekmecəsi də açılmırdı (yalnız tost qalırdı).

   İNDİ (`form[data-sar-ajax]`):
   * göndərişdən əvvəl HTML5 yoxlaması — xəta SAHƏNİN YANINDA + dialoqun başında;
   * `EMSCore.fetchJSON` (X-Requested-With + CSRF) → server JSON
     `{ok, message, errors: {sahə: mesaj}}` qaytarır:
       - 400 → dialoq AÇIQ qalır, yazılanlar toxunulmur, hər xəta öz sahəsinin
         yanında (`aria-invalid` + `aria-describedby`), xülasə dialoqun başında;
         dialoqsuz forma (çekmecədəki sil/status) → xəta tostu;
       - 200 → dialoq bağlanır, bölmə fraqmenti alınıb KPI/siyahı və çekmecələrin
         gövdəsi YERİNDƏ əvəzlənir (açıq çekmecə açıq qalır, sürüşmə yeri qorunur),
         uğur tostu; toplu əlavənin qismən uğurunda dialoq yalnız uğursuz sətirlərlə
         açıq qalır;
   * JS-siz/adi POST xətasında server vəziyyəti sessiyaya yazır, bölmə onu
     `#sar-form-state` JSON blokunda qaytarır → burada dialoq yenidən açılır,
     dəyərlər və xətalar bərpa olunur.

   Mətnlər `[data-sar-root]`-un `data-sar-msg-*` atributlarındandır (Django
   kataloqu). AJAX-SAFE: yalnız `EMSDelegate` + `EMSReady`; idempotent.
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSExamRoomsAjax) {
        return;
    }

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE || !window.EMSReady) {
        return;
    }

    var SECTION = "superadmin-exam-rooms";

    function root() {
        return document.querySelector("[data-sar-root]");
    }

    function text(attr) {
        var host = root();
        return (host && host.getAttribute(attr)) || "";
    }

    function toast(message, kind) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, kind || "info");
        }
    }

    function each(list, fn) {
        for (var i = 0; i < list.length; i += 1) {
            fn(list[i], i);
        }
    }

    /* ---- Xətalar: sahənin yanında + dialoqun başında --------------------- */

    function clearErrors(form) {
        if (!form) {
            return;
        }
        each(form.querySelectorAll("[data-sar-field-error], [data-sar-error-list]"), function (node) {
            node.parentNode.removeChild(node);
        });
        each(form.querySelectorAll("[data-sar-described]"), function (el) {
            var id = el.getAttribute("data-sar-described");
            var rest = (el.getAttribute("aria-describedby") || "").split(/\s+/).filter(function (part) {
                return part && part !== id;
            });
            if (rest.length) {
                el.setAttribute("aria-describedby", rest.join(" "));
            } else {
                el.removeAttribute("aria-describedby");
            }
            el.removeAttribute("data-sar-described");
        });
        each(form.querySelectorAll('[aria-invalid="true"]'), function (el) {
            el.removeAttribute("aria-invalid");
        });
        var box = form.querySelector("[data-ems-form-error]");
        if (box) {
            box.textContent = "";
            box.hidden = true;
        }
    }

    function fieldFor(form, name) {
        if (!name || name === "__all__") {
            return null;
        }
        var nodes = form.querySelectorAll("[name]");
        for (var i = 0; i < nodes.length; i += 1) {
            if (nodes[i].name === name && nodes[i].type !== "hidden") {
                return nodes[i];
            }
        }
        return null;
    }

    function markField(el, name, message) {
        var id = (el.id || "sar-field-" + name) + "-error";
        var note = document.createElement("p");
        note.className = "ems-msg ems-msg--error sar-field-error";
        note.id = id;
        note.setAttribute("data-sar-field-error", name);
        note.textContent = String(message);
        (el.closest(".ems-field") || el.parentNode).appendChild(note);
        el.setAttribute("aria-invalid", "true");
        var described = (el.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
        described.push(id);
        el.setAttribute("aria-describedby", described.join(" "));
        el.setAttribute("data-sar-described", id);
    }

    /** Server/kliyent xətalarını formaya çəkir; birinci səhv sahəni qaytarır. */
    function showErrors(form, payload) {
        clearErrors(form);
        var errors = (payload && payload.errors) || {};
        var first = null;
        Object.keys(errors).forEach(function (name) {
            var el = fieldFor(form, name);
            if (el && errors[name]) {
                markField(el, name, errors[name]);
                first = first || el;
            }
        });
        var message = (payload && (payload.summary || payload.message)) || "";
        var box = form.querySelector("[data-ems-form-error]");
        if (box) {
            box.textContent = message || text("data-sar-msg-failed");
            box.hidden = false;
            var lines = (payload && payload.error_list) || [];
            if (lines.length) {
                var list = document.createElement("ul");
                list.className = "sar-error-list";
                list.setAttribute("data-sar-error-list", "1");
                lines.forEach(function (line) {
                    var item = document.createElement("li");
                    item.textContent = String(line);
                    list.appendChild(item);
                });
                box.parentNode.insertBefore(list, box.nextSibling);
            }
        } else if (!first) {
            // Dialoqsuz forma (çekmecədəki sil/status) — xəta tostla.
            toast(message || text("data-sar-msg-failed"), "error");
        }
        if (first && typeof first.focus === "function") {
            first.focus();
        }
        return first;
    }

    /** HTML5 yoxlaması (`_form_dialog.html` `novalidate`-dir) — brauzer balonu əvəzinə sahə xətası. */
    function clientErrors(form) {
        if (typeof form.checkValidity !== "function" || form.checkValidity()) {
            return null;
        }
        var errors = {};
        each(form.querySelectorAll("input, textarea, select"), function (el) {
            if (!el.name || el.type === "hidden" || el.disabled || errors[el.name]) {
                return;
            }
            if (el.validity && !el.validity.valid) {
                errors[el.name] = el.validity.valueMissing
                    ? text("data-sar-msg-required")
                    : el.validationMessage || text("data-sar-msg-invalid");
            }
        });
        return errors;
    }

    /* ---- Göndəriş -------------------------------------------------------- */

    function setBusy(form, busy) {
        each(form.querySelectorAll('[type="submit"]'), function (btn) {
            btn.disabled = busy;
        });
        if (busy) {
            form.setAttribute("data-sar-busy", "1");
            form.setAttribute("aria-busy", "true");
        } else {
            form.removeAttribute("data-sar-busy");
            form.removeAttribute("aria-busy");
        }
    }

    function onSuccess(form, payload) {
        var dialog = form.closest(".ems-overlay--dialog");
        if (payload.keep_open) {
            // Toplu əlavənin qismən uğuru: textarea-da YALNIZ uğursuz sətirlər qalır.
            var area = fieldFor(form, "bulk_text");
            if (area) {
                area.value = payload.remaining_text || "";
            }
            showErrors(form, payload);
        } else {
            clearErrors(form);
            if (dialog && window.EMSOverlay) {
                window.EMSOverlay.close(dialog);
            }
        }
        toast(payload.message, payload.level || "success");
        (payload.warnings || []).forEach(function (warning) {
            toast(warning, "warning");
        });
        return refresh(payload);
    }

    function onError(form, err) {
        var payload = err && err.payload;
        if (!payload || typeof payload !== "object") {
            payload = { message: text("data-sar-msg-failed") };
        }
        showErrors(form, payload);
    }

    function submitForm(form) {
        var token = form.querySelector('input[name="csrfmiddlewaretoken"]');
        setBusy(form, true);
        return window.EMSCore.fetchJSON(form.getAttribute("action") || window.location.href, {
            method: "POST",
            body: new window.FormData(form),
            headers: token && token.value ? { "X-CSRFToken": token.value } : {},
        })
            .then(
                function (payload) {
                    return onSuccess(form, payload || {});
                },
                function (err) {
                    onError(form, err);
                }
            )
            .then(function () {
                setBusy(form, false);
            });
    }

    DELEGATE.on("submit", "form[data-sar-ajax]", function (event, form) {
        var invalid = form.hasAttribute("data-sar-form") ? clientErrors(form) : null;
        if (invalid) {
            event.preventDefault();
            showErrors(form, { errors: invalid, message: text("data-sar-msg-check") });
            return;
        }
        if (!window.EMSCore || typeof window.EMSCore.fetchJSON !== "function" || typeof window.FormData !== "function") {
            return; // köhnə yol: adi POST + redirect (server xətada dialoqu yenidən açır)
        }
        event.preventDefault();
        if (form.getAttribute("data-sar-busy") !== "1") {
            submitForm(form);
        }
    });

    /* ---- Uğurdan sonra: bölməni YERİNDƏ yenilə --------------------------- */

    function reloadSection() {
        if (typeof window.EMSProfileLoadSection === "function") {
            window.EMSProfileLoadSection(SECTION, window.location.href);
        } else {
            window.location.reload();
        }
    }

    function syncText(host, fresh, selector) {
        var next = fresh.querySelector(selector);
        var current = host.querySelector(selector);
        if (next && current) {
            current.textContent = next.textContent;
        }
    }

    function patchDrawer(current, fresh) {
        syncText(current, fresh, ".ems-drawer__title");
        syncText(current, fresh, ".ems-drawer__sub");
        [".ems-drawer__body", ".ems-drawer__foot"].forEach(function (selector) {
            var box = current.querySelector(selector);
            var next = fresh.querySelector(selector);
            if (box && next) {
                var top = box.scrollTop;
                box.innerHTML = next.innerHTML;
                box.scrollTop = top; // açıq çekmecə «tullanmır»
            }
        });
        if (!current.hidden && !current.contains(document.activeElement)) {
            var close = current.querySelector(".ems-drawer__x");
            if (close) {
                close.focus();
            }
        }
    }

    function patch(host, fresh) {
        each(fresh.querySelectorAll("[data-sar-region]"), function (region) {
            var current = host.querySelector('[data-sar-region="' + region.getAttribute("data-sar-region") + '"]');
            if (current) {
                current.innerHTML = region.innerHTML;
            }
        });
        syncText(host, fresh, "[data-sar-managers-count]");
        syncText(host, fresh, ".ems-filters__count");

        var seen = {};
        var anchor = host.querySelector(".ems-overlay--dialog");
        each(fresh.querySelectorAll(".ems-overlay--drawer[id]"), function (drawer) {
            seen[drawer.id] = true;
            var current = document.getElementById(drawer.id);
            if (current && host.contains(current)) {
                patchDrawer(current, drawer);
                return;
            }
            var node = document.importNode(drawer, true);
            node.hidden = true;
            if (anchor) {
                anchor.parentNode.insertBefore(node, anchor);
            } else {
                host.appendChild(node);
            }
        });
        each(host.querySelectorAll(".ems-overlay--drawer[id]"), function (drawer) {
            if (seen[drawer.id]) {
                return;
            }
            // Zal silinib (və ya bu səhifədən çıxıb) — çekmecəsi bağlanır və götürülür.
            if (!drawer.hidden && window.EMSOverlay) {
                window.EMSOverlay.close(drawer);
            }
            drawer.parentNode.removeChild(drawer);
        });
    }

    function highlight(host, payload) {
        var api = window.EMSExamRooms || {};
        if (typeof api.flashRow !== "function") {
            return;
        }
        if (payload.hl_comp) {
            api.flashRow(host.querySelector('[data-comp-row="' + payload.hl_comp + '"]'));
        } else if (payload.hl_room) {
            var cell = host.querySelector('[data-sar-room-row="' + payload.hl_room + '"]');
            api.flashRow(cell ? cell.closest("tr") : null);
        }
    }

    var refreshSeq = 0;

    function refresh(payload) {
        var host = root();
        var base = host && host.getAttribute("data-sar-fragment-url");
        if (!host || !base || typeof window.DOMParser !== "function") {
            reloadSection();
            return Promise.resolve();
        }
        var seq = (refreshSeq += 1);
        var url = new URL(base, window.location.origin);
        var params = new URLSearchParams(window.location.search);
        ["section", "hl_room", "hl_comp"].forEach(function (key) {
            params.delete(key);
        });
        url.search = params.toString();
        host.setAttribute("aria-busy", "true");
        return window.EMSCore.fetchJSON(url.toString())
            .then(function (data) {
                if (seq !== refreshSeq) {
                    return;
                }
                var doc = new window.DOMParser().parseFromString((data && data.html) || "", "text/html");
                var fresh = doc.querySelector("[data-sar-root]");
                if (!fresh) {
                    throw new Error("sar_root_missing");
                }
                patch(host, fresh);
                host.removeAttribute("aria-busy");
                highlight(host, payload || {});
                document.dispatchEvent(new CustomEvent("sar:refreshed", { detail: { payload: payload || {} } }));
            })
            .catch(function () {
                host.removeAttribute("aria-busy");
                reloadSection();
            });
    }

    /* ---- Adi POST xətasından sonra: dialoqu bərpa et --------------------- */

    function parsePrefill(btn) {
        try {
            return JSON.parse(btn.getAttribute("data-tof-prefill") || "{}") || {};
        } catch (err) {
            return {};
        }
    }

    function findOpener(state) {
        var openers = document.querySelectorAll('[data-tof-open="' + state.dialog + '"]');
        for (var i = 0; i < openers.length; i += 1) {
            var values = parsePrefill(openers[i]);
            if (
                values.action === state.action &&
                String(values.room_id || "") === String(state.room_id || "") &&
                String(values.computer_id || "") === String(state.computer_id || "")
            ) {
                return openers[i];
            }
        }
        return null;
    }

    function formFor(overlay, action) {
        var forms = overlay.querySelectorAll("form[data-sar-ajax]");
        for (var i = 0; i < forms.length; i += 1) {
            var field = forms[i].querySelector('input[name="action"]');
            if (field && field.value === action) {
                return forms[i];
            }
        }
        return forms[0] || null;
    }

    function fillValues(form, values) {
        each(form.querySelectorAll("[name]"), function (el) {
            if (el.name === "csrfmiddlewaretoken" || el.getAttribute("data-tof-keep") === "1") {
                return;
            }
            if (el.type === "checkbox") {
                el.checked = values[el.name] === "1"; // POST-da yoxdursa = işarəsiz idi
            } else if (Object.prototype.hasOwnProperty.call(values, el.name)) {
                el.value = values[el.name];
            }
        });
    }

    function restoreFormState() {
        var node = document.getElementById("sar-form-state");
        if (!node) {
            return;
        }
        var state = null;
        try {
            state = JSON.parse(node.textContent || "null");
        } catch (err) {
            state = null;
        }
        node.parentNode.removeChild(node); // bir dəfəlik — panel swap-ında təkrarlanmasın
        var overlay = state && state.dialog ? document.getElementById(state.dialog) : null;
        if (!overlay || !window.EMSOverlay) {
            return;
        }
        var drawer = state.room_id ? document.getElementById("sarRoomDrawer-" + state.room_id) : null;
        if (drawer && drawer.hidden && state.dialog !== "sarRoomDialog") {
            window.EMSOverlay.open(drawer);
        }
        var opener = overlay.classList.contains("ems-overlay--dialog") ? findOpener(state) : null;
        if (opener) {
            opener.click(); // ortaq prefill + başlıq/alt başlıq/düymə mətni (teaching_office.js + bizim)
        }
        if (overlay.hidden) {
            window.EMSOverlay.open(overlay);
        }
        var form = formFor(overlay, state.action);
        if (!form) {
            return;
        }
        fillValues(form, state.values || {});
        showErrors(form, { errors: state.errors || {}, message: state.message || "" });
    }

    window.EMSReady(restoreFormState);

    window.EMSExamRoomsAjax = {
        clearErrors: clearErrors,
        showErrors: showErrors,
        refresh: refresh,
        restoreFormState: restoreFormState,
    };
})(window, document);
