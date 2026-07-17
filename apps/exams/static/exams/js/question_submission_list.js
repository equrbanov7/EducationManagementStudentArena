/* Sual göndərişləri bölməsi — filtr select-lərinin avto-submit-i və
 * göndəriş silmə təsdiqi.
 *
 * QEYD: profil SPA-sı bölmə swap-ında paneldəki <script> taqlarını yenidən
 * icra edir — ona görə bütün dinləyicilər document səviyyəsində DELEGATED
 * qoşulur və qlobal bayraqla ikiqat qoşulmanın qarşısı alınır (CSP: inline
 * handler yoxdur).
 */
(function () {
    "use strict";

    if (window.__qsubListInit) {
        return;
    }
    window.__qsubListInit = true;

    // Filtr select-i dəyişən kimi formanı göndər (axtarış inputunun debounce-u
    // profile/ui.js-dəki js-profile-debounce-search mexanizmindədir).
    document.addEventListener("change", function (event) {
        var select = event.target;
        if (!select || select.tagName !== "SELECT") {
            return;
        }
        var form = select.closest("form.js-qsub-filter-form");
        if (!form) {
            return;
        }
        // Fakültə dəyişəndə köhnə kafedra seçimi yeni fakültəyə aid olmaya
        // bilər — server onsuz da sıfırlayır, amma URL-i təmiz saxlayaq.
        if (select.name === "qsub_faculty") {
            var kafedra = form.querySelector('select[name="qsub_kafedra"]');
            if (kafedra) {
                kafedra.value = "";
            }
        }
        if (select.name === "qsub_year") {
            var period = form.querySelector('select[name="qsub_period"]');
            if (period) {
                period.value = "";
            }
        }
        if (typeof form.requestSubmit === "function") {
            form.requestSubmit();
        } else {
            form.submit();
        }
    });

    // Silmə təsdiqi — həm siyahı kartındakı mini-forma, həm detal səhifəsindəki
    // formaction düyməsi üçün.
    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form || !form.classList || !form.classList.contains("js-qsub-delete-form")) {
            return;
        }
        var message = form.getAttribute("data-confirm") || "";
        if (message && !window.confirm(message)) {
            event.preventDefault();
        }
    });

    document.addEventListener("click", function (event) {
        var button = event.target && event.target.closest ? event.target.closest(".js-qsub-confirm") : null;
        if (!button) {
            return;
        }
        var message = button.getAttribute("data-confirm") || "";
        if (message && !window.confirm(message)) {
            event.preventDefault();
        }
    });
})();
