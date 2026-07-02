/* Draft persistence, CSRF refresh, and URL step state for the register wizard. */

function getDraftStorage() {
    try {
        return window.localStorage || null;
    } catch (error) {
        return null;
    }
}

function getLegacyDraftStorage() {
    try {
        return window.sessionStorage || null;
    } catch (error) {
        return null;
    }
}

function getCookie(name) {
    // Faza 6.3: mərkəzi EMSCore.getCookie (core/csrf.js); bu fayl "" gözləyir.
    return window.EMSCore.getCookie(name) || "";
}

function syncFreshCsrfToken() {
    if (!registerForm) return;
    var cookieToken = getCookie("csrftoken");
    var tokenInput = registerForm.querySelector('input[name="csrfmiddlewaretoken"]');
    if (cookieToken && tokenInput) {
        tokenInput.value = cookieToken;
    }
}

function migrateLegacySignupDraft() {
    var draftStorage = getDraftStorage();
    var legacyDraftStorage = getLegacyDraftStorage();
    if (!draftStorage || !legacyDraftStorage) return;
    if (draftStorage.getItem(signupDraftStorageKey)) return;

    var legacyDraft = legacyDraftStorage.getItem(signupDraftStorageKey);
    if (!legacyDraft) return;

    draftStorage.setItem(signupDraftStorageKey, legacyDraft);
    legacyDraftStorage.removeItem(signupDraftStorageKey);
}

function buildSignupStateUrl(step, shouldRestoreDraft) {
    var targetUrl = new URL(window.location.href);
    var normalizedStep = normalizeWizardStep(step);

    if (normalizedStep > 1) {
        targetUrl.searchParams.set(signupStepQueryKey, String(normalizedStep));
    } else {
        targetUrl.searchParams.delete(signupStepQueryKey);
    }

    if (shouldRestoreDraft) {
        targetUrl.searchParams.set(signupRestoreDraftQueryKey, "1");
    } else {
        targetUrl.searchParams.delete(signupRestoreDraftQueryKey);
    }

    return targetUrl;
}

function syncLanguageSwitcherTargets(step) {
    if (!languageSwitcherNextInputs.length) return;

    var targetUrl = buildSignupStateUrl(step, false);
    var nextValue = targetUrl.pathname + targetUrl.search + targetUrl.hash;
    languageSwitcherNextInputs.forEach(function (input) {
        input.value = nextValue;
    });
}

function persistWizardStep(step) {
    var normalizedStep = normalizeWizardStep(step);
    var currentUrl = buildSignupStateUrl(normalizedStep, false);

    if (window.history && typeof window.history.replaceState === "function") {
        window.history.replaceState({}, "", currentUrl.toString());
    }

    syncLanguageSwitcherTargets(normalizedStep);
}

function getRequestedWizardStep() {
    var currentUrl = new URL(window.location.href);
    return normalizeWizardStep(currentUrl.searchParams.get(signupStepQueryKey));
}

function shouldRestoreSignupDraft() {
    var currentUrl = new URL(window.location.href);
    return currentUrl.searchParams.get(signupRestoreDraftQueryKey) === "1";
}

function currentWizardStep() {
    var activeStep = document.querySelector(".wizard-step.active");
    if (activeStep && activeStep.dataset.step) {
        return normalizeWizardStep(activeStep.dataset.step);
    }

    var visiblePanel = document.querySelector(".wizard-panel:not([hidden])");
    if (visiblePanel && visiblePanel.id) {
        return normalizeWizardStep(visiblePanel.id.replace("step", ""));
    }

    return 1;
}

function collectSignupDraft() {
    if (!registerForm) return null;

    var values = {};
    var fields = registerForm.querySelectorAll("input[name], select[name], textarea[name]");

    fields.forEach(function (field) {
        if (!field.name || field.disabled) return;
        if (field.type === "password") return;

        if (field.type === "checkbox") {
            values[field.name] = field.checked;
        } else {
            values[field.name] = field.value;
        }
    });

    if (organizationSearchInput) {
        values.organizationSearchInput = organizationSearchInput.value;
        values.organizationSearchNoOrganization = organizationSearchInput.dataset.noOrganizationSelected === "1";
    }

    values.selectedOrgType = _selectedOrgType || getRegistrationMeta().orgType || "";

    return {
        step: currentWizardStep(),
        values: values,
    };
}

function saveSignupDraft() {
    var draftStorage = getDraftStorage();
    if (!draftStorage) return;
    var draft = collectSignupDraft();
    if (!draft) return;
    draftStorage.setItem(signupDraftStorageKey, JSON.stringify(draft));
}

function clearSignupDraft() {
    var draftStorage = getDraftStorage();
    if (draftStorage) {
        draftStorage.removeItem(signupDraftStorageKey);
    }

    var legacyDraftStorage = getLegacyDraftStorage();
    if (legacyDraftStorage) {
        legacyDraftStorage.removeItem(signupDraftStorageKey);
    }
}

function restoreSignupDraft() {
    var draftStorage = getDraftStorage();
    if (!draftStorage) return null;

    var rawDraft = draftStorage.getItem(signupDraftStorageKey);
    if (!rawDraft) return null;

    try {
        var parsedDraft = JSON.parse(rawDraft);
        var values = parsedDraft && parsedDraft.values ? parsedDraft.values : {};
        var restoredSelectFields = [];

        Object.keys(values).forEach(function (name) {
            if (
                name === "organizationSearchInput" ||
                name === "organizationSearchNoOrganization" ||
                name === "selectedOrgType"
            ) {
                return;
            }

            var field = registerForm ? registerForm.elements.namedItem(name) : null;
            if (!field || field.type === "password") return;

            if (field instanceof RadioNodeList) {
                Array.prototype.forEach.call(field, function (radio) {
                    radio.checked = radio.value === values[name];
                });
                return;
            }

            if (field.type === "checkbox") {
                field.checked = Boolean(values[name]);
            } else {
                field.value = values[name];
                if (field.tagName === "SELECT") {
                    restoredSelectFields.push(field);
                }
            }
        });

        if (organizationSearchInput && typeof values.organizationSearchInput === "string") {
            organizationSearchInput.value = values.organizationSearchInput;
            organizationSearchInput.dataset.selectedValue = organizationSelect ? organizationSelect.value : "";
            organizationSearchInput.dataset.noOrganizationSelected = values.organizationSearchNoOrganization
                ? "1"
                : "";
        }

        if (values.selectedOrgType && (!registrationTypeSelect || !registrationTypeSelect.value)) {
            showPersonaStep(values.selectedOrgType);
        }

        clearUnsupportedIndividualSelection();
        updateStep2State();
        syncStep2CardSelection();
        restoredSelectFields.forEach(function (field) {
            field.dispatchEvent(new Event("change", { bubbles: true }));
        });

        if (organizationSelect && values.join_organization !== undefined) {
            populateJoinOrganizationOptions("");
            organizationSelect.value = values.join_organization;
            syncSearchInputWithSelectedOrganization();
            if (organizationSearchInput && typeof values.organizationSearchInput === "string") {
                organizationSearchInput.value = values.organizationSearchInput;
                organizationSearchInput.dataset.noOrganizationSelected = values.organizationSearchNoOrganization
                    ? "1"
                    : "";
            }
        }

        if (privacyCheckbox && values.accept_privacy_policy !== undefined) {
            privacyCheckbox.checked = Boolean(values.accept_privacy_policy);
            syncPrivacyConsentState();
        }

        refreshOrganizationChoiceUI();
        updateSelectionSummary();
        return parsedDraft;
    } catch (error) {
        clearSignupDraft();
        return null;
    }
}

function exposeRegisterWizardDraftHooks() {
    window.persistRegisterWizardStep = persistWizardStep;
    window.saveRegisterSignupDraft = saveSignupDraft;
    window.resolveRegisterWizardStep = function (step, direction) {
        var normalizedStep = normalizeWizardStep(step);
        if (normalizedStep === 3 && !shouldShowInstitutionStep()) {
            return direction === "back" ? 2 : 4;
        }
        return normalizedStep;
    };
}
