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
            event.preventDefault();
            submitForm();
        });

        if (clearButton) {
            clearButton.addEventListener("click", function () {
                if (!input.value.trim()) {
                    return;
                }
                input.value = "";
                syncClearButton();
                submitForm();
            });
        }
    });
});
