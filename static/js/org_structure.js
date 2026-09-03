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

    /* ---- "Ətraflı bax" — fakültə/kafedra ətraflı görünüş modalı ---------- */

    function detailModalParts() {
        var modal = document.getElementById("orgUnitDetailModal");
        if (!modal) {
            return null;
        }
        return {
            modal: modal,
            title: modal.querySelector("#orgUnitDetailModalLabel"),
            loading: modal.querySelector("[data-org-unit-detail-loading]"),
            error: modal.querySelector("[data-org-unit-detail-error]"),
            content: modal.querySelector("[data-org-unit-detail-content]"),
        };
    }

    window.EMSDelegate.on("click", ".js-org-unit-detail", function (event, button) {
        var url = button.getAttribute("data-detail-url");
        var parts = detailModalParts();
        if (!url || !parts || !window.bootstrap || !window.bootstrap.Modal) {
            return;
        }
        var fallbackTitle = parts.title ? parts.title.textContent : "";
        if (parts.title) {
            parts.title.textContent = button.getAttribute("data-unit-name") || fallbackTitle;
        }
        parts.content.innerHTML = "";
        parts.error.hidden = true;
        parts.loading.hidden = false;
        window.bootstrap.Modal.getOrCreateInstance(parts.modal).show();

        if (!window.EMSCore || !window.EMSCore.fetchJSON) {
            return;
        }
        window.EMSCore.fetchJSON(url)
            .then(function (payload) {
                parts.loading.hidden = true;
                if (payload && payload.ok && typeof payload.html === "string") {
                    parts.content.innerHTML = payload.html;
                    if (parts.title && payload.unit_name) {
                        parts.title.textContent = payload.unit_name;
                    }
                } else {
                    parts.error.hidden = false;
                    parts.error.textContent = parts.error.getAttribute("data-label-error") || "Xəta baş verdi.";
                }
            })
            .catch(function () {
                parts.loading.hidden = true;
                parts.error.hidden = false;
                parts.error.textContent = parts.error.getAttribute("data-label-error") || "Xəta baş verdi.";
            });
    });

    // Modal içindəki müəllim axtarışı — server-rendered siyahını client-side
    // süzür (adətən onlarla sətir, əlavə sorğuya ehtiyac yoxdur).
    window.EMSDelegate.on("input", ".js-org-unit-detail-teacher-search", function (event, input) {
        var list = input.closest(".org-unit-detail__block");
        if (!list) {
            return;
        }
        var query = input.value.trim().toLowerCase();
        var rows = list.querySelectorAll(".org-unit-detail__teacher-row");
        var visibleCount = 0;
        rows.forEach(function (row) {
            var matches = !query || (row.getAttribute("data-teacher-name") || "").indexOf(query) !== -1;
            row.hidden = !matches;
            if (matches) {
                visibleCount += 1;
            }
        });
        var noMatch = list.querySelector(".js-org-unit-detail-teacher-nomatch");
        if (noMatch) {
            noMatch.hidden = !(query && visibleCount === 0);
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
