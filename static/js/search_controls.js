/**
 * Standard search controls:
 * - show/hide clear (X) button
 * - Enter submits search
 * - clear resets filter and submits
 */
document.addEventListener("DOMContentLoaded", function () {
    var forms = document.querySelectorAll("[data-standard-search-form]");
    forms.forEach(function (form) {
        var input = form.querySelector("[data-standard-search-input]");
        var clearButton = form.querySelector("[data-standard-search-clear]");
        var submitButton = form.querySelector("[data-standard-search-submit]");

        if (!input) {
            return;
        }

        function syncClearButton() {
            if (!clearButton) {
                return;
            }
            clearButton.hidden = !input.value.trim();
        }

        function submitForm() {
            form.classList.add("is-loading");
            if (submitButton) {
                submitButton.disabled = true;
            }
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit(submitButton || undefined);
                return;
            }
            form.submit();
        }

        syncClearButton();

        input.addEventListener("input", syncClearButton);
        input.addEventListener("keydown", function (event) {
            if (
                event.key !== "Enter" ||
                event.shiftKey ||
                event.ctrlKey ||
                event.altKey ||
                event.metaKey ||
                event.isComposing
            ) {
                return;
            }
            if (window.EMSSearchInput && window.EMSSearchInput.handles(input)) {
                return; // Enter-i vahid EMSSearchInput qatı emal edir (iki dəfə göndərilməsin)
            }
            event.preventDefault();
            submitForm();
        });

        if (clearButton) {
            clearButton.addEventListener("click", function () {
                if (!input.value.trim()) {
                    return;
                }
                if (window.EMSSearchInput && window.EMSSearchInput.clear(input)) {
                    syncClearButton();
                    input.focus();
                    return; // səhifə yenilənmədən sıfırlanır (2026-10-14)
                }
                input.value = "";
                syncClearButton();
                submitForm();
            });
        }
    });
});
