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
