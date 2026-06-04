(function () {
    "use strict";

    function initDebouncedSearchForms(root) {
        var scope = root || document;
        var forms = scope.querySelectorAll ? scope.querySelectorAll("form") : [];
        forms.forEach(function (form) {
            var method = (form.getAttribute("method") || "get").toLowerCase();
            if (method !== "get") {
                return;
            }
            if (form.hasAttribute("data-auto-filter-form")) {
                return;
            }
            if (form.dataset.debounceSearchInitialized === "1") {
                return;
            }

            var searchInputs = Array.from(
                form.querySelectorAll('input[name][type="text"], input[name][type="search"]')
            ).filter(function (input) {
                return /search/i.test(input.name || "");
            });
            var filterSelects = Array.from(form.querySelectorAll("select[name]")).filter(function (select) {
                return !select.disabled && !select.hasAttribute("data-no-auto-submit");
            });

            if (!searchInputs.length && !filterSelects.length) {
                return;
            }
            if (!searchInputs.length && !form.hasAttribute("data-auto-submit-selects")) {
                return;
            }

            var parsedDelay = parseInt(form.getAttribute("data-debounce-ms") || "1000", 10);
            var delayMs = Number.isFinite(parsedDelay) && parsedDelay >= 0 ? parsedDelay : 1000;
            var debounceTimer = null;

            function submitForm() {
                if (typeof form.requestSubmit === "function") {
                    form.requestSubmit();
                    return;
                }
                form.submit();
            }

            function scheduleSubmit(waitMs) {
                if (debounceTimer) {
                    clearTimeout(debounceTimer);
                    debounceTimer = null;
                }
                debounceTimer = window.setTimeout(submitForm, waitMs);
            }

            searchInputs.forEach(function (input) {
                input.addEventListener("input", function () {
                    scheduleSubmit(delayMs);
                });
            });

            filterSelects.forEach(function (select) {
                select.addEventListener("change", function () {
                    scheduleSubmit(0);
                });
            });

            form.addEventListener("submit", function () {
                if (debounceTimer) {
                    clearTimeout(debounceTimer);
                    debounceTimer = null;
                }
            });

            form.dataset.debounceSearchInitialized = "1";
        });
    }

    // Qlobal expose ki, profile.js AJAX swap-dan sonra re-init edə bilsin.
    window.EMSDebouncedSearchForms = { init: initDebouncedSearchForms };

    document.addEventListener("DOMContentLoaded", function () {
        initDebouncedSearchForms(document);
    });

    // AJAX section swap-dan sonra avtomatik re-init.
    document.addEventListener("profile:section:loaded", function (event) {
        var panel = event.detail && event.detail.panel ? event.detail.panel : document;
        initDebouncedSearchForms(panel);
    });
})();
