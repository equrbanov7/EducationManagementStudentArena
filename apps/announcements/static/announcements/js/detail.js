/* «Elanlar» detalı — «oxundu» qəbzi, son tarix geri sayımı, «Müraciət et».
 *
 * AJAX-safe: `EMSReady` (hər bölmə swap-ından sonra) yalnız hələ işlənməmiş detal kartını
 * götürür (`data-ann-read-sent`); düymələr `EMSDelegate` ilə. Mətnlər data-atributlardan
 * gəlir (i18n serverdə). CSRF `EMSCore.fetchJSON` tərəfindən avtomatik qoyulur.
 */
(function () {
    "use strict";

    if (window.__emsAnnouncementsDetail) {
        return;
    }
    window.__emsAnnouncementsDetail = true;

    function markRead() {
        var card = document.querySelector("[data-ann-detail]:not([data-ann-read-sent])");
        if (!card || !window.EMSCore) { return; }
        card.setAttribute("data-ann-read-sent", "1");
        var url = card.getAttribute("data-read-url");
        if (!url) { return; }
        window.EMSCore.fetchJSON(url, { method: "POST", data: {} })
            .then(function (payload) {
                if (!payload || !payload.newly_read) { return; }
                document.querySelectorAll('.profile-sidebar [data-badge-key="announcements_unread"]').forEach(function (badge) {
                    var value = parseInt(badge.textContent, 10);
                    badge.textContent = value > 1 ? String(value - 1) : "";
                });
            })
            .catch(function () { /* oxundu qəbzi kritik deyil */ });
    }

    function setResult(section, text, isError) {
        var node = section.querySelector("[data-ann-apply-result]");
        if (!node) { return; }
        node.hidden = false;
        node.textContent = text;
        node.classList.toggle("is-error", Boolean(isError));
    }

    function errorText(section, error) {
        var payload = error && error.payload;
        var errors = payload && payload.errors && payload.errors.__all__;
        return (errors && errors[0]) || section.getAttribute("data-msg-error") || "Error";
    }

    window.EMSDelegate.on("submit", "[data-ann-apply] [data-ann-apply-form]", function (event, form) {
        event.preventDefault();
        var section = form.closest("[data-ann-apply]");
        var button = form.querySelector("[data-ann-apply-submit]");
        if (!section || (button && button.disabled)) { return; }
        if (button) { button.disabled = true; button.setAttribute("aria-busy", "true"); }
        var note = form.elements.namedItem("note");
        window.EMSCore.fetchJSON(section.getAttribute("data-apply-url"), {
            method: "POST",
            data: { note: note ? note.value : "" }
        })
            .then(function (payload) {
                var done = section.getAttribute("data-msg-done") || "";
                setResult(section, payload && payload.number ? done + ": " + payload.number : done, false);
                form.hidden = true;
            })
            .catch(function (error) {
                setResult(section, errorText(section, error), true);
                if (button) { button.disabled = false; }
            })
            .then(function () {
                if (button) { button.removeAttribute("aria-busy"); }
            });
    });

    window.EMSDelegate.on("click", "[data-ann-apply] [data-ann-apply-link]", function (event, button) {
        event.preventDefault();
        var section = button.closest("[data-ann-apply]");
        var href = button.getAttribute("data-href");
        if (!section || !href) { return; }
        // Pəncərə klik anında açılır (popup bloklayıcısı), qəbz isə paralel yazılır.
        var opened = window.open(href, "_blank", "noopener,noreferrer");
        window.EMSCore.fetchJSON(section.getAttribute("data-apply-url"), { method: "POST", data: {} })
            .then(function () {
                if (!opened) { window.location.href = href; }
            })
            .catch(function (error) { setResult(section, errorText(section, error), true); });
    });

    function hoursLeft() {
        document.querySelectorAll("[data-ann-countdown]").forEach(function (node) {
            var due = Date.parse(node.getAttribute("data-ann-countdown"));
            if (isNaN(due)) { return; }
            var ms = due - Date.now();
            if (ms > 0 && ms < 24 * 3600 * 1000) {
                var hours = Math.floor(ms / 3600000);
                var minutes = Math.floor((ms % 3600000) / 60000);
                node.setAttribute("data-ann-left", (hours < 10 ? "0" : "") + hours + ":" + (minutes < 10 ? "0" : "") + minutes);
            }
        });
    }

    window.EMSReady(function () {
        markRead();
        hoursLeft();
    });
    window.EMSReady.once("ann-countdown", function () {
        window.setInterval(hoursLeft, 60000);
    });
})();
