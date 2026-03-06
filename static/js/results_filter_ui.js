(function () {
    function submitForm(form) {
        if (!form) return;
        if (typeof form.requestSubmit === "function") {
            form.requestSubmit();
        } else {
            form.submit();
        }
    }

    function resetField(field) {
        if (!field) return;

        const tagName = field.tagName.toLowerCase();
        const resetValue = field.getAttribute("data-reset-value");

        if (tagName === "select") {
            if (resetValue !== null) {
                field.value = resetValue;
            } else if (field.options.length > 0) {
                field.selectedIndex = 0;
            }
            return;
        }

        const type = (field.getAttribute("type") || "").toLowerCase();
        if (type === "checkbox" || type === "radio") {
            field.checked = false;
            return;
        }

        field.value = resetValue !== null ? resetValue : "";
    }

    document.addEventListener("DOMContentLoaded", function () {
        const forms = document.querySelectorAll(".js-results-filters-form");

        forms.forEach(function (form) {
            const searchInput = form.querySelector(".js-auto-filter-search");
            const autoControls = form.querySelectorAll(".js-auto-filter");
            const clearBtn = form.querySelector(".js-clear-results-filters");
            const resettableFields = form.querySelectorAll(".js-filter-resettable");
            let debounceTimer = null;

            const triggerSubmit = function () {
                submitForm(form);
            };

            if (searchInput) {
                searchInput.addEventListener("input", function () {
                    clearTimeout(debounceTimer);
                    debounceTimer = setTimeout(triggerSubmit, 500);
                });
            }

            autoControls.forEach(function (control) {
                control.addEventListener("change", triggerSubmit);
            });

            if (clearBtn) {
                clearBtn.addEventListener("click", function () {
                    resettableFields.forEach(resetField);
                    triggerSubmit();
                });
            }
        });
    });
})();
