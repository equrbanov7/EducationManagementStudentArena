/**
 * Role assignment search UX behaviors:
 * - Enter key submits exactly like search button.
 * - Clear (X) button visibility and behavior.
 * - Loading spinner state while form is submitting.
 */
document.addEventListener("DOMContentLoaded", function () {
    var searchForms = document.querySelectorAll("[data-role-assignment-search-form]");
    if (!searchForms.length) {
        return;
    }

    searchForms.forEach(function (form) {
        var input = form.querySelector("[data-role-assignment-search-input]");
        var clearButton = form.querySelector("[data-role-assignment-clear]");
        var submitButton = form.querySelector("[data-role-assignment-submit]");

        if (!input) {
            return;
        }

        function syncClearButtonVisibility() {
            if (!clearButton) {
                return;
            }
            clearButton.hidden = !(input.value || "").trim();
        }

        syncClearButtonVisibility();

        input.addEventListener("input", syncClearButtonVisibility);

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
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit(submitButton || undefined);
                return;
            }
            form.submit();
        });

        if (clearButton) {
            clearButton.addEventListener("click", function () {
                input.value = "";
                syncClearButtonVisibility();
                if (typeof form.requestSubmit === "function") {
                    form.requestSubmit(submitButton || undefined);
                    return;
                }
                form.submit();
            });
        }

        form.addEventListener("submit", function () {
            form.classList.add("is-loading");
            if (submitButton) {
                submitButton.disabled = true;
            }
        });
    });
});
