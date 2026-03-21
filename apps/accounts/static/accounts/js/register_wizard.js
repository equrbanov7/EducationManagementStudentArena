/**
 * Registration wizard - multi-step form navigation.
 * Steps:
 * 1) Country
 * 2) Registration type + organization details / join organization
 * 3) Account details
 */
document.addEventListener("DOMContentLoaded", function () {
    var i18n = window.REGISTER_I18N || {};

    function tr(key, fallback) {
        return i18n[key] || fallback;
    }

    var registrationTypeMap = {
        individual: { mode: "individual", orgType: "individual" },
        school: { mode: "organization_create", orgType: "school" },
        university: { mode: "organization_create", orgType: "university" },
        course_center: { mode: "organization_create", orgType: "course_center" },
        school_student: { mode: "student_join", orgType: "school" },
        university_student: { mode: "student_join", orgType: "university" },
        course_student: { mode: "student_join", orgType: "course_center" },
    };

    var countrySelect = document.getElementById("id_country");
    var registrationTypeSelect = document.getElementById("id_organization_type");

    var individualAccountInfo = document.getElementById("individualAccountInfo");
    var orgCreateFields = document.getElementById("orgCreateFields");
    var studentJoinFields = document.getElementById("studentJoinFields");

    var organizationNameInput = document.getElementById("id_institution_not_listed_name");
    var organizationNameLabel = document.getElementById("organizationNameLabel");
    var organizationNameHelp = document.getElementById("organizationNameHelp");

    var orgIdentifierField = document.getElementById("orgIdentifierField");
    var orgIdentifierInput = document.getElementById("id_organization_identifier");
    var orgIdentifierLabel = document.getElementById("orgIdentifierLabel");
    var orgIdentifierHelp = document.getElementById("orgIdentifierHelp");
    var licenseIdentifierInput = document.getElementById("id_organization_license_identifier");

    var organizationSearchInput = document.getElementById("organizationSearchInput");
    var organizationSearchLabel = document.getElementById("organizationSearchLabel");
    var organizationSearchList = document.getElementById("organizationSearchList");
    var studentJoinHint = document.getElementById("studentJoinHint");
    var organizationSelect = document.getElementById("id_join_organization");
    var organizationSearchDebounceTimer = null;

    var initialRoleField = document.getElementById("initialRoleField");
    var autoRoleInfoField = document.getElementById("autoRoleInfoField");
    var autoRoleInfoText = document.getElementById("autoRoleInfoText");
    var initialRoleSelect = document.getElementById("id_initial_role");
    var registerForm = document.getElementById("registerForm");
    var privacyCheckbox = document.getElementById("id_accept_privacy_policy");
    var privacyCard = document.getElementById("privacyConsentCard");
    var privacyClientError = document.getElementById("privacyConsentClientError");
    var privacyServerError = document.getElementById("privacyConsentServerError");
    var privacyAcceptButton = document.querySelector("[data-accept-privacy-policy]");
    var privacyModalElement = document.getElementById("privacyPolicyModal");
    var languageSwitcherForms = document.querySelectorAll(".language-switcher__form");
    var languageSwitcherNextInputs = document.querySelectorAll('.language-switcher__form input[name="next"]');
    var signupStepQueryKey = "signup_step";
    var signupRestoreDraftQueryKey = "signup_restore";
    var signupDraftStorageKey = "accounts.register.draft";

    var lookupData = window.SIGNUP_LOOKUP_DATA || {};
    var organizations = lookupData.organizations || [];
    var enhancedSelects = [];

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

    function currentSelection() {
        var selected = registrationTypeSelect ? registrationTypeSelect.value : "individual";
        return registrationTypeMap[selected] || registrationTypeMap.individual;
    }

    function hideOrganizationSearchList() {
        if (organizationSearchList) organizationSearchList.hidden = true;
    }

    function organizationOptionLabel(organization) {
        if (!organization) return "";
        return organization.country ? organization.name + " (" + organization.country + ")" : organization.name;
    }

    function filteredOrganizations(searchText) {
        var selectedCountry = (countrySelect ? countrySelect.value : "").toUpperCase();
        var selection = currentSelection();
        var search = (searchText || "").toLowerCase().trim();

        return organizations.filter(function (organization) {
            if (organization.org_type !== selection.orgType) return false;
            if (selectedCountry && organization.country_code && organization.country_code !== selectedCountry) return false;
            if (search && !organization.name.toLowerCase().includes(search)) return false;
            return true;
        });
    }

    function populateJoinOrganizationOptions(searchText) {
        if (!organizationSelect) return;
        var previousValue = organizationSelect.value;
        var options = filteredOrganizations(searchText);

        organizationSelect.innerHTML = '<option value="">' + tr("select_empty_organization", "Təşkilat seçin") + "</option>";
        options.forEach(function (organization) {
            var option = document.createElement("option");
            option.value = String(organization.id);
            option.textContent = organizationOptionLabel(organization);
            organizationSelect.appendChild(option);
        });

        if (options.some(function (item) { return String(item.id) === previousValue; })) {
            organizationSelect.value = previousValue;
        }
    }

    function renderOrganizationSearchList(searchText) {
        if (!organizationSearchList || !organizationSearchInput) return;
        var options = filteredOrganizations(searchText);
        organizationSearchList.innerHTML = "";

        if (!options.length) {
            var empty = document.createElement("div");
            empty.className = "register-search-empty";
            empty.textContent = tr("no_results", "Nəticə tapılmadı");
            organizationSearchList.appendChild(empty);
            organizationSearchList.hidden = false;
            return;
        }

        options.forEach(function (organization) {
            var optionButton = document.createElement("button");
            optionButton.type = "button";
            optionButton.className = "register-search-option";
            optionButton.textContent = organizationOptionLabel(organization);
            optionButton.dataset.value = String(organization.id);
            if (organizationSelect && organizationSelect.value === String(organization.id)) {
                optionButton.classList.add("is-selected");
            }

            optionButton.addEventListener("click", function () {
                if (organizationSelect) {
                    organizationSelect.value = String(organization.id);
                }
                organizationSearchInput.value = organizationOptionLabel(organization);
                organizationSearchInput.dataset.selectedValue = String(organization.id);
                hideOrganizationSearchList();
            });
            organizationSearchList.appendChild(optionButton);
        });

        organizationSearchList.hidden = false;
    }

    function syncSearchInputWithSelectedOrganization() {
        if (!organizationSearchInput || !organizationSelect) return;
        var selectedOption = organizationSelect.options[organizationSelect.selectedIndex];
        if (selectedOption && selectedOption.value) {
            organizationSearchInput.value = selectedOption.textContent;
            organizationSearchInput.dataset.selectedValue = selectedOption.value;
        } else {
            organizationSearchInput.dataset.selectedValue = "";
        }
    }

    function updateCreateFieldsCopy(orgType) {
        if (!organizationNameLabel || !organizationNameInput || !orgIdentifierLabel || !orgIdentifierHelp) {
            return;
        }

        if (orgType === "university") {
            organizationNameLabel.textContent = tr(
                "label_university_manual",
                "Universitet adı (Siyahıda yoxdur / Digər)"
            );
            organizationNameInput.placeholder = tr("placeholder_university_manual", "Universitet adını daxil edin...");
            orgIdentifierLabel.textContent = tr("label_university_identifier", "Universitet kodu / identifikatoru");
            orgIdentifierHelp.textContent = tr("help_identifier_required", "Universitet üçün bu sahə məcburidir.");
        } else if (orgType === "school") {
            organizationNameLabel.textContent = tr("label_school_manual", "Məktəb adı (Siyahıda yoxdur / Digər)");
            organizationNameInput.placeholder = tr(
                "placeholder_school_manual",
                "Məktəb siyahıda yoxdursa adını daxil edin..."
            );
            orgIdentifierLabel.textContent = tr("label_school_identifier", "Məktəb nömrəsi / kodu (opsional)");
            orgIdentifierHelp.textContent = tr("help_identifier_optional", "Bu sahə opsionaldır.");
        } else if (orgType === "course_center") {
            organizationNameLabel.textContent = tr(
                "label_course_center_manual",
                "Kurs mərkəzi adı (Siyahıda yoxdur / Digər)"
            );
            organizationNameInput.placeholder = tr(
                "placeholder_course_center_manual",
                "Kurs mərkəzi siyahıda yoxdursa adını daxil edin..."
            );
            orgIdentifierLabel.textContent = tr("label_course_center_identifier", "Mərkəz identifikatoru (opsional)");
            orgIdentifierHelp.textContent = tr("help_identifier_optional", "Bu sahə opsionaldır.");
        } else {
            organizationNameLabel.textContent = tr(
                "label_institution_manual_default",
                "Müəssisə adı (Siyahıda yoxdur / Digər)"
            );
            organizationNameInput.placeholder = tr("placeholder_search_default", "Müəssisə axtar...");
            orgIdentifierLabel.textContent = tr("label_identifier_default", "Rəsmi identifikator / kod");
            orgIdentifierHelp.textContent = tr("help_identifier_optional", "Bu sahə opsionaldır.");
        }
    }

    function updateStudentJoinCopy(orgType) {
        if (!organizationSearchLabel || !organizationSearchInput || !studentJoinHint) return;
        var selectedCountry = (countrySelect ? countrySelect.value : "").toUpperCase();

        if (orgType === "university") {
            organizationSearchLabel.textContent = tr("label_search_university", "Universitet axtar");
            organizationSearchInput.placeholder = tr("placeholder_search_university", "Universitet axtar...");
            studentJoinHint.textContent =
                selectedCountry === "AZ"
                    ? tr("hint_university_az", "Azərbaycandakı universitetləri siyahıdan seçə bilərsiniz.")
                    : tr("hint_university_global", "Ölkənizə uyğun universitet siyahısından seçim edin.");
        } else if (orgType === "school") {
            organizationSearchLabel.textContent = tr("label_search_school", "Məktəb axtar (ad və ya nömrə)");
            organizationSearchInput.placeholder = tr(
                "placeholder_search_school",
                "Məktəb adı və ya nömrəsi axtar..."
            );
            studentJoinHint.textContent = tr("hint_school", "Məktəbinizi siyahıdan seçin və ya əl ilə daxil edin.");
        } else if (orgType === "course_center") {
            organizationSearchLabel.textContent = tr("label_search_course_center", "Kurs mərkəzi axtar");
            organizationSearchInput.placeholder = tr("placeholder_search_course_center", "Kurs mərkəzi axtar...");
            studentJoinHint.textContent = tr(
                "hint_course_center",
                "Kurs mərkəzini siyahıdan seçin və ya əl ilə daxil edin."
            );
        } else {
            organizationSearchLabel.textContent = tr("label_search_default", "Müəssisə axtar");
            organizationSearchInput.placeholder = tr("placeholder_search_default", "Müəssisə axtar...");
            studentJoinHint.textContent = "";
        }
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

    function normalizeWizardStep(step) {
        var parsed = parseInt(step, 10);
        if (parsed >= 1 && parsed <= 3) {
            return parsed;
        }
        return 1;
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
        }

        return {
            step: currentWizardStep(),
            values: values,
        };
    }

    function saveSignupDraft() {
        if (!window.sessionStorage) return;
        var draft = collectSignupDraft();
        if (!draft) return;
        window.sessionStorage.setItem(signupDraftStorageKey, JSON.stringify(draft));
    }

    function clearSignupDraft() {
        if (!window.sessionStorage) return;
        window.sessionStorage.removeItem(signupDraftStorageKey);
    }

    function restoreSignupDraft() {
        if (!window.sessionStorage) return;

        var rawDraft = window.sessionStorage.getItem(signupDraftStorageKey);
        if (!rawDraft) return;

        try {
            var parsedDraft = JSON.parse(rawDraft);
            var values = parsedDraft && parsedDraft.values ? parsedDraft.values : {};
            var restoredSelectFields = [];

            Object.keys(values).forEach(function (name) {
                if (name === "organizationSearchInput") return;

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
            }

            updateStep2State();
            restoredSelectFields.forEach(function (field) {
                field.dispatchEvent(new Event("change", { bubbles: true }));
            });

            if (organizationSelect && values.join_organization !== undefined) {
                organizationSelect.value = values.join_organization;
                syncSearchInputWithSelectedOrganization();
                if (organizationSearchInput && typeof values.organizationSearchInput === "string") {
                    organizationSearchInput.value = values.organizationSearchInput;
                }
            }

            if (privacyCheckbox && values.accept_privacy_policy !== undefined) {
                privacyCheckbox.checked = Boolean(values.accept_privacy_policy);
                syncPrivacyConsentState();
            }
        } catch (error) {
            clearSignupDraft();
            return;
        }

        clearSignupDraft();
    }

    window.persistRegisterWizardStep = persistWizardStep;

    [countrySelect, registrationTypeSelect].forEach(function (select) {
        enhanceBootstrapSelect(select);
    });

    function updateStep2State() {
        var selection = currentSelection();
        var isIndividual = selection.mode === "individual";
        var isCreatorMode = selection.mode === "organization_create";
        var isStudentJoinMode = selection.mode === "student_join";

        if (individualAccountInfo) individualAccountInfo.hidden = !isIndividual;
        if (orgCreateFields) orgCreateFields.hidden = !isCreatorMode;
        if (studentJoinFields) studentJoinFields.hidden = !isStudentJoinMode;
        if (orgIdentifierField) orgIdentifierField.hidden = !isCreatorMode;
        if (initialRoleField) initialRoleField.hidden = true;
        if (autoRoleInfoField) autoRoleInfoField.hidden = false;

        if (initialRoleSelect) {
            // Keep posted value valid for ChoiceField; backend maps student-join to student role.
            initialRoleSelect.value = isStudentJoinMode ? "member" : "org_admin";
        }

        if (autoRoleInfoText) {
            if (isIndividual) {
                autoRoleInfoText.textContent = tr(
                    "auto_role_info_owner",
                    "Fərdi hesab üçün rol avtomatik olaraq təşkilat admini olacaq."
                );
            } else if (isStudentJoinMode) {
                autoRoleInfoText.textContent =
                    "Email təsdiqindən sonra təşkilata qoşulma müraciətiniz təsdiq gözləyəcək.";
            } else {
                autoRoleInfoText.textContent = tr(
                    "auto_role_info_org",
                    "Seçilən qurum tipi üçün rol avtomatik olaraq təşkilat admini olacaq."
                );
            }
        }

        if (organizationNameInput) {
            organizationNameInput.required = isCreatorMode;
            if (!isCreatorMode) organizationNameInput.value = "";
        }

        if (organizationNameHelp) {
            organizationNameHelp.hidden = !isCreatorMode;
        }

        if (orgIdentifierInput) {
            orgIdentifierInput.required = isCreatorMode && selection.orgType === "university";
            if (!isCreatorMode) orgIdentifierInput.value = "";
        }

        if (licenseIdentifierInput && !isCreatorMode) {
            licenseIdentifierInput.value = "";
        }

        if (organizationSelect) {
            organizationSelect.required = false;
            if (!isStudentJoinMode) organizationSelect.value = "";
        }

        if (isCreatorMode) {
            updateCreateFieldsCopy(selection.orgType);
        }

        if (isStudentJoinMode) {
            updateStudentJoinCopy(selection.orgType);
            populateJoinOrganizationOptions(organizationSearchInput ? organizationSearchInput.value : "");
            syncSearchInputWithSelectedOrganization();
        } else {
            if (organizationSearchDebounceTimer) {
                clearTimeout(organizationSearchDebounceTimer);
                organizationSearchDebounceTimer = null;
            }
            if (organizationSearchInput) {
                organizationSearchInput.value = "";
                organizationSearchInput.dataset.selectedValue = "";
            }
            hideOrganizationSearchList();
        }
    }

    if (countrySelect) {
        countrySelect.addEventListener("change", function () {
            updateStep2State();
        });
    }

    if (registrationTypeSelect) {
        registrationTypeSelect.addEventListener("change", function () {
            updateStep2State();
        });
    }

    if (organizationSearchInput) {
        organizationSearchInput.addEventListener("input", function () {
            if (currentSelection().mode !== "student_join") return;

            var selectedValue = organizationSearchInput.dataset.selectedValue || "";
            if (selectedValue && organizationSelect) {
                var selectedOption = organizationSelect.querySelector('option[value="' + selectedValue + '"]');
                if (!selectedOption || organizationSearchInput.value !== selectedOption.textContent) {
                    organizationSelect.value = "";
                    organizationSearchInput.dataset.selectedValue = "";
                }
            }

            if (organizationSearchDebounceTimer) {
                clearTimeout(organizationSearchDebounceTimer);
            }
            organizationSearchDebounceTimer = window.setTimeout(function () {
                populateJoinOrganizationOptions(organizationSearchInput.value);
                renderOrganizationSearchList(organizationSearchInput.value);
            }, 1000);
        });

        organizationSearchInput.addEventListener("focus", function () {
            if (currentSelection().mode !== "student_join") return;
            if (organizationSearchDebounceTimer) {
                clearTimeout(organizationSearchDebounceTimer);
                organizationSearchDebounceTimer = null;
            }
            populateJoinOrganizationOptions(organizationSearchInput.value);
            renderOrganizationSearchList(organizationSearchInput.value);
        });
    }

    if (organizationSelect) {
        organizationSelect.addEventListener("change", function () {
            syncSearchInputWithSelectedOrganization();
        });
    }

    document.addEventListener("click", function (event) {
        if (!organizationSearchInput || !organizationSearchList) return;
        if (currentSelection().mode !== "student_join") return;

        var clickInsideInput = organizationSearchInput.contains(event.target);
        var clickInsideList = organizationSearchList.contains(event.target);
        if (!clickInsideInput && !clickInsideList) {
            hideOrganizationSearchList();
        }
    });

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

    if (registerForm && privacyCheckbox) {
        registerForm.addEventListener("submit", function (event) {
            if (privacyCheckbox.checked) return;

            event.preventDefault();
            wizardNext(3);

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
        registerForm.addEventListener("input", function (event) {
            if (event.target && event.target.type === "password") return;
            saveSignupDraft();
        });

        registerForm.addEventListener("change", function (event) {
            if (event.target && event.target.type === "password") return;
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

    updateStep2State();

    if (shouldRestoreSignupDraft()) {
        restoreSignupDraft();
    }

    // If form has errors, reveal the relevant step.
    var hasErrors = document.querySelector(".register-global-errors, .register-field-error:not([hidden])");
    if (hasErrors) {
        var step2Error = document.querySelector("#step2 .register-field-error");
        wizardNext(step2Error ? 2 : 3);
        return;
    }

    var requestedStep = getRequestedWizardStep();
    syncLanguageSwitcherTargets(requestedStep);
    if (requestedStep > 1) {
        wizardNext(requestedStep);
    } else if (shouldRestoreSignupDraft()) {
        persistWizardStep(1);
    }
});

function wizardNext(step) {
    var normalizedStep = Math.max(1, Math.min(3, parseInt(step, 10) || 1));
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
}

function wizardBack(step) {
    wizardNext(step);
}
