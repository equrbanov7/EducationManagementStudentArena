/* Elan popup-u (base.html, yalnız gözləyən elan varsa yüklənir).
 *
 * Bootstrap modalı (role=dialog, aria-modal, fokus tələsi). Stepper: bir neçə elan varsa
 * «‹ ›» ilə gəzilir; YALNIZ göstərilmiş addımlar «görüldü» sayılır.
 *
 * Adi elan: «Bağla» / Esc / «Ətraflı bax» → `popup_seen` POST (keepalive), sonra modal bağlanır
 * və ya detala keçilir.
 *
 * MƏCBURİ elan (`data-mandatory`): təsdiqlənməmiş məcburi elan qaldıqca modal KİLİDLİDİR —
 * × və «Bağla» gizlidir, `hide.bs.modal` ləğv olunur (Esc, fon kliki, istənilən `hide()`), fon
 * statikdir. «Elanı oxudum və tanış oldum» işarələnəndə «Təsdiq edirəm» aktivləşir → `ack` POST
 * (`EMSCore.fetchJSON`, CSRF avtomatik) → elan stepper-dən çıxır, növbətiyə keçilir; heç nə
 * qalmayıbsa modal bağlanır. «Ətraflı bax» məcburi elanda da icazəlidir.
 *
 * AJAX-safe: `EMSReady` ilə işə düşür; init idempotentdir (modal elementində bayraq) — bölmə
 * swap-ından sonra təkrar çağırılsa da dinləyicilər ikiqat bağlanmır.
 */
(function () {
    "use strict";

    if (window.__emsAnnouncementsPopup) {
        return;
    }
    window.__emsAnnouncementsPopup = true;

    function init() {
        var modalEl = document.querySelector("[data-ann-popup]");
        if (!modalEl || modalEl.__annPopupInit || !window.bootstrap || !window.bootstrap.Modal) { return; }
        modalEl.__annPopupInit = true;
        var items = Array.prototype.slice.call(modalEl.querySelectorAll("[data-ann-popup-item]"));
        if (!items.length) { return; }
        var index = 0;
        var total = items.length;
        var shown = {};
        var reported = false;
        var counter = modalEl.querySelector("[data-ann-popup-counter]");
        var prev = modalEl.querySelector("[data-ann-popup-prev]");
        var next = modalEl.querySelector("[data-ann-popup-next]");
        var steps = modalEl.querySelector(".ann-popup__steps");
        var more = modalEl.querySelector("[data-ann-popup-more]");
        var ackBox = modalEl.querySelector("[data-ann-popup-ack]");
        var ackCheck = modalEl.querySelector("[data-ann-popup-ack-check]");
        var ackError = modalEl.querySelector("[data-ann-popup-ack-error]");
        var confirm = modalEl.querySelector("[data-ann-popup-confirm]");
        var closers = Array.prototype.slice.call(modalEl.querySelectorAll("[data-ann-popup-close]"));
        var busy = false;

        function needsAck(item) {
            return Boolean(item) && item.getAttribute("data-mandatory") === "1" && !item.hasAttribute("data-acked");
        }

        function isLocked() {
            return items.some(needsAck);
        }

        function syncLock() {
            var locked = isLocked();
            modalEl.classList.toggle("is-locked", locked);
            closers.forEach(function (button) { button.hidden = locked; });
        }

        function syncAck() {
            var current = items[index];
            var pending = needsAck(current);
            if (ackBox) { ackBox.hidden = !pending; }
            if (ackCheck) { ackCheck.checked = false; }
            if (ackError) { ackError.hidden = true; ackError.textContent = ""; }
            if (confirm) { confirm.hidden = !pending; confirm.disabled = true; }
            if (more) {
                more.classList.toggle("btn-primary", !pending);
                more.classList.toggle("btn-outline-primary", pending);
            }
        }

        function show(i) {
            index = Math.max(0, Math.min(items.length - 1, i));
            items.forEach(function (item, k) { item.hidden = k !== index; });
            shown[items[index].getAttribute("data-id")] = true;
            if (counter) { counter.textContent = (index + 1) + " / " + items.length; }
            if (steps) { steps.hidden = items.length < 2; }
            if (prev) { prev.disabled = index === 0; }
            if (next) { next.disabled = index === items.length - 1; }
            if (more) { more.setAttribute("href", items[index].getAttribute("data-detail-url") || "#"); }
            syncAck();
            syncLock();
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

        function decrementBadge() {
            document.querySelectorAll('.profile-sidebar [data-badge-key="announcements_unread"]').forEach(function (badge) {
                var value = parseInt(badge.textContent, 10);
                badge.textContent = value > 1 ? String(value - 1) : "";
            });
        }

        var modal = window.bootstrap.Modal.getOrCreateInstance(modalEl, { backdrop: "static", keyboard: true });

        modalEl.addEventListener("hide.bs.modal", function (event) {
            if (isLocked()) {
                event.preventDefault();  // Esc / proqram `hide()` — təsdiqsiz bağlanmır
                return;
            }
            report();
        });
        closers.forEach(function (button) {
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
        if (ackCheck && confirm) {
            ackCheck.addEventListener("change", function () { confirm.disabled = busy || !ackCheck.checked; });
        }
        if (confirm) {
            confirm.addEventListener("click", function () {
                var item = items[index];
                if (busy || !needsAck(item) || !ackCheck || !ackCheck.checked || !window.EMSCore) { return; }
                busy = true;
                confirm.disabled = true;
                confirm.setAttribute("aria-busy", "true");
                window.EMSCore.fetchJSON(item.getAttribute("data-ack-url"), { method: "POST", data: { confirm: true } })
                    .then(function (payload) {
                        item.setAttribute("data-acked", "1");
                        if (payload && payload.newly_read) { decrementBadge(); }
                        items.splice(index, 1);
                        item.hidden = true;
                        if (!items.length) {
                            syncLock();
                            modal.hide();
                            return;
                        }
                        show(Math.min(index, items.length - 1));
                    })
                    .catch(function (error) {
                        var payload = error && error.payload;
                        var errors = payload && payload.errors && payload.errors.__all__;
                        if (ackError) {
                            ackError.textContent = (errors && errors[0]) || modalEl.getAttribute("data-msg-ack-error") || "Error";
                            ackError.hidden = false;
                        }
                        confirm.disabled = !ackCheck.checked;
                    })
                    .then(function () {
                        busy = false;
                        confirm.removeAttribute("aria-busy");
                    });
            });
        }
        modalEl.addEventListener("keydown", function (event) {
            if (items.length < 2) { return; }
            if (event.key === "ArrowRight" && event.target === modalEl) { show(index + 1); }
            if (event.key === "ArrowLeft" && event.target === modalEl) { show(index - 1); }
        });
        if (total) { show(0); }
        modal.show();
    }

    if (typeof window.EMSReady === "function") {
        window.EMSReady(init);
    }
})();
