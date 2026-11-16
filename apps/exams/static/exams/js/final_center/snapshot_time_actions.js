/**
 * Zal monitoru — tələbə modalında «Əlavə vaxt» bloku (sahib 2026-11-17).
 *
 * Nəzarətçi / imtahan mərkəzi BU tələbəyə N dəqiqə əlavə edir (məs. kompüter dondu, vaxt itdi): dəqiqə + səbəb →
 * təsdiq pəncərəsi (EMSConfirm) → POST. Yalnız həmin cəhdin vaxtı uzanır; tələbənin ekranı yeni vaxtı WS /
 * status sorğusu ilə yenidən yükləmədən alır. Blokun görünməsi snapshot JSON-unun `time_actions`-ındandır;
 * modal həyat dövrü snapshot_modal.js-in `fxc:snapshot-open|render|close` hadisələri ilə gəlir.
 * AJAX-safe: hadisələr bir dəfə (EMSReady.once) document-ə bağlanır, elementlər hər dəfə yenidən oxunur.
 */
(function () {
    "use strict";

    var current = { sessionId: null, ticketId: null, maxMinutes: 60 };
    var busy = false;

    function tools() {
        return document.getElementById("fxc-time-tools");
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

    function setGiven(root, minutes) {
        var text = minutes > 0 ? String(root.dataset.i18nGiven || "").replace("%(minutes)s", String(minutes)) : "";
        setText(root, "[data-time-given]", text);
    }

    function reset() {
        var root = tools();
        if (!root) return;
        root.hidden = true;
        setText(root, "[data-time-note]", "");
        setText(root, "[data-time-warning]", "");
        var reason = part(root, "[data-time-reason]");
        if (reason) reason.value = "";
        var minutes = part(root, "[data-time-minutes]");
        if (minutes) minutes.value = "5";
    }

    function render(detail) {
        var root = tools();
        if (!root || !detail || !detail.data) return;
        var changed = current.ticketId !== detail.ticketId;
        current.sessionId = detail.sessionId;
        current.ticketId = detail.ticketId;
        var actions = detail.data.time_actions || {};
        root.hidden = !actions.extend;
        setGiven(root, parseInt(actions.extra_minutes, 10) || 0);
        current.maxMinutes = parseInt(actions.max_minutes, 10) || 0;
        var minutes = part(root, "[data-time-minutes]");
        if (minutes && current.maxMinutes > 0) {
            minutes.max = String(current.maxMinutes);
            if (changed && parseInt(minutes.value, 10) > current.maxMinutes) minutes.value = String(current.maxMinutes);
        }
    }

    function readMinutes(root) {
        var input = part(root, "[data-time-minutes]");
        var value = parseInt(input ? input.value : "", 10);
        if (isNaN(value) || value < 1) return 0;
        return Math.min(value, current.maxMinutes || value);
    }

    function failure(root, err) {
        var payload = err && err.payload;
        setText(root, "[data-time-note]", "");
        setText(root, "[data-time-warning]", (payload && payload.error) || root.dataset.i18nFailed || "");
    }

    function submit(root, minutes, reason) {
        if (busy || current.ticketId == null) return;
        busy = true;
        var url = fillUrl(root.dataset.urlTemplate, current.sessionId, current.ticketId);
        // Forma kimi (request.POST) — URLSearchParams brauzerdə Content-Type-ı özü qoyur.
        var body = new URLSearchParams({ minutes: String(minutes), reason: reason });
        window.EMSCore.fetchJSON(url, { method: "POST", body: body })
            .then(function (payload) {
                busy = false;
                if (!payload || !payload.success) {
                    failure(root, { payload: payload });
                    return;
                }
                setText(root, "[data-time-warning]", "");
                setText(root, "[data-time-note]", payload.message || "");
                setGiven(root, parseInt(payload.extra_minutes, 10) || 0);
                var reasonEl = part(root, "[data-time-reason]");
                if (reasonEl) reasonEl.value = "";
                if (window.FXCSnapshot && typeof window.FXCSnapshot.reload === "function") {
                    window.FXCSnapshot.reload();
                }
            })
            .catch(function (err) {
                busy = false;
                failure(root, err);
            });
    }

    function onExtend(root) {
        var minutes = readMinutes(root);
        var reasonEl = part(root, "[data-time-reason]");
        var reason = reasonEl ? reasonEl.value.trim() : "";
        if (!minutes) {
            var input = part(root, "[data-time-minutes]");
            if (input) input.focus();
            return;
        }
        if (!reason) {
            setText(root, "[data-time-warning]", root.dataset.i18nReasonRequired || "");
            if (reasonEl) reasonEl.focus();
            return;
        }
        var message = String(root.dataset.i18nConfirm || "").replace("%(minutes)s", String(minutes));
        if (window.EMSConfirm && typeof window.EMSConfirm.open === "function") {
            window.EMSConfirm.open({ body: message }).then(function (ok) { if (ok) submit(root, minutes, reason); });
            return;
        }
        submit(root, minutes, reason);
    }

    window.EMSReady.once("fxc-snapshot-time-actions", function () {
        document.addEventListener("fxc:snapshot-open", function () { reset(); });
        document.addEventListener("fxc:snapshot-close", function () { reset(); current.ticketId = null; });
        document.addEventListener("fxc:snapshot-render", function (evt) { render(evt.detail); });
        window.EMSDelegate.on("click", "#fxc-time-tools [data-time-quick]", function (evt, btn) {
            var input = part(tools(), "[data-time-minutes]");
            if (input) input.value = btn.dataset.timeQuick;
        });
        window.EMSDelegate.on("click", "#fxc-time-tools [data-time-action='extend']", function () {
            var root = tools();
            if (root) onExtend(root);
        });
    });
})();
