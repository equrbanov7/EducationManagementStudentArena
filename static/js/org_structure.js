/* =========================================================================
   org_structure.js — Fakültə / Kafedra idarəetmə UI (modal doldurma).

   AJAX-safe: bütün handler-lər EMSDelegate ilə `document` üzərində delegated
   qoşulur, ona görə profil bölməsi AJAX ilə dəyişəndə yenidən init lazım deyil.
   CSP: inline onclick yoxdur — hər şey bu faylda.
   ========================================================================= */
(function () {
    "use strict";

    if (!window.EMSDelegate || !window.EMSReady) {
        return;
    }

    function setField(root, fieldName, value) {
        var field = root.querySelector('[data-org-field="' + fieldName + '"]');
        if (!field) {
            return;
        }
        if (field.tagName === "INPUT" || field.tagName === "SELECT" || field.tagName === "TEXTAREA") {
            field.value = value == null ? "" : value;
            if (field.tagName === "SELECT" && window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(field);
            }
        } else {
            field.textContent = value == null ? "" : value;
        }
    }

    function openUnitModal(button, fill) {
        var targetSelector = button.getAttribute("data-modal-target");
        if (!targetSelector || !window.bootstrap || !window.bootstrap.Modal) {
            return;
        }
        var modal = document.querySelector(targetSelector);
        if (!modal) {
            return;
        }
        fill(modal);
        window.bootstrap.Modal.getOrCreateInstance(modal).show();
    }

    // Redaktə modalı — ad/kod (+ kafedrada fakültə) doldurulur.
    window.EMSDelegate.on("click", ".js-org-unit-edit", function (event, button) {
        openUnitModal(button, function (modal) {
            setField(modal, "unit_id", button.getAttribute("data-unit-id"));
            setField(modal, "name", button.getAttribute("data-unit-name"));
            setField(modal, "code", button.getAttribute("data-unit-code"));
            if (button.hasAttribute("data-unit-parent")) {
                setField(modal, "parent", button.getAttribute("data-unit-parent"));
            }
        });
    });

    // Silmə təsdiq modalı.
    window.EMSDelegate.on("click", ".js-org-unit-delete", function (event, button) {
        openUnitModal(button, function (modal) {
            setField(modal, "unit_id", button.getAttribute("data-unit-id"));
            setField(modal, "unit_name", button.getAttribute("data-unit-name"));
        });
    });

    // Rəhbər (dekan / kafedra müdiri) təyinat modalı — cari rəhbər önseçilir.
    window.EMSDelegate.on("click", ".js-org-unit-head", function (event, button) {
        openUnitModal(button, function (modal) {
            setField(modal, "unit_id", button.getAttribute("data-unit-id"));
            setField(modal, "unit_name", button.getAttribute("data-unit-name"));
            setField(modal, "head_user", button.getAttribute("data-head-id") || "");
        });
    });

    // Kafedraya müəllim təyinatı modalı.
    window.EMSDelegate.on("click", ".js-org-unit-add-teacher", function (event, button) {
        openUnitModal(button, function (modal) {
            setField(modal, "unit_id", button.getAttribute("data-unit-id"));
            setField(modal, "unit_name", button.getAttribute("data-unit-name"));
            setField(modal, "membership_id", "");
        });
    });

    // Modal formu submit olunan kimi modalı bağla — AJAX swap zamanı
    // backdrop-un "ilişib qalmaması" üçün.
    window.EMSDelegate.on("submit", "form[data-org-modal-form]", function (event, form) {
        var modal = form.closest(".modal");
        if (modal && window.bootstrap && window.bootstrap.Modal) {
            window.bootstrap.Modal.getOrCreateInstance(modal).hide();
        }
    });

    // Defensiv: bölmə AJAX ilə əvəz olunarkən açıq modal DOM-dan silinərsə,
    // sahibsiz backdrop və body kilidi təmizlənsin.
    window.EMSReady(function () {
        if (document.querySelector(".modal.show")) {
            return;
        }
        document.querySelectorAll(".modal-backdrop").forEach(function (backdrop) {
            backdrop.remove();
        });
        document.body.classList.remove("modal-open");
        document.body.style.removeProperty("overflow");
        document.body.style.removeProperty("padding-right");
    });
})();
