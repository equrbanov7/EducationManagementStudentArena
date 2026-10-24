/* Sillabus redaktoru — plan saatı formaları (AJAX-safe: EMSDelegate, kabinet qabığında swap-dan sonra da işləyir).
 *
 * 1) Müəllim: plan/yük saatı tapılmayanda saatı əl ilə seçir (sahib 2026-09-20) — `syllabus_action` → `plan_hours`.
 * 2) Kafedra / tədris şöbəsi: plan saatını BİR qrup üçün düzəldir (sahib 2026-10-25) — forma öz `data-action-url`-i
 *    ilə `syllabus_plan_hours_override`-a gedir; `[data-syl-planhours-reset]` düyməsi düzəlişi silir (`reset`).
 *
 * Uğurda bölmə yenidən yüklənir ([data-syl-reload] varsa ona klik, yoxsa səhifə yenilənir). */
(function () {
    "use strict";
    if (!window.EMSDelegate) return;

    function post(url, payload) {
        if (window.EMSCore && window.EMSCore.fetchJSON) {
            return window.EMSCore.fetchJSON(url, { method: "POST", body: JSON.stringify(payload) });
        }
        return fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": (window.EMSCore && window.EMSCore.getCookie) ? window.EMSCore.getCookie("csrftoken") : "",
            },
            body: JSON.stringify(payload),
        }).then(function (r) { return r.json(); });
    }

    function say(msg, text) {
        if (!msg) return;
        msg.hidden = false;
        msg.textContent = text || "";
    }

    window.EMSDelegate.on("submit", "[data-syl-planhours]", function (event) {
        event.preventDefault();
        var form = event.target.closest("[data-syl-planhours]");
        if (!form || form.dataset.busy === "1") return;
        var msg = form.querySelector("[data-syl-planhours-msg]");
        var reset = !!(event.submitter && event.submitter.hasAttribute("data-syl-planhours-reset"));
        var payload = { action: "plan_hours", version: form.dataset.version };
        if (reset) {
            payload.reset = true;
        } else {
            ["lecture", "seminar", "lab"].forEach(function (k) {
                var el = form.querySelector('[name="' + k + '"]');
                payload[k] = el && el.value ? parseInt(el.value, 10) || 0 : 0;
            });
            if (!(payload.lecture || payload.seminar || payload.lab)) {
                say(msg, form.dataset.emptyMessage || "0");
                return;
            }
        }
        form.dataset.busy = "1";
        post(form.dataset.actionUrl, payload).then(function (data) {
            form.dataset.busy = "";
            if (data && data.ok) {
                if (msg && data.message) {
                    msg.classList.add("syl-planhours__msg--ok");
                    say(msg, data.message);
                }
                var reload = document.querySelector("[data-syl-reload]");
                if (reload) reload.click(); else window.location.reload();
                return;
            }
            if (msg) msg.classList.remove("syl-planhours__msg--ok");
            say(msg, (data && (data.error || data.message)) || "");
        }).catch(function () {
            form.dataset.busy = "";
            say(msg, form.dataset.networkMessage || "");
        });
    });
})();
