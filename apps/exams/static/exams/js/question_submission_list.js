/* Sual göndərişləri — silmə təsdiqi (siyahı bölməsi + detal səhifəsi).
 *
 * 2026-09-09: filtr select-lərinin avto-submit-i və uzun-siyahılı axtarışlı
 * seçiciləri ORTAQ `ems_ui` filtr panelinə köçdü (`_filter_bar.html` +
 * `filter_bar.js`), ona görə həmin bloklar buradan silindi.
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

    // Silmə təsdiqi — mərkəzləşmiş bootstrap modalı (_qsub_delete_modal.html).
    // Native window.confirm yalnız modal/bootstrap tapılmayanda fallback-dır.
    function openDeleteModal(actionUrl) {
        var modalEl = document.getElementById("qsubDeleteModal");
        var modalForm = document.getElementById("qsubDeleteModalForm");
        if (!modalEl || !modalForm || typeof bootstrap === "undefined") {
            return false;
        }
        modalForm.action = actionUrl || "";
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
        return true;
    }

    // Siyahı kartındakı mini-forma: submit-i saxla, modalda təsdiq istə.
    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form || !form.classList || !form.classList.contains("js-qsub-delete-form")) {
            return;
        }
        // Modal formunun öz submit-i buradan keçməsin (id ilə tanınır).
        if (form.id === "qsubDeleteModalForm") {
            return;
        }
        if (openDeleteModal(form.action)) {
            event.preventDefault();
            return;
        }
        var message = form.getAttribute("data-confirm") || "";
        if (!message) {
            return;
        }
        event.preventDefault();
        window.EMSConfirm.open({ body: message, danger: true }).then(function (ok) {
            if (ok) {
                form.submit();
            }
        });
    });

    // Detal səhifəsindəki formaction düyməsi.
    document.addEventListener("click", function (event) {
        var button = event.target && event.target.closest ? event.target.closest(".js-qsub-confirm") : null;
        if (!button) {
            return;
        }
        var actionUrl = button.getAttribute("formaction") || (button.form && button.form.action) || "";
        if (openDeleteModal(actionUrl)) {
            event.preventDefault();
            return;
        }
        var message = button.getAttribute("data-confirm") || "";
        if (!message) {
            return;
        }
        event.preventDefault();
        window.EMSConfirm.open({ body: message, danger: true }).then(function (ok) {
            if (!ok || !button.form) {
                return;
            }
            if (typeof button.form.requestSubmit === "function") {
                button.form.requestSubmit(button);
            } else {
                button.form.submit();
            }
        });
    });
})();
