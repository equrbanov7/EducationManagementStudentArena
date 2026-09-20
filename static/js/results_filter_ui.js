(function () {
    // Sahib 2026-09-21: filtr dəyişəndə nəticə kartı spinner əvəzinə SKELETON göstərir
    // (`[data-results-skeleton-target]` — səhifə yenidən yüklənənə qədər).
    function showSkeleton() {
        var target = document.querySelector("[data-results-skeleton-target]");
        if (!target) return;
        var rows = "";
        for (var i = 0; i < 6; i += 1) {
            rows += '<div class="ems-skelrow"><div class="skeleton-line skeleton-line--lg"></div><div class="skeleton-line"></div>' +
                '<div class="skeleton-line skeleton-line--sm"></div><div class="skeleton-line skeleton-line--sm"></div></div>';
        }
        target.setAttribute("aria-busy", "true");
        target.innerHTML = '<div class="skeleton ems-results-skeleton" aria-hidden="true">' + rows + "</div>";
    }

    function submitForm(form) {
        if (!form) return;
        showSkeleton();
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
