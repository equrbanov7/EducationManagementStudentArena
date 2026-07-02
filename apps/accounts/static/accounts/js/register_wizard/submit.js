/* Navigation, submit validation, and final initialisation for register wizard. */

function validateStudentGroupNumber() {
    var selection = currentSelection();
    var isStudent = selection.mode === "student_join";
    if (!groupNumberInput || !isStudent) {
        clearInlineFieldError(groupNumberInput);
        return true;
    }

    if ((groupNumberInput.value || "").trim()) {
        clearInlineFieldError(groupNumberInput);
        return true;
    }

    setInlineFieldError(
        groupNumberInput,
        tr("group_number_required", "Group / class is required for students.")
    );
    return false;
}

function initRegisterWizardNavigation() {
    document.querySelectorAll("[data-wizard-next]").forEach(function (button) {
        button.addEventListener("click", function (event) {
            event.preventDefault();
            if (button.disabled || button.getAttribute("aria-disabled") === "true") return;

            var nextStep = button.getAttribute("data-wizard-next");
            wizardNext(nextStep, "next");
        });
    });

    document.querySelectorAll("[data-wizard-back]").forEach(function (button) {
        button.addEventListener("click", function (event) {
            event.preventDefault();
            if (button.disabled || button.getAttribute("aria-disabled") === "true") return;

            var previousStep = button.getAttribute("data-wizard-back");
            wizardBack(previousStep);
        });
    });
}

function initRegisterWizardPrivacyAndSubmit() {
    if (privacyCheckbox) {
        privacyCheckbox.addEventListener("change", function () {
            if (privacyCheckbox.checked) {
                clearPrivacyErrors();
            }
            syncPrivacyConsentState();
        });
        syncPrivacyConsentState();
    }

    if (privacyAcceptButton && privacyCheckbox) {
        privacyAcceptButton.addEventListener("click", function () {
            privacyCheckbox.checked = true;
            privacyCheckbox.dispatchEvent(new Event("change", { bubbles: true }));
            if (privacyModalElement && window.bootstrap && window.bootstrap.Modal) {
                window.bootstrap.Modal.getOrCreateInstance(privacyModalElement).hide();
            }
            privacyCheckbox.focus();
        });
    }

    if (registerForm) {
        registerForm.addEventListener("submit", function () {
            syncFreshCsrfToken();
            saveSignupDraft();
        });
    }

    if (registerForm && privacyCheckbox) {
        registerForm.addEventListener("submit", function (event) {
            if (privacyCheckbox.checked) return;

            event.preventDefault();
            wizardNext(4);

            if (privacyClientError) {
                privacyClientError.textContent = tr(
                    "privacy_policy_required",
                    "Davam etmək üçün məxfilik siyasətini qəbul edin."
                );
                privacyClientError.hidden = false;
            }

            if (privacyCard) {
                privacyCard.classList.add("is-invalid");
            }

            privacyCheckbox.focus();
        });
    }

    if (registerForm) {
        registerForm.addEventListener("submit", function (event) {
            if (privacyCheckbox && !privacyCheckbox.checked) return;
            if (validateStudentGroupNumber()) return;

            event.preventDefault();
            wizardNext(4);
            if (groupNumberInput) {
                groupNumberInput.focus();
            }
        });
    }

    if (registerForm) {
        registerForm.addEventListener("submit", function (event) {
            if (event.defaultPrevented) return;
            if (!isJoinMode(currentSelection().mode)) return;
            if (joinChoiceInput && joinChoiceInput.value) return;

            event.preventDefault();
            wizardNext(3);
            showOrganizationSearchError();
            setStep3ContinueEnabled(false);
            if (organizationSearchInput) organizationSearchInput.focus();
        });
    }

    if (registerForm && registerSubmitBtn) {
        registerForm.addEventListener("submit", function (event) {
            if (event.defaultPrevented) return;
            if (registerForm.dataset.submitting === "1") {
                event.preventDefault();
                return;
            }
            registerForm.dataset.submitting = "1";
            registerSubmitBtn.disabled = true;
            registerSubmitBtn.classList.add("is-loading");
            var spinner = registerSubmitBtn.querySelector(".register-submit-btn__spinner");
            if (spinner) spinner.hidden = false;
        });
    }

    if (groupNumberInput) {
        groupNumberInput.addEventListener("input", function () {
            if ((groupNumberInput.value || "").trim()) {
                clearInlineFieldError(groupNumberInput);
            }
        });
    }

    if (registerForm) {
        registerForm.addEventListener("input", function (event) {
            if (event.target && event.target.type === "password") return;
            updateSelectionSummary();
            saveSignupDraft();
        });

        registerForm.addEventListener("change", function (event) {
            if (event.target && event.target.type === "password") return;
            updateSelectionSummary();
            saveSignupDraft();
        });
    }

    languageSwitcherForms.forEach(function (form) {
        form.addEventListener("submit", function () {
            saveSignupDraft();

            var nextInput = form.querySelector('input[name="next"]');
            if (!nextInput) return;

            var targetUrl = buildSignupStateUrl(currentWizardStep(), true);
            nextInput.value = targetUrl.pathname + targetUrl.search + targetUrl.hash;
        });
    });
}

function initRegisterWizardErrorJumps() {
    document.querySelectorAll("[data-error-jump]").forEach(function (link) {
        link.addEventListener("click", function (event) {
            event.preventDefault();
            var targetId = link.getAttribute("data-error-jump");
            var field = document.getElementById(targetId);
            if (!field) return;
            wizardNext(stepNumberForElement(field));
            focusWithoutScroll(field);
            scrollIntoViewSafely(field, "center");
        });
    });
}

function revealInitialErrorOrRestoreDraft() {
    var firstErrorField = document.querySelector(".register-field-error:not([hidden])");
    var hasErrors = firstErrorField || document.querySelector(".register-global-errors");
    if (hasErrors) {
        var targetStep = firstErrorField ? stepNumberForElement(firstErrorField) : 4;
        wizardNext(targetStep);
        if (targetStep === 2) {
            if (step2a) step2a.hidden = true;
            if (step2b) step2b.hidden = false;
        }
        focusErrorSummaryOrField();
        return;
    }

    var requestedStep = getRequestedWizardStep();
    var restoredDraft = restoreSignupDraft();
    var restoredStep = restoredDraft && restoredDraft.step ? normalizeWizardStep(restoredDraft.step) : 1;
    syncLanguageSwitcherTargets(requestedStep > 1 ? requestedStep : restoredStep);
    if (requestedStep > 1) {
        wizardNext(requestedStep);
    } else if (restoredStep > 1) {
        wizardNext(restoredStep);
    } else if (shouldRestoreSignupDraft()) {
        persistWizardStep(1);
    }
}

function initRegisterWizardSubmitModule() {
    initRegisterWizardNavigation();
    initRegisterWizardPrivacyAndSubmit();
    initRegisterWizardErrorJumps();
}
