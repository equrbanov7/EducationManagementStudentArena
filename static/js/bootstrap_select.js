(function () {
    function normalizeValue(value) {
        return value === null || value === undefined ? "" : String(value);
    }

    function enhanceBootstrapSelect(select) {
        if (!select) {
            return null;
        }

        if (select.dataset.bootstrapSelectReady === "true") {
            return select._bootstrapSelectApi || null;
        }

        var wrapper = select.closest(".bootstrap-single-select");
        if (!wrapper) {
            return null;
        }

        select.dataset.bootstrapSelectReady = "true";
        select.classList.add("is-enhanced");

        var dropdown = document.createElement("div");
        dropdown.className = "dropdown bootstrap-single-select__dropdown";

        var toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "btn btn-outline-secondary dropdown-toggle bootstrap-single-select__toggle";
        toggle.setAttribute("data-bs-toggle", "dropdown");
        toggle.setAttribute("data-bs-display", "static");
        toggle.setAttribute("aria-expanded", "false");

        var label = document.createElement("span");
        label.className = "bootstrap-single-select__label-text";
        toggle.appendChild(label);

        var caret = document.createElement("span");
        caret.className = "bootstrap-single-select__caret";
        caret.innerHTML = '<i class="fas fa-chevron-down" aria-hidden="true"></i>';
        toggle.appendChild(caret);

        var menu = document.createElement("div");
        menu.className = "dropdown-menu bootstrap-single-select__menu";

        dropdown.appendChild(toggle);
        dropdown.appendChild(menu);
        select.insertAdjacentElement("afterend", dropdown);

        function syncToggleState() {
            var selectedOption = select.options[select.selectedIndex] || select.options[0];
            var hasValue = Boolean(select.value);

            label.textContent = selectedOption ? selectedOption.textContent : "";
            toggle.classList.toggle("is-placeholder", !hasValue);
            toggle.classList.toggle("is-disabled", select.disabled);
            toggle.disabled = select.disabled;
            toggle.setAttribute("aria-disabled", select.disabled ? "true" : "false");
        }

        function syncSelectedState() {
            menu.querySelectorAll(".bootstrap-single-select__option").forEach(function (button) {
                var isSelected = normalizeValue(button.dataset.value) === normalizeValue(select.value);
                button.classList.toggle("is-selected", isSelected);
                button.setAttribute("aria-pressed", isSelected ? "true" : "false");
            });
        }

        function buildMenu() {
            menu.innerHTML = "";

            Array.prototype.forEach.call(select.options, function (option, index) {
                var optionButton = document.createElement("button");
                var isPlaceholder = index === 0 && !option.value;

                optionButton.type = "button";
                optionButton.className = "dropdown-item bootstrap-single-select__option";
                optionButton.dataset.value = option.value;
                optionButton.disabled = option.disabled;
                optionButton.classList.toggle("is-placeholder", isPlaceholder);

                var optionLabel = document.createElement("span");
                optionLabel.className = "bootstrap-single-select__option-label";
                optionLabel.textContent = option.textContent;
                optionButton.appendChild(optionLabel);

                var optionCheck = document.createElement("span");
                optionCheck.className = "bootstrap-single-select__option-check";
                optionCheck.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i>';
                optionButton.appendChild(optionCheck);

                optionButton.addEventListener("click", function () {
                    if (optionButton.disabled) {
                        return;
                    }

                    select.value = option.value;
                    select.dispatchEvent(new Event("change", { bubbles: true }));

                    if (window.bootstrap && window.bootstrap.Dropdown) {
                        window.bootstrap.Dropdown.getOrCreateInstance(toggle).hide();
                    }
                });

                menu.appendChild(optionButton);
            });

            syncSelectedState();
            syncToggleState();
        }

        function refresh() {
            buildMenu();
        }

        function sync() {
            syncSelectedState();
            syncToggleState();
        }

        select.addEventListener("change", sync);

        select._refreshBootstrapSelect = refresh;
        select._syncBootstrapSelect = sync;

        var api = {
            refresh: refresh,
            sync: sync,
        };

        select._bootstrapSelectApi = api;
        refresh();

        return api;
    }

    function initBootstrapSelects(root) {
        var scope = root || document;
        scope.querySelectorAll("[data-bootstrap-select]").forEach(function (select) {
            enhanceBootstrapSelect(select);
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        initBootstrapSelects(document);
    });

    // AJAX section swap-dan sonra avtomatik re-init.
    document.addEventListener("profile:section:loaded", function (event) {
        var panel = event.detail && event.detail.panel ? event.detail.panel : document;
        initBootstrapSelects(panel);
    });

    window.EMSBootstrapSelect = {
        enhance: enhanceBootstrapSelect,
        init: initBootstrapSelects,
        refresh: function (select) {
            if (!select) {
                return;
            }

            if (typeof select._refreshBootstrapSelect === "function") {
                select._refreshBootstrapSelect();
                return;
            }

            enhanceBootstrapSelect(select);
        },
        sync: function (select) {
            if (select && typeof select._syncBootstrapSelect === "function") {
                select._syncBootstrapSelect();
            }
        },
    };
})();
