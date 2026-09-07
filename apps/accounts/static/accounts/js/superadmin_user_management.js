/* QA 2026-09-05 (UX-17): cədvəl başlıqları mövcud "Sıralama" (`user_sort`)
 * select-inə bağlıdır. Sıralama məntiqi DƏYİŞMİR — düymə yalnız select-in
 * dəyərini təyin edib formu göndərir (server tam səhifəni yeni sıralama ilə
 * render edir); aktiv sütunun aria-sort-u serverdə şablonla qoyulur. AJAX-safe:
 * `EMSReady` + idempotent + `EMSProfileReinitHooks` (bölmə panel swap-ı). */
function initSuperadminUserSort(root) {
    var scope = root || document;
    var tables = scope.querySelectorAll ? scope.querySelectorAll("[data-user-management-table]") : [];
    Array.prototype.forEach.call(tables, function (table) {
        if (table.dataset.userSortReady === "1") {
            return;
        }
        table.dataset.userSortReady = "1";
        var form = table.closest(".user-management-container").querySelector("form.user-management-filters");
        var select = form && form.querySelector('select[name="user_sort"]');
        if (!select) {
            return;
        }
        table.querySelectorAll("[data-user-sort-value]").forEach(function (button) {
            button.addEventListener("click", function () {
                select.value = button.dataset.userSortValue;
                select.dispatchEvent(new Event("change", { bubbles: true }));
                if (typeof form.requestSubmit === "function") {
                    form.requestSubmit();
                } else {
                    form.submit();
                }
            });
        });
    });
}

if (window.EMSReady) {
    window.EMSReady(initSuperadminUserSort);
} else {
    document.addEventListener("DOMContentLoaded", function () {
        initSuperadminUserSort(document);
    });
}
window.EMSProfileReinitHooks = window.EMSProfileReinitHooks || {};
window.EMSProfileReinitHooks.superadminUserSort = function (panel) {
    initSuperadminUserSort(panel || document);
};

document.addEventListener("DOMContentLoaded", function () {
    var deleteModal = document.getElementById("superadminUserDeleteModal");
    if (!deleteModal) {
        return;
    }

    deleteModal.addEventListener("show.bs.modal", function (event) {
        var trigger = event.relatedTarget;
        if (!trigger) {
            return;
        }

        var title = trigger.getAttribute("data-modal-title") || gettext("Hesabı sil");
        var description =
            trigger.getAttribute("data-modal-description") ||
            gettext("Seçilmiş istifadəçi hesabı üçün bu əməliyyat tətbiq ediləcək.");
        var username = trigger.getAttribute("data-username") || "";
        var userId = trigger.getAttribute("data-user-id") || "";
        var action = trigger.getAttribute("data-action") || "soft_delete";
        var nextUrl = trigger.getAttribute("data-next") || "";
        var submitLabel = trigger.getAttribute("data-modal-submit-label") || "Sil";

        var titleEl = document.getElementById("superadminUserDeleteModalLabel");
        var nameEl = document.getElementById("superadminUserDeleteName");
        var descriptionEl = document.getElementById("superadminUserDeleteDescription");
        var idInput = document.getElementById("superadminUserDeleteId");
        var actionInput = document.getElementById("superadminUserDeleteAction");
        var nextInput = document.getElementById("superadminUserDeleteNext");
        var submitBtn = document.getElementById("superadminUserDeleteSubmitLabel");

        if (titleEl) {
            titleEl.textContent = title;
        }
        if (nameEl) {
            nameEl.textContent = username;
        }
        if (descriptionEl) {
            descriptionEl.textContent = description;
        }
        if (idInput) {
            idInput.value = userId;
        }
        if (actionInput) {
            actionInput.value = action;
        }
        if (nextInput) {
            nextInput.value = nextUrl;
        }
        if (submitBtn) {
            submitBtn.textContent = submitLabel;
        }
    });
});
