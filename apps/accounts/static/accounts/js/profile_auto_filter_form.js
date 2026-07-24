/*
 * profile_auto_filter_form.js
 * Source: extracted verbatim from the inline <script> shared by
 *   _pending_review_content.html, _review_results_content.html and
 *   _pending_answers_content.html (CSP inline-removal, 2026-07).
 * Auto-submits any [data-auto-filter-form] on text input (debounced),
 * Enter, or select change. Idempotent via the form.dataset.autoFilterBound
 * guard, and re-runs on every profile AJAX section swap via EMSReady.
 */
(function () {
    "use strict";

    function setupAutoFilterForm(form) {
        if (!form || form.dataset.autoFilterBound === "1") {
            return;
        }
        form.dataset.autoFilterBound = "1";

        var debounceHandle = null;
        var textFields = form.querySelectorAll('input[type="text"], input[type="search"]');
        var selects = form.querySelectorAll("select");

        function submitForm() {
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit();
                return;
            }
            form.submit();
        }

        textFields.forEach(function (field) {
            field.addEventListener("input", function () {
                window.clearTimeout(debounceHandle);
                debounceHandle = window.setTimeout(submitForm, 350);
            });
            field.addEventListener("keydown", function (event) {
                if (event.key === "Enter") {
                    event.preventDefault();
                    window.clearTimeout(debounceHandle);
                    submitForm();
                }
            });
        });

        selects.forEach(function (select) {
            select.addEventListener("change", submitForm);
        });
    }

    window.EMSReady(function () {
        document.querySelectorAll("[data-auto-filter-form]").forEach(setupAutoFilterForm);
    });
})();
