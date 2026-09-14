/**
 * data-confirm atributlu formlar üçün sadə təsdiq addımı.
 * (İnline onsubmit YOXDUR — CSP-safe xarici fayl.)
 */
(function () {
    "use strict";
    document.addEventListener("submit", function (evt) {
        var form = evt.target.closest ? evt.target.closest("form[data-confirm]") : null;
        if (!form) return;
        var text = form.dataset.confirm;
        if (!text) return;
        // 2026-09-14 (audit FE-F19): native confirm() → EMSConfirm (vahid dialoq); ləğv = sorğu yoxdur.
        if (form.dataset.emsConfirmed === "1") {
            delete form.dataset.emsConfirmed;
            return;
        }
        evt.preventDefault();
        var submitter = evt.submitter || null;
        window.EMSConfirm.open({ body: text, danger: true }).then(function (ok) {
            if (!ok) return;
            form.dataset.emsConfirmed = "1";
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit(submitter && submitter.form === form ? submitter : undefined);
            } else {
                form.submit();
            }
        });
    });
})();
