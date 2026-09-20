/* Sillabus redaktoru — plan saatı tapılmayanda müəllimin əl ilə saat yazması
 * (sahib 2026-09-20). Forma `syllabus_action` → `plan_hours`; uğurda bölmə
 * yenidən yüklənir ([data-syl-reload] varsa ona klik, yoxsa səhifə yenilənir).
 * AJAX-safe: EMSDelegate (kabinet qabığında swap-dan sonra da işləyir). */
(function () {
    "use strict";
    if (!window.EMSDelegate) return;
    window.EMSDelegate.on("submit", "[data-syl-planhours]", function (event) {
        event.preventDefault();
        var form = event.target.closest("[data-syl-planhours]");
        if (!form || form.dataset.busy === "1") return;
        var msg = form.querySelector("[data-syl-planhours-msg]");
        var payload = { action: "plan_hours", version: form.dataset.version };
        ["lecture", "seminar", "lab"].forEach(function (k) {
            var el = form.querySelector('[name="' + k + '"]');
            payload[k] = el && el.value ? parseInt(el.value, 10) || 0 : 0;
        });
        if (!(payload.lecture || payload.seminar || payload.lab)) {
            if (msg) { msg.hidden = false; msg.textContent = form.dataset.emptyMessage || "0"; }
            return;
        }
        form.dataset.busy = "1";
        var request = window.EMSCore && window.EMSCore.fetchJSON
            ? window.EMSCore.fetchJSON(form.dataset.actionUrl, { method: "POST", body: JSON.stringify(payload) })
            : fetch(form.dataset.actionUrl, {
                  method: "POST",
                  credentials: "same-origin",
                  headers: { "Content-Type": "application/json", "X-CSRFToken": (window.EMSCore && window.EMSCore.getCookie) ? window.EMSCore.getCookie("csrftoken") : "" },
                  body: JSON.stringify(payload),
              }).then(function (r) { return r.json(); });
        request.then(function (data) {
            form.dataset.busy = "";
            if (data && data.ok) {
                var reload = document.querySelector("[data-syl-reload]");
                if (reload) reload.click(); else window.location.reload();
                return;
            }
            if (msg) { msg.hidden = false; msg.textContent = (data && (data.error || data.message)) || ""; }
        }).catch(function () {
            form.dataset.busy = "";
            if (msg) { msg.hidden = false; msg.textContent = form.dataset.networkMessage || ""; }
        });
    });
})();
