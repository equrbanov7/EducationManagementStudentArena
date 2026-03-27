(function () {
    function normalizeValue(value) {
        return value === null || value === undefined ? "" : String(value);
    }

    function buildOption(option) {
        const clonedOption = option.cloneNode(true);
        clonedOption.selected = false;
        return clonedOption;
    }

    function refreshEnhancedSelect(select) {
        if (!select) {
            return;
        }

        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
            window.EMSBootstrapSelect.refresh(select);
            return;
        }

        if (typeof select._refreshBootstrapSelect === "function") {
            select._refreshBootstrapSelect();
        }
    }

    function syncEnhancedSelect(select) {
        if (!select) {
            return;
        }

        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.sync === "function") {
            window.EMSBootstrapSelect.sync(select);
            return;
        }

        if (typeof select._syncBootstrapSelect === "function") {
            select._syncBootstrapSelect();
        }
    }

    function initPostCategoryPicker(container) {
        if (!container || container.dataset.categoryPickerReady === "true") {
            return container && container._categoryPickerApi ? container._categoryPickerApi : null;
        }

        const rootSelect = container.querySelector("[data-post-category-root]");
        const subcategorySelect = container.querySelector("[data-post-category-sub]");
        const subcategoryHint = container.querySelector("[data-post-category-sub-hint]");

        if (!rootSelect || !subcategorySelect) {
            return null;
        }

        const placeholderOption = subcategorySelect.querySelector('option[value=""]');
        const subcategoryOptions = Array.from(subcategorySelect.querySelectorAll("option[data-parent-id]")).map(buildOption);

        function setSubcategoryHint(hasRootSelection, hasSubcategories) {
            if (!subcategoryHint) {
                return;
            }

            if (!hasRootSelection) {
                subcategoryHint.textContent = "Select a category first.";
                return;
            }

            if (!hasSubcategories) {
                subcategoryHint.textContent = "This category does not have any subcategories yet.";
                return;
            }

            subcategoryHint.textContent = "Optional: choose a more specific subcategory if it matches your post.";
        }

        function syncSubcategories(selectedSubcategoryValue) {
            const normalizedRootValue = normalizeValue(rootSelect.value);
            const normalizedSubcategoryValue = normalizeValue(selectedSubcategoryValue);
            const matchingSubcategories = subcategoryOptions.filter(function (option) {
                return option.dataset.parentId === normalizedRootValue;
            });

            subcategorySelect.innerHTML = "";
            if (placeholderOption) {
                const clonedPlaceholder = placeholderOption.cloneNode(true);
                clonedPlaceholder.selected = !normalizedSubcategoryValue;
                subcategorySelect.appendChild(clonedPlaceholder);
            }

            matchingSubcategories.forEach(function (option) {
                const clonedOption = option.cloneNode(true);
                if (normalizeValue(clonedOption.value) === normalizedSubcategoryValue) {
                    clonedOption.selected = true;
                }
                subcategorySelect.appendChild(clonedOption);
            });

            const hasRootSelection = Boolean(normalizedRootValue);
            const hasSubcategories = matchingSubcategories.length > 0;
            subcategorySelect.disabled = !hasRootSelection || !hasSubcategories;

            if (!hasSubcategories) {
                subcategorySelect.value = "";
            }

            setSubcategoryHint(hasRootSelection, hasSubcategories);
            refreshEnhancedSelect(subcategorySelect);
            syncEnhancedSelect(rootSelect);
        }

        function setValues(rootCategoryId, subcategoryId) {
            rootSelect.value = normalizeValue(rootCategoryId);
            syncSubcategories(subcategoryId);
            syncEnhancedSelect(rootSelect);
        }

        function reset() {
            setValues("", "");
        }

        rootSelect.addEventListener("change", function () {
            syncSubcategories("");
        });

        const api = {
            reset: reset,
            setValues: setValues,
            sync: function () {
                syncSubcategories(subcategorySelect.value);
            },
        };

        container.dataset.categoryPickerReady = "true";
        container._categoryPickerApi = api;
        api.sync();
        return api;
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll(".js-post-category-picker").forEach(function (container) {
            initPostCategoryPicker(container);
        });
    });

    window.createPostCategoryPicker = initPostCategoryPicker;
})();
