/**
 * Registration wizard - multi-step form navigation.
 * Steps:
 * 1) Country
 * 2a) Organization type card selection
 * 2b) Role/persona card selection + org-specific fields
 * 3) Institution selection for join flows
 * 4) Account details (with persona-specific fields)
 */
document.addEventListener("DOMContentLoaded", function () {
    var i18n = window.REGISTER_I18N || {};

    function tr(key, fallback) {
        if (!i18n[key] || i18n[key] === key) {
            return fallback;
        }
        return i18n[key];
    }

    var registrationTypeMap = {
        individual: { mode: "individual", orgType: "individual" },
        school: { mode: "organization_create", orgType: "school" },
        university: { mode: "organization_create", orgType: "university" },
        course_center: { mode: "organization_create", orgType: "course_center" },
        school_student: { mode: "student_join", orgType: "school" },
        university_student: { mode: "student_join", orgType: "university" },
        course_student: { mode: "student_join", orgType: "course_center" },
        school_teacher: { mode: "teacher_join", orgType: "school" },
        university_teacher: { mode: "teacher_join", orgType: "university" },
        course_teacher: { mode: "teacher_join", orgType: "course_center" },
        school_staff: { mode: "staff_join", orgType: "school" },
        university_staff: { mode: "staff_join", orgType: "university" },
        course_staff: { mode: "staff_join", orgType: "course_center" },
    };
    var emptyRegistrationSelection = { mode: "", orgType: "" };

    // Org type → combined registration type value for each role
    var orgRoleCombinedMap = {
        individual: { owner: "individual" },
        school: { owner: "school", teacher: "school_teacher", staff: "school_staff", student: "school_student" },
        university: { owner: "university", teacher: "university_teacher", staff: "university_staff", student: "university_student" },
        course_center: { owner: "course_center", teacher: "course_teacher", staff: "course_staff", student: "course_student" },
    };

    var countrySelect = document.getElementById("id_country");
    var registrationTypeSelect = document.getElementById("id_organization_type");

    var step2a = document.getElementById("step2a");
    var step2b = document.getElementById("step2b");
    var step2bTitle = document.getElementById("step2bTitle");
    var step3Title = document.getElementById("step3Title");
    var orgTypeCards = document.getElementById("orgTypeCards");
    var roleCards = document.getElementById("roleCards");
    var roleCardOwner = document.getElementById("roleCardOwner");
    var roleCardTeacher = document.getElementById("roleCardTeacher");
    var roleCardStaff = document.getElementById("roleCardStaff");
    var roleCardStudent = document.getElementById("roleCardStudent");
    var step2bBackBtn = document.getElementById("step2bBackBtn");

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
    var licenseIdentifierLabel = document.getElementById("licenseIdentifierLabel");
    var licenseIdentifierHelp = document.getElementById("licenseIdentifierHelp");

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
    var signupSummary = document.getElementById("signupSelectionSummary");
    var signupSummaryCountry = document.getElementById("signupSummaryCountry");
    var signupSummaryAccountType = document.getElementById("signupSummaryAccountType");
    var signupSummaryRole = document.getElementById("signupSummaryRole");
    var signupSummaryOrganization = document.getElementById("signupSummaryOrganization");
    var signupSummaryOrganizationItem = document.getElementById("signupSummaryOrganizationItem");

    // Step 4 persona-specific elements
    var phoneField = document.getElementById("phoneField");
    var studentSpecificFields = document.getElementById("studentSpecificFields");
    var teacherSpecificFields = document.getElementById("teacherSpecificFields");
    var staffSpecificFields = document.getElementById("staffSpecificFields");
    var departmentField = document.getElementById("departmentField");
    var specializationInput = document.getElementById("id_specialization");
    var groupNumberInput = document.getElementById("id_group_number");

    var lookupData = window.SIGNUP_LOOKUP_DATA || {};
    var organizations = lookupData.organizations || [];
    var enhancedSelects = [];
    var step2bBaseTitle = step2bTitle ? step2bTitle.textContent.trim() : tr("choose_role", "Choose your role");
    var individualSignupCard = orgTypeCards
        ? orgTypeCards.querySelector('.register-persona-card[data-org-type="individual"]')
        : null;

    // Track which org type the user picked in step 2a
    var _selectedOrgType = null;

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
        var selected = registrationTypeSelect ? registrationTypeSelect.value : "";
        if (!individualSignupCard && selected === "individual") {
            return emptyRegistrationSelection;
        }
        if (!selected) return emptyRegistrationSelection;
        return registrationTypeMap[selected] || emptyRegistrationSelection;
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

    function isJoinMode(mode) {
        return mode === "student_join" || mode === "teacher_join" || mode === "staff_join";
    }

    function shouldShowInstitutionStep() {
        return isJoinMode(currentSelection().mode);
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

    function selectNoOrganization() {
        if (organizationSelect) {
            organizationSelect.value = "";
            organizationSelect.dispatchEvent(new Event("change", { bubbles: true }));
        }
        if (organizationSearchInput) {
            organizationSearchInput.value = noOrganizationAffiliationLabel();
            organizationSearchInput.dataset.selectedValue = "";
            organizationSearchInput.dataset.noOrganizationSelected = "1";
        }
        hideOrganizationSearchList();
        updateSelectionSummary();
        saveSignupDraft();
    }

    function selectedOptionText(select) {
        if (!select || !select.options || select.selectedIndex < 0) return "";
        var selectedOption = select.options[select.selectedIndex];
        return selectedOption && selectedOption.value ? selectedOption.textContent.trim() : "";
    }

    function getRegistrationMeta(value) {
        var selectedValue = value !== undefined ? value : registrationTypeSelect ? registrationTypeSelect.value : "";
        if (!individualSignupCard && selectedValue === "individual") {
            selectedValue = "";
        }

        for (var orgType in orgRoleCombinedMap) {
            if (!Object.prototype.hasOwnProperty.call(orgRoleCombinedMap, orgType)) continue;

            var roles = orgRoleCombinedMap[orgType];
            for (var role in roles) {
                if (!Object.prototype.hasOwnProperty.call(roles, role)) continue;
                if (roles[role] === selectedValue) {
                    return {
                        value: selectedValue,
                        orgType: orgType,
                        role: role,
                    };
                }
            }
        }

        return {
            value: selectedValue,
            orgType: selectedValue ? "individual" : "",
            role: selectedValue === "individual" ? "owner" : "",
        };
    }

    function cardTitleText(container, selector) {
        if (!container) return "";
        var title = container.querySelector(selector + " .register-persona-card__title");
        return title ? title.textContent.trim() : "";
    }

    function setStep2bTitleText(orgType) {
        if (!step2bTitle) return;

        var orgTypeLabel =
            cardTitleText(orgTypeCards, '.register-persona-card[data-org-type="' + orgType + '"]') || orgType;

        step2bTitle.textContent = orgTypeLabel + " – " + step2bBaseTitle;
    }

    function syncStep2CardSelection() {
        var meta = getRegistrationMeta();

        if (orgTypeCards) {
            orgTypeCards.querySelectorAll(".register-persona-card[data-org-type]").forEach(function (card) {
                card.classList.toggle("is-selected", Boolean(meta.orgType) && card.dataset.orgType === meta.orgType);
            });
        }

        if (roleCards) {
            roleCards.querySelectorAll(".register-persona-role-card[data-role]").forEach(function (card) {
                card.classList.toggle("is-selected", Boolean(meta.role) && card.dataset.role === meta.role);
            });
        }

        if (!meta.value) return;

        _selectedOrgType = meta.orgType || null;

        if (step2a) step2a.hidden = true;
        if (step2b) step2b.hidden = false;

        if (meta.orgType === "individual") {
            if (roleCards) roleCards.hidden = true;
            if (step2bTitle) step2bTitle.hidden = true;
            return;
        }

        if (roleCards) roleCards.hidden = false;
        if (step2bTitle) step2bTitle.hidden = false;
        setStep2bTitleText(meta.orgType);
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

    // Set the combined registration type value from org type + role
    function setRegistrationValue(orgType, role) {
        var roles = orgRoleCombinedMap[orgType] || {};
        var combinedValue = roles[role] || "";
        if (registrationTypeSelect) {
            registrationTypeSelect.value = combinedValue;
            registrationTypeSelect.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }

    function clearUnsupportedIndividualSelection() {
        if (individualSignupCard || !registrationTypeSelect || registrationTypeSelect.value !== "individual") {
            return;
        }

        registrationTypeSelect.value = "";
    }

    // Show step 2b for the chosen org type
    function showPersonaStep(orgType) {
        _selectedOrgType = orgType;

        if (step2a) step2a.hidden = true;
        if (step2b) step2b.hidden = false;

        // For individual, immediately pick owner and skip role selection
        if (orgType === "individual") {
            setRegistrationValue("individual", "owner");
            if (step2b) step2b.hidden = false;
            // Show only the individual info, hide role cards
            if (roleCards) roleCards.hidden = true;
            if (individualAccountInfo) individualAccountInfo.hidden = false;
            if (orgCreateFields) orgCreateFields.hidden = true;
            if (studentJoinFields) studentJoinFields.hidden = true;
            if (step2bTitle) step2bTitle.hidden = true;
            return;
        }

        // Show role cards for org types
        if (roleCards) roleCards.hidden = false;
        if (step2bTitle) step2bTitle.hidden = false;

        // Update title
        setStep2bTitleText(orgType);

        // Reset combined select so no stale value
        if (registrationTypeSelect) registrationTypeSelect.value = "";

        // Hide fields until role is picked
        if (individualAccountInfo) individualAccountInfo.hidden = true;
        if (orgCreateFields) orgCreateFields.hidden = true;
        if (studentJoinFields) studentJoinFields.hidden = true;
    }

    // Org type card click handlers
    if (orgTypeCards) {
        orgTypeCards.querySelectorAll(".register-persona-card[data-org-type]").forEach(function (card) {
            card.addEventListener("click", function () {
                var orgType = card.dataset.orgType;
                // Mark card as selected
                orgTypeCards.querySelectorAll(".register-persona-card").forEach(function (c) {
                    c.classList.remove("is-selected");
                });
                card.classList.add("is-selected");
                showPersonaStep(orgType);
            });
        });
    }

    // Role card click handlers
    if (roleCards) {
        roleCards.querySelectorAll(".register-persona-role-card[data-role]").forEach(function (card) {
            card.addEventListener("click", function () {
                var role = card.dataset.role;
                var orgType = _selectedOrgType || "individual";
                // Mark card as selected
                roleCards.querySelectorAll(".register-persona-role-card").forEach(function (c) {
                    c.classList.remove("is-selected");
                });
                card.classList.add("is-selected");
                setRegistrationValue(orgType, role);
                updateStep2State();
            });
        });
    }

    // Step 2b back button → back to step 2a (org type selection)
    if (step2bBackBtn) {
        step2bBackBtn.addEventListener("click", function () {
            if (step2a) step2a.hidden = false;
            if (step2b) step2b.hidden = true;
            _selectedOrgType = null;
            if (registrationTypeSelect) {
                registrationTypeSelect.value = "";
                registrationTypeSelect.dispatchEvent(new Event("change", { bubbles: true }));
            }
        });
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

        organizationSelect.innerHTML = '<option value="">' + noOrganizationAffiliationLabel() + "</option>";
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

        var noOrganizationButton = document.createElement("button");
        noOrganizationButton.type = "button";
        noOrganizationButton.className = "register-search-option register-search-option--neutral";
        noOrganizationButton.textContent = noOrganizationAffiliationLabel();
        noOrganizationButton.dataset.value = "";
        if (isNoOrganizationSelected()) {
            noOrganizationButton.classList.add("is-selected");
        }
        noOrganizationButton.addEventListener("click", selectNoOrganization);
        organizationSearchList.appendChild(noOrganizationButton);

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
                    organizationSelect.dispatchEvent(new Event("change", { bubbles: true }));
                }
                organizationSearchInput.value = organizationOptionLabel(organization);
                organizationSearchInput.dataset.selectedValue = String(organization.id);
                clearNoOrganizationSelection();
                hideOrganizationSearchList();
                updateSelectionSummary();
                saveSignupDraft();
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
            clearNoOrganizationSelection();
        } else if (isNoOrganizationSelected()) {
            organizationSearchInput.value = noOrganizationAffiliationLabel();
            organizationSearchInput.dataset.selectedValue = "";
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
            orgIdentifierLabel.textContent = tr("label_school_identifier", "Məktəb kodu / identifikatoru");
            orgIdentifierHelp.textContent = tr("help_identifier_required", "Məktəb üçün bu sahə məcburidir.");
        } else if (orgType === "course_center") {
            organizationNameLabel.textContent = tr(
                "label_course_center_manual",
                "Kurs mərkəzi adı (Siyahıda yoxdur / Digər)"
            );
            organizationNameInput.placeholder = tr(
                "placeholder_course_center_manual",
                "Kurs mərkəzi siyahıda yoxdursa adını daxil edin..."
            );
            orgIdentifierLabel.textContent = tr("label_course_center_identifier", "Kurs mərkəzi kodu / identifikatoru");
            orgIdentifierHelp.textContent = tr("help_identifier_required", "Kurs mərkəzi üçün bu sahə məcburidir.");
        } else {
            organizationNameLabel.textContent = tr(
                "label_institution_manual_default",
                "Müəssisə adı (Siyahıda yoxdur / Digər)"
            );
            organizationNameInput.placeholder = tr("placeholder_search_default", "Müəssisə axtar...");
            orgIdentifierLabel.textContent = tr("label_identifier_default", "Rəsmi identifikator / kod");
            orgIdentifierHelp.textContent = tr("help_identifier_required", "Bu sahə məcburidir.");
        }

        if (licenseIdentifierLabel) {
            licenseIdentifierLabel.textContent = tr("label_license_identifier", "Lisenziya identifikatoru");
        }

        if (licenseIdentifierInput) {
            licenseIdentifierInput.placeholder = tr(
                "placeholder_license_identifier",
                "Lisenziya identifikatorunu daxil edin..."
            );
        }

        if (licenseIdentifierHelp) {
            licenseIdentifierHelp.textContent = tr(
                "help_license_identifier_required",
                "Lisenziya identifikatoru məcburidir."
            );
        }
    }

    function updateStudentJoinCopy(orgType) {
        if (!organizationSearchLabel || !organizationSearchInput || !studentJoinHint) return;
        var selectedCountry = (countrySelect ? countrySelect.value : "").toUpperCase();

        if (orgType === "university") {
            if (step3Title) step3Title.textContent = tr("choose_university", "Universitet seçin");
            organizationSearchLabel.textContent = tr("label_search_university", "Universitet axtar");
            organizationSearchInput.placeholder = tr("placeholder_search_university", "Universitet axtar...");
            studentJoinHint.textContent =
                selectedCountry === "AZ"
                    ? tr("hint_university_az", "Azərbaycandakı universitetləri siyahıdan seçə bilərsiniz.")
                    : tr("hint_university_global", "Ölkənizə uyğun universitet siyahısından seçim edin.");
        } else if (orgType === "school") {
            if (step3Title) step3Title.textContent = tr("choose_school", "Məktəb seçin");
            organizationSearchLabel.textContent = tr("label_search_school", "Məktəb axtar (ad və ya nömrə)");
            organizationSearchInput.placeholder = tr(
                "placeholder_search_school",
                "Məktəb adı və ya nömrəsi axtar..."
            );
            studentJoinHint.textContent = tr("hint_school", "Məktəbinizi siyahıdan seçin və ya əl ilə daxil edin.");
        } else if (orgType === "course_center") {
            if (step3Title) step3Title.textContent = tr("choose_course_center", "Kurs mərkəzi seçin");
            organizationSearchLabel.textContent = tr("label_search_course_center", "Kurs mərkəzi axtar");
            organizationSearchInput.placeholder = tr("placeholder_search_course_center", "Kurs mərkəzi axtar...");
            studentJoinHint.textContent = tr(
                "hint_course_center",
                "Kurs mərkəzini siyahıdan seçin və ya əl ilə daxil edin."
            );
        } else {
            if (step3Title) step3Title.textContent = tr("choose_institution", "Təşkilat seçin");
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
        if (parsed >= 1 && parsed <= 4) {
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
            values.organizationSearchNoOrganization = organizationSearchInput.dataset.noOrganizationSelected === "1";
        }

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
        if (!draftStorage) return;

        var rawDraft = draftStorage.getItem(signupDraftStorageKey);
        if (!rawDraft) return;

        try {
            var parsedDraft = JSON.parse(rawDraft);
            var values = parsedDraft && parsedDraft.values ? parsedDraft.values : {};
            var restoredSelectFields = [];

            Object.keys(values).forEach(function (name) {
                if (name === "organizationSearchInput" || name === "organizationSearchNoOrganization") return;

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

            clearUnsupportedIndividualSelection();
            updateStep2State();
            syncStep2CardSelection();
            restoredSelectFields.forEach(function (field) {
                field.dispatchEvent(new Event("change", { bubbles: true }));
            });

            if (organizationSelect && values.join_organization !== undefined) {
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

            updateSelectionSummary();
        } catch (error) {
            clearSignupDraft();
            return;
        }
    }

    window.persistRegisterWizardStep = persistWizardStep;
    window.saveRegisterSignupDraft = saveSignupDraft;
    window.resolveRegisterWizardStep = function (step, direction) {
        var normalizedStep = normalizeWizardStep(step);
        if (normalizedStep === 3 && !shouldShowInstitutionStep()) {
            return direction === "back" ? 2 : 4;
        }
        return normalizedStep;
    };

    migrateLegacySignupDraft();

    [countrySelect, registrationTypeSelect].forEach(function (select) {
        enhanceBootstrapSelect(select);
    });

    function updateStep2State() {
        var selection = currentSelection();
        var isIndividual = selection.mode === "individual";
        var isCreatorMode = selection.mode === "organization_create";
        var isStudentJoinMode = selection.mode === "student_join";
        var isTeacherJoinMode = selection.mode === "teacher_join";
        var isStaffJoinMode = selection.mode === "staff_join";
        var isJoinAny = isStudentJoinMode || isTeacherJoinMode || isStaffJoinMode;

        if (individualAccountInfo) individualAccountInfo.hidden = !isIndividual;
        if (orgCreateFields) orgCreateFields.hidden = !isCreatorMode;
        if (studentJoinFields) studentJoinFields.hidden = !isJoinAny;
        if (orgIdentifierField) orgIdentifierField.hidden = !isCreatorMode;
        if (initialRoleField) initialRoleField.hidden = true;
        if (autoRoleInfoField) autoRoleInfoField.hidden = false;

        if (initialRoleSelect) {
            if (isStudentJoinMode) {
                initialRoleSelect.value = "member";
            } else if (isTeacherJoinMode) {
                initialRoleSelect.value = "teacher";
            } else if (isStaffJoinMode) {
                initialRoleSelect.value = "member";
            } else {
                initialRoleSelect.value = "org_admin";
            }
        }

        if (autoRoleInfoText) {
            if (isIndividual) {
                autoRoleInfoText.textContent = tr(
                    "auto_role_info_owner",
                    "Fərdi hesab üçün rol avtomatik olaraq təşkilat admini olacaq."
                );
            } else if (isStudentJoinMode) {
                autoRoleInfoText.textContent =
                    tr("auto_role_info_student_join", "Email təsdiqindən sonra təşkilata tələbə kimi qoşulacaqsınız.");
            } else if (isTeacherJoinMode) {
                autoRoleInfoText.textContent =
                    tr("auto_role_info_teacher_join", "Email təsdiqindən sonra təşkilata müəllim kimi qoşulacaqsınız (təsdiq gözlənilir).");
            } else if (isStaffJoinMode) {
                autoRoleInfoText.textContent =
                    tr("auto_role_info_staff_join", "Email təsdiqindən sonra təşkilata işçi kimi qoşulacaqsınız (təsdiq gözlənilir).");
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
            orgIdentifierInput.required = isCreatorMode;
            if (!isCreatorMode) orgIdentifierInput.value = "";
        }

        if (licenseIdentifierInput) {
            licenseIdentifierInput.required = isCreatorMode;
            if (!isCreatorMode) licenseIdentifierInput.value = "";
        }

        if (organizationSelect) {
            organizationSelect.required = false;
            if (!isJoinAny) {
                organizationSelect.value = "";
            } else if (organizationSelect.value) {
                clearNoOrganizationSelection();
            }
        }

        if (isCreatorMode) {
            updateCreateFieldsCopy(selection.orgType);
        }

        if (isJoinAny) {
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
                organizationSearchInput.dataset.noOrganizationSelected = "";
            }
            hideOrganizationSearchList();
        }

        syncStep2CardSelection();

        // Also update step 4 persona fields
        updateStep3State();
        updateSelectionSummary();
    }

    function updateStep3State() {
        var selection = currentSelection();
        var isStudent = selection.mode === "student_join";
        var isTeacher = selection.mode === "teacher_join";
        var isStaff = selection.mode === "staff_join";
        var isJoinAny = isStudent || isTeacher || isStaff;

        if (studentSpecificFields) studentSpecificFields.hidden = !isStudent;
        if (teacherSpecificFields) teacherSpecificFields.hidden = !isTeacher;
        if (staffSpecificFields) staffSpecificFields.hidden = !isStaff;
        // Department field is shared: visible for both teacher and staff
        if (departmentField) departmentField.hidden = !(isTeacher || isStaff);
        if (phoneField) phoneField.hidden = !isJoinAny;

        // Make specialization/group required for students
        if (specializationInput) specializationInput.required = isStudent;
        if (groupNumberInput) {
            groupNumberInput.required = isStudent;
            groupNumberInput.setAttribute("aria-required", isStudent ? "true" : "false");
            if (!isStudent) {
                clearInlineFieldError(groupNumberInput);
            }
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
            if (!isJoinMode(currentSelection().mode)) return;

            if (
                organizationSearchInput.dataset.noOrganizationSelected === "1" &&
                organizationSearchInput.value !== noOrganizationAffiliationLabel()
            ) {
                clearNoOrganizationSelection();
            }

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
            if (!isJoinMode(currentSelection().mode)) return;
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
            if (organizationSelect.value) {
                clearNoOrganizationSelection();
            }
            syncSearchInputWithSelectedOrganization();
            updateSelectionSummary();
        });
    }

    document.addEventListener("click", function (event) {
        if (!organizationSearchInput || !organizationSearchList) return;
        if (!isJoinMode(currentSelection().mode)) return;

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

    clearUnsupportedIndividualSelection();
    updateStep2State();
    updateStep3State();

    // If form has errors, reveal the relevant step.
    var hasErrors = document.querySelector(".register-global-errors, .register-field-error:not([hidden])");
    if (hasErrors) {
        var step2Error = document.querySelector("#step2 .register-field-error");
        if (step2Error) {
            // Show step 2 with step 2b visible (errors are in org-specific fields)
            wizardNext(2);
            if (step2a) step2a.hidden = true;
            if (step2b) step2b.hidden = false;
        } else if (document.querySelector("#step3 .register-field-error")) {
            wizardNext(3);
        } else {
            wizardNext(4);
        }
        return;
    }

    var requestedStep = getRequestedWizardStep();
    if (shouldRestoreSignupDraft() || requestedStep > 1) {
        restoreSignupDraft();
    }
    syncLanguageSwitcherTargets(requestedStep);
    if (requestedStep > 1) {
        wizardNext(requestedStep);
    } else if (shouldRestoreSignupDraft()) {
        persistWizardStep(1);
    }
});

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
