/**
 * Zal monitoru — tələbə modalında imtahan mərkəzinin PIN / kompüter düymələri (sahib 2026-10-26).
 *
 * «PIN-i göstər» → serverdən (audit + rate-limit) cari fərdi PIN alınır və göstərilir; «Gizlət»
 * dəyəri DOM-dan silir (yenidən göstərmək yenə sorğu + audit-dir). «Yeni PIN ver» — imtahana hələ
 * başlamamış tələbə; «Başqa kompüterdə davam et» — davam edən cəhd üçün «cihaz dəyişikliyi» təsdiqi.
 * Düymələrin görünməsi snapshot JSON-unun `pin_actions`-ındandır; modal həyat dövrü
 * snapshot_modal.js-in `fxc:snapshot-open|render|close` hadisələri ilə gəlir.
 * AJAX-safe: hadisələr bir dəfə (EMSReady.once) document-ə bağlanır, elementlər hər dəfə yenidən oxunur.
 */
(function () {
    "use strict";

    var MASK = "••••••••";
    var current = { sessionId: null, ticketId: null };
    var busy = false;

    function tools() {
        return document.getElementById("fxc-pin-tools");
    }

    function part(root, selector) {
        return root ? root.querySelector(selector) : null;
    }

    function fillUrl(tpl, sid, tid) {
        return String(tpl || "")
            .replace("sessions/0/", "sessions/" + sid + "/")
            .replace("tickets/0/", "tickets/" + tid + "/");
    }

    function setText(root, selector, text) {
        var el = part(root, selector);
        if (!el) return;
        el.textContent = text || "";
        el.hidden = !text;
    }

    function maskPin(root) {
        var value = part(root, "[data-pin-value]");
        if (value) value.textContent = MASK;
        var btn = part(root, '[data-pin-action="reveal"]');
        if (btn) btn.setAttribute("aria-pressed", "false");
        var label = part(root, "[data-pin-reveal-label]");
        if (label && root) label.textContent = root.dataset.i18nShow || "";
    }

    function showPin(root, pin) {
        var value = part(root, "[data-pin-value]");
        if (value) value.textContent = pin || MASK;
        var btn = part(root, '[data-pin-action="reveal"]');
        if (btn) btn.setAttribute("aria-pressed", "true");
        var label = part(root, "[data-pin-reveal-label]");
        if (label) label.textContent = root.dataset.i18nHide || "";
    }

    function reset() {
        var root = tools();
        if (!root) return;
        root.hidden = true;
        maskPin(root);
        setText(root, "[data-pin-note]", "");
        setText(root, "[data-pin-warning]", "");
    }

    function render(detail) {
        var root = tools();
        if (!root || !detail || !detail.data) return;
        current.sessionId = detail.sessionId;
        current.ticketId = detail.ticketId;
        var actions = detail.data.pin_actions || {};
        var any = !!(actions.reveal || actions.reissue || actions.device_release);
        root.hidden = !any;
        var map = { reveal: actions.reveal, reissue: actions.reissue, device: actions.device_release };
        Object.keys(map).forEach(function (key) {
            var btn = part(root, '[data-pin-action="' + key + '"]');
            if (btn) btn.hidden = !map[key];
        });
        var head = part(root, ".fxc-pin-tools__head");
        if (head) head.hidden = !actions.reveal;
    }

    function failure(root, err) {
        var payload = err && err.payload;
        var message = (payload && payload.error) || (root && root.dataset.i18nFailed) || "";
        setText(root, "[data-pin-note]", "");
        setText(root, "[data-pin-warning]", message);
    }

    function post(kind) {
        var root = tools();
        if (!root || busy || current.ticketId == null) return Promise.resolve(null);
        var tpl = root.dataset[kind + "UrlTemplate"];
        busy = true;
        return window.EMSCore.fetchJSON(fillUrl(tpl, current.sessionId, current.ticketId), { method: "POST", data: {} })
            .then(function (payload) {
                busy = false;
                return payload;
            })
            .catch(function (err) {
                busy = false;
                failure(root, err);
                return null;
            });
    }

    function applyPinPayload(root, payload, note) {
        if (!payload || !payload.success) return;
        showPin(root, payload.pin);
        setText(root, "[data-pin-note]", note || "");
        setText(root, "[data-pin-warning]", payload.warning || "");
    }

    function onReveal(root, btn) {
        if (btn.getAttribute("aria-pressed") === "true") {
            maskPin(root); // dəyər DOM-dan silinir — yenidən göstərmək yeni sorğudur (audit)
            return;
        }
        post("reveal").then(function (payload) { applyPinPayload(root, payload, ""); });
    }

    function confirmThen(message, fn) {
        if (window.EMSConfirm && typeof window.EMSConfirm.open === "function") {
            window.EMSConfirm.open({ body: message }).then(function (ok) { if (ok) fn(); });
            return;
        }
        fn();
    }

    function onReissue(root) {
        confirmThen(root.dataset.i18nConfirmReissue || "", function () {
            post("reissue").then(function (payload) {
                applyPinPayload(root, payload, root.dataset.i18nNewPin || "");
            });
        });
    }

    function onDevice(root) {
        confirmThen(root.dataset.i18nConfirmDevice || "", function () {
            post("device").then(function (payload) {
                if (!payload || !payload.success) return;
                setText(root, "[data-pin-warning]", "");
                setText(root, "[data-pin-note]", payload.message || "");
            });
        });
    }

    window.EMSReady.once("fxc-snapshot-pin-actions", function () {
        document.addEventListener("fxc:snapshot-open", function () { reset(); });
        document.addEventListener("fxc:snapshot-close", function () { reset(); });
        document.addEventListener("fxc:snapshot-render", function (evt) { render(evt.detail); });
        window.EMSDelegate.on("click", "#fxc-pin-tools [data-pin-action]", function (evt, btn) {
            var root = tools();
            if (!root) return;
            var action = btn.dataset.pinAction;
            if (action === "reveal") onReveal(root, btn);
            else if (action === "reissue") onReissue(root);
            else if (action === "device") onDevice(root);
        });
    });
})();
