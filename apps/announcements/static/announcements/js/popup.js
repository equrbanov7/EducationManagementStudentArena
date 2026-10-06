/* Birdəfəlik elan popup-u (base.html, yalnız gözləyən elan varsa yüklənir).
 *
 * Bootstrap modalı (role=dialog, aria-modal, fokus tələsi, Esc). Stepper: bir neçə elan varsa
 * «‹ ›» ilə gəzilir; YALNIZ göstərilmiş addımlar «görüldü» sayılır. «Bağla» / Esc / «Ətraflı bax»
 * → `popup_seen` POST (keepalive), sonra modal bağlanır və ya detala keçilir.
 */
(function () {
    "use strict";

    if (window.__emsAnnouncementsPopup) {
        return;
    }
    window.__emsAnnouncementsPopup = true;

    function init() {
        var modalEl = document.querySelector("[data-ann-popup]");
        if (!modalEl || !window.bootstrap || !window.bootstrap.Modal) { return; }
        var items = Array.prototype.slice.call(modalEl.querySelectorAll("[data-ann-popup-item]"));
        if (!items.length) { return; }
        var index = 0;
        var shown = {};
        var reported = false;
        var counter = modalEl.querySelector("[data-ann-popup-counter]");
        var prev = modalEl.querySelector("[data-ann-popup-prev]");
        var next = modalEl.querySelector("[data-ann-popup-next]");
        var more = modalEl.querySelector("[data-ann-popup-more]");

        function show(i) {
            index = Math.max(0, Math.min(items.length - 1, i));
            items.forEach(function (item, k) { item.hidden = k !== index; });
            shown[items[index].getAttribute("data-id")] = true;
            if (counter) { counter.textContent = (index + 1) + " / " + items.length; }
            if (prev) { prev.disabled = index === 0; }
            if (next) { next.disabled = index === items.length - 1; }
            if (more) { more.setAttribute("href", items[index].getAttribute("data-detail-url") || "#"); }
        }

        function report() {
            if (reported) { return Promise.resolve(); }
            reported = true;
            var ids = Object.keys(shown);
            if (!ids.length || !window.EMSCore) { return Promise.resolve(); }
            var headers = { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" };
            headers["X-CSRFToken"] = window.EMSCore.getCsrfToken ? window.EMSCore.getCsrfToken() : "";
            return window.fetch(modalEl.getAttribute("data-seen-url"), {
                method: "POST",
                credentials: "same-origin",
                headers: headers,
                body: JSON.stringify({ ids: ids }),
                keepalive: true
            }).catch(function () { /* növbəti açılışda yenidən göstərilər — itki yoxdur */ });
        }

        var modal = window.bootstrap.Modal.getOrCreateInstance(modalEl, { backdrop: "static", keyboard: true });
        modalEl.addEventListener("hide.bs.modal", function () { report(); });
        modalEl.querySelectorAll("[data-ann-popup-close]").forEach(function (button) {
            button.addEventListener("click", function () { modal.hide(); });
        });
        if (prev) { prev.addEventListener("click", function () { show(index - 1); }); }
        if (next) { next.addEventListener("click", function () { show(index + 1); }); }
        if (more) {
            more.addEventListener("click", function (event) {
                event.preventDefault();
                var href = more.getAttribute("href");
                report().then(function () { window.location.href = href; });
            });
        }
        modalEl.addEventListener("keydown", function (event) {
            if (items.length < 2) { return; }
            if (event.key === "ArrowRight" && event.target === modalEl) { show(index + 1); }
            if (event.key === "ArrowLeft" && event.target === modalEl) { show(index - 1); }
        });
        show(0);
        modal.show();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
