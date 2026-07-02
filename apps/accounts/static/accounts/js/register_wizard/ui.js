/* Shared UI helpers for the registration wizard. */

function syncEnhancedSelect(select) {
    if (select && typeof select._syncEnhancedSelect === "function") {
        select._syncEnhancedSelect();
    }
}

function enhanceBootstrapSelect(select) {
    if (!select || select.dataset.registerEnhancedReady === "1") return;

    var field = select.closest(".register-form-field");
    if (!field) return;

    select.dataset.registerEnhancedReady = "1";
    select.classList.add("is-enhanced");

    var dropdown = document.createElement("div");
    dropdown.className = "dropdown register-bootstrap-select";

    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "btn btn-outline-secondary dropdown-toggle register-bootstrap-select__toggle";
    toggle.setAttribute("data-bs-toggle", "dropdown");
    toggle.setAttribute("data-bs-display", "static");
    toggle.setAttribute("aria-expanded", "false");
    if (select.id) {
        toggle.id = select.id + "__toggle";
    }

    var toggleLabel = document.createElement("span");
    toggleLabel.className = "register-bootstrap-select__label";
    toggle.appendChild(toggleLabel);

    var toggleCaret = document.createElement("span");
    toggleCaret.className = "register-bootstrap-select__caret";
    toggleCaret.innerHTML = '<i class="fas fa-chevron-down" aria-hidden="true"></i>';
    toggle.appendChild(toggleCaret);

    var menu = document.createElement("div");
    menu.className = "dropdown-menu register-bootstrap-select__menu";
    if (toggle.id) {
        menu.setAttribute("aria-labelledby", toggle.id);
    }

    var optionButtons = [];
    Array.prototype.forEach.call(select.options, function (option) {
        var optionButton = document.createElement("button");
        optionButton.type = "button";
        optionButton.className = "dropdown-item register-bootstrap-select__option";
        optionButton.dataset.value = option.value;
        optionButton.disabled = option.disabled;

        var optionText = document.createElement("span");
        optionText.className = "register-bootstrap-select__option-label";
        optionText.textContent = option.textContent;
        optionButton.appendChild(optionText);

        var optionCheck = document.createElement("span");
        optionCheck.className = "register-bootstrap-select__option-check";
        optionCheck.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i>';
        optionButton.appendChild(optionCheck);

        optionButton.addEventListener("click", function () {
            if (optionButton.disabled) return;

            select.value = option.value;
            select.dispatchEvent(new Event("change", { bubbles: true }));

            if (window.bootstrap && window.bootstrap.Dropdown) {
                window.bootstrap.Dropdown.getOrCreateInstance(toggle).hide();
            }
            toggle.focus();
        });

        optionButtons.push(optionButton);
        menu.appendChild(optionButton);
    });

    dropdown.appendChild(toggle);
    dropdown.appendChild(menu);
    select.insertAdjacentElement("afterend", dropdown);

    select._syncEnhancedSelect = function () {
        var selectedOption = select.options[select.selectedIndex] || select.options[0];
        var hasValue = Boolean(select.value);
        var hasError = Boolean(field.querySelector(".register-field-error"));

        toggleLabel.textContent = selectedOption ? selectedOption.textContent : "";
        toggle.classList.toggle("is-placeholder", !hasValue);
        toggle.classList.toggle("is-invalid", hasError);

        optionButtons.forEach(function (button) {
            var isSelected = button.dataset.value === select.value;
            button.classList.toggle("is-selected", isSelected);
            button.setAttribute("aria-pressed", isSelected ? "true" : "false");
        });
    };

    select.addEventListener("change", function () {
        syncEnhancedSelect(select);
    });

    enhancedSelects.push(select);
    syncEnhancedSelect(select);
}

function setInlineFieldError(input, message) {
    if (!input) return;

    var field = input.closest(".register-form-field");
    var errorEl = field ? field.querySelector(".register-field-error") : null;
    if (!field) return;

    if (!errorEl) {
        errorEl = document.createElement("div");
        errorEl.className = "register-field-error";
        field.appendChild(errorEl);
    }

    errorEl.textContent = message;
    errorEl.hidden = false;
    input.classList.add("is-invalid");
    input.setAttribute("aria-invalid", "true");
}

function clearInlineFieldError(input) {
    if (!input) return;

    var field = input.closest(".register-form-field");
    var errorEl = field ? field.querySelector(".register-field-error") : null;
    if (errorEl) {
        errorEl.hidden = true;
        errorEl.textContent = "";
    }
    input.classList.remove("is-invalid");
    input.removeAttribute("aria-invalid");
}

function syncPrivacyConsentState() {
    if (!privacyCheckbox || !privacyCard) return;
    privacyCard.classList.toggle("is-accepted", privacyCheckbox.checked);
    if (privacyCheckbox.checked) {
        privacyCard.classList.remove("is-invalid");
    }
}

function clearPrivacyErrors() {
    if (privacyClientError) {
        privacyClientError.hidden = true;
        privacyClientError.textContent = "";
    }
    if (privacyServerError) {
        privacyServerError.hidden = true;
    }
    if (privacyCard) {
        privacyCard.classList.remove("is-invalid");
    }
}

function noOrganizationAffiliationLabel() {
    return tr("no_organization_affiliation", "Hazırda heç bir təşkilata aid deyiləm");
}

function isNoOrganizationSelected() {
    return organizationSearchInput && organizationSearchInput.dataset.noOrganizationSelected === "1";
}

function clearNoOrganizationSelection() {
    if (!organizationSearchInput) return;
    organizationSearchInput.dataset.noOrganizationSelected = "";
}

function updateSelectionSummary() {
    if (!signupSummary) return;

    var meta = getRegistrationMeta();
    var selection = currentSelection();
    var countryLabel = selectedOptionText(countrySelect);
    var accountTypeLabel = meta.orgType
        ? cardTitleText(orgTypeCards, '.register-persona-card[data-org-type="' + meta.orgType + '"]')
        : "";
    var roleLabel = meta.role
        ? cardTitleText(roleCards, '.register-persona-role-card[data-role="' + meta.role + '"]')
        : "";
    var organizationLabel = "";

    if (selection.mode === "organization_create" && organizationNameInput) {
        organizationLabel = organizationNameInput.value.trim();
    } else if (isJoinMode(selection.mode)) {
        if (isNoOrganizationSelected()) {
            organizationLabel = noOrganizationAffiliationLabel();
        } else {
            var hasSelectedOrganization =
                organizationSearchInput && organizationSearchInput.dataset.selectedValue
                    ? organizationSearchInput.dataset.selectedValue
                    : organizationSelect
                      ? organizationSelect.value
                      : "";
            organizationLabel = hasSelectedOrganization
                ? selectedOptionText(organizationSelect) ||
                  (organizationSearchInput ? organizationSearchInput.value.trim() : "")
                : "";
        }
    }

    if (signupSummaryCountry) {
        signupSummaryCountry.textContent = countryLabel || "-";
    }

    if (signupSummaryAccountType) {
        signupSummaryAccountType.textContent = accountTypeLabel || "-";
    }

    if (signupSummaryRole) {
        signupSummaryRole.textContent = roleLabel || "-";
    }

    if (signupSummaryOrganization && signupSummaryOrganizationItem) {
        signupSummaryOrganization.textContent = organizationLabel || "-";
        signupSummaryOrganizationItem.hidden = !organizationLabel;
    }

    signupSummary.hidden = !(countryLabel || accountTypeLabel || roleLabel || organizationLabel);
}

function normalizeWizardStep(step) {
    var parsed = parseInt(step, 10);
    if (parsed >= 1 && parsed <= 4) {
        return parsed;
    }
    return 1;
}

function stepNumberForElement(element) {
    var panel = element ? element.closest(".wizard-panel") : null;
    if (panel && panel.id) {
        return normalizeWizardStep(panel.id.replace("step", ""));
    }
    return 4;
}

function scrollIntoViewSafely(element, block) {
    if (!element || typeof element.scrollIntoView !== "function") return;
    try {
        element.scrollIntoView({ block: block || "center", inline: "nearest" });
    } catch (error) {
        element.scrollIntoView();
    }
}

function focusWithoutScroll(element) {
    if (!element || typeof element.focus !== "function") return;
    try {
        element.focus({ preventScroll: true });
    } catch (error) {
        element.focus();
    }
}

function focusErrorSummaryOrField() {
    var summary = document.getElementById("registerErrorSummary");
    if (summary) {
        focusWithoutScroll(summary);
        scrollIntoViewSafely(summary, "start");
        return;
    }
    scrollIntoViewSafely(
        document.querySelector(".register-field-error:not([hidden]), .register-global-errors"),
        "center"
    );
}

function wizardNext(step, direction) {
    var normalizedStep = Math.max(1, Math.min(4, parseInt(step, 10) || 1));
    if (typeof window.resolveRegisterWizardStep === "function") {
        normalizedStep = window.resolveRegisterWizardStep(normalizedStep, direction || "next");
    }
    var panels = document.querySelectorAll(".wizard-panel");
    panels.forEach(function (panel) {
        panel.hidden = true;
    });

    var target = document.getElementById("step" + normalizedStep);
    if (target) target.hidden = false;

    var steps = document.querySelectorAll(".wizard-step");
    steps.forEach(function (item) {
        var currentStep = parseInt(item.dataset.step, 10);
        item.classList.toggle("active", currentStep === normalizedStep);
        item.classList.toggle("completed", currentStep < normalizedStep);
    });

    if (typeof window.persistRegisterWizardStep === "function") {
        window.persistRegisterWizardStep(normalizedStep);
    }

    if (typeof window.saveRegisterSignupDraft === "function") {
        window.saveRegisterSignupDraft();
    }
}

function wizardBack(step) {
    wizardNext(step, "back");
}

window.wizardNext = wizardNext;
window.wizardBack = wizardBack;
