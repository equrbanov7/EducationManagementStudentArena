/* «Sənəd yoxlaması» əməkdaş siyahısı — «Ləğv et» düyməsi səbəb dialoqunu açır.
   Düymə: data-dvs-revoke, data-action (POST ünvanı — server şablonundan), data-code (alt başlıq).
   AJAX-safe: document səviyyəli EMSDelegate (təkrar qeydiyyat stack-lənmir); dialoq davranışı
   (fokus tələsi, ≥ N simvol səbəb) ems_ui/overlay.js-dədir. Form adi POST ilə göndərilir. */
(function (window, document) {
    "use strict";

    var DIALOG_ID = "dvs-revoke-dialog";

    function openRevoke(event, button) {
        event.preventDefault();
        var dialog = document.getElementById(DIALOG_ID);
        if (!dialog || !window.EMSOverlay) {
            return;
        }
        var form = dialog.querySelector("form[data-ems-reason-form]");
        var action = button.getAttribute("data-action") || "";
        if (!form || action.charAt(0) !== "/") {
            return; // yalnız eyni-origin nisbi yol (server şablonundan)
        }
        form.setAttribute("action", action);
        var sub = dialog.querySelector(".ems-dialog__sub");
        if (sub) {
            sub.textContent = button.getAttribute("data-code") || "";
        }
        var field = form.querySelector("[data-ems-reason-field]");
        if (field) {
            field.value = "";
        }
        window.EMSOverlay.open(DIALOG_ID);
        if (window.EMSOverlay.syncReason) {
            window.EMSOverlay.syncReason(dialog);
        }
    }

    function bind() {
        if (window.EMSDelegate && window.EMSDelegate.on) {
            window.EMSDelegate.on("click", "[data-dvs-revoke]", openRevoke);
        }
    }

    if (window.EMSReady && window.EMSReady.once) {
        window.EMSReady.once("verification-staff-revoke", bind);
    } else if (window.EMSReady) {
        window.EMSReady(function () {
            if (!window.__dvsRevokeBound) {
                window.__dvsRevokeBound = true;
                bind();
            }
        });
    }
})(window, document);
