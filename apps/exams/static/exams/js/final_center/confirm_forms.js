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
        if (text && !window.confirm(text)) {
            evt.preventDefault();
        }
    });
})();
