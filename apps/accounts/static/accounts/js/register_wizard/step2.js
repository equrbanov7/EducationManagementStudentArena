/* Step 2: organization type, persona, and organization-create fields. */

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

function showPersonaStep(orgType) {
    _selectedOrgType = orgType;

    if (step2a) step2a.hidden = true;
    if (step2b) step2b.hidden = false;

    if (orgType === "individual") {
        setRegistrationValue("individual", "owner");
        if (step2b) step2b.hidden = false;
        if (roleCards) roleCards.hidden = true;
        if (individualAccountInfo) individualAccountInfo.hidden = false;
        if (orgCreateFields) orgCreateFields.hidden = true;
        if (studentJoinFields) studentJoinFields.hidden = true;
        if (step2bTitle) step2bTitle.hidden = true;
        return;
    }

    if (roleCards) roleCards.hidden = false;
    if (step2bTitle) step2bTitle.hidden = false;
    setStep2bTitleText(orgType);

    if (registrationTypeSelect) registrationTypeSelect.value = "";

    if (individualAccountInfo) individualAccountInfo.hidden = true;
    if (orgCreateFields) orgCreateFields.hidden = true;
    if (studentJoinFields) studentJoinFields.hidden = true;
}

function updateCreateFieldsCopy(orgType) {
    if (!organizationNameLabel || !organizationNameInput || !orgIdentifierLabel || !orgIdentifierHelp) {
        return;
    }

    if (orgType === "university") {
        organizationNameLabel.textContent = tr(
            "label_university_manual",
            gettext("Universitet adı (Siyahıda yoxdur / Digər)")
        );
        organizationNameInput.placeholder = tr("placeholder_university_manual", gettext("Universitet adını daxil edin..."));
        orgIdentifierLabel.textContent = tr("label_university_identifier", "Universitet kodu / identifikatoru");
        orgIdentifierHelp.textContent = tr("help_identifier_required", gettext("Universitet üçün bu sahə məcburidir."));
    } else if (orgType === "school") {
        organizationNameLabel.textContent = tr("label_school_manual", gettext("Məktəb adı (Siyahıda yoxdur / Digər)"));
        organizationNameInput.placeholder = tr(
            "placeholder_school_manual",
            gettext("Məktəb siyahıda yoxdursa adını daxil edin...")
        );
        orgIdentifierLabel.textContent = tr("label_school_identifier", gettext("Məktəb kodu / identifikatoru"));
        orgIdentifierHelp.textContent = tr("help_identifier_required", gettext("Məktəb üçün bu sahə məcburidir."));
    } else if (orgType === "course_center") {
        organizationNameLabel.textContent = tr(
            "label_course_center_manual",
            gettext("Kurs mərkəzi adı (Siyahıda yoxdur / Digər)")
        );
        organizationNameInput.placeholder = tr(
            "placeholder_course_center_manual",
            gettext("Kurs mərkəzi siyahıda yoxdursa adını daxil edin...")
        );
        orgIdentifierLabel.textContent = tr("label_course_center_identifier", gettext("Kurs mərkəzi kodu / identifikatoru"));
        orgIdentifierHelp.textContent = tr("help_identifier_required", gettext("Kurs mərkəzi üçün bu sahə məcburidir."));
    } else {
        organizationNameLabel.textContent = tr(
            "label_institution_manual_default",
            gettext("Müəssisə adı (Siyahıda yoxdur / Digər)")
        );
        organizationNameInput.placeholder = tr("placeholder_search_default", gettext("Müəssisə axtar..."));
        orgIdentifierLabel.textContent = tr("label_identifier_default", gettext("Rəsmi identifikator / kod"));
        orgIdentifierHelp.textContent = tr("help_identifier_required", gettext("Bu sahə məcburidir."));
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
            gettext("Lisenziya identifikatoru məcburidir.")
        );
    }
}

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

    updateAutoRoleInfoText(isIndividual, isStudentJoinMode, isTeacherJoinMode, isStaffJoinMode);

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

    updateJoinFieldState(isJoinAny, selection.orgType);
    syncStep2CardSelection();
    updateStep3State();
    updateSelectionSummary();
}

function updateAutoRoleInfoText(isIndividual, isStudentJoinMode, isTeacherJoinMode, isStaffJoinMode) {
    if (!autoRoleInfoText) {
        return;
    }

    if (isIndividual) {
        autoRoleInfoText.textContent = tr(
            "auto_role_info_owner",
            gettext("Fərdi hesab üçün rol avtomatik olaraq təşkilat admini olacaq.")
        );
    } else if (isStudentJoinMode) {
        autoRoleInfoText.textContent =
            tr("auto_role_info_student_join", gettext("Email təsdiqindən sonra təşkilata tələbə kimi qoşulacaqsınız."));
    } else if (isTeacherJoinMode) {
        autoRoleInfoText.textContent =
            tr("auto_role_info_teacher_join", gettext("Email təsdiqindən sonra təşkilata müəllim kimi qoşulacaqsınız (təsdiq gözlənilir)."));
    } else if (isStaffJoinMode) {
        autoRoleInfoText.textContent =
            tr("auto_role_info_staff_join", gettext("Email təsdiqindən sonra təşkilata işçi kimi qoşulacaqsınız (təsdiq gözlənilir)."));
    } else {
        autoRoleInfoText.textContent = tr(
            "auto_role_info_org",
            gettext("Seçilən qurum tipi üçün rol avtomatik olaraq təşkilat admini olacaq.")
        );
    }
}

function updateJoinFieldState(isJoinAny, orgType) {
    if (isJoinAny) {
        updateStudentJoinCopy(orgType);
        populateJoinOrganizationOptions(organizationSearchInput ? organizationSearchInput.value : "");
        syncSearchInputWithSelectedOrganization();
        refreshOrganizationChoiceUI();
        return;
    }

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
    refreshOrganizationChoiceUI();
}

function initRegisterWizardStep2() {
    if (orgTypeCards) {
        orgTypeCards.querySelectorAll(".register-persona-card[data-org-type]").forEach(function (card) {
            card.addEventListener("click", function () {
                var orgType = card.dataset.orgType;
                orgTypeCards.querySelectorAll(".register-persona-card").forEach(function (c) {
                    c.classList.remove("is-selected");
                });
                card.classList.add("is-selected");
                showPersonaStep(orgType);
                updateSelectionSummary();
                saveSignupDraft();
            });
        });
    }

    if (roleCards) {
        roleCards.querySelectorAll(".register-persona-role-card[data-role]").forEach(function (card) {
            card.addEventListener("click", function () {
                var role = card.dataset.role;
                var orgType = _selectedOrgType || "individual";
                roleCards.querySelectorAll(".register-persona-role-card").forEach(function (c) {
                    c.classList.remove("is-selected");
                });
                card.classList.add("is-selected");
                setRegistrationValue(orgType, role);
                updateStep2State();
                if (shouldShowInstitutionStep()) {
                    wizardNext(3);
                }
                saveSignupDraft();
            });
        });
    }

    if (step2bBackBtn) {
        step2bBackBtn.addEventListener("click", function () {
            if (step2a) step2a.hidden = false;
            if (step2b) step2b.hidden = true;
            _selectedOrgType = null;
            if (registrationTypeSelect) {
                registrationTypeSelect.value = "";
                registrationTypeSelect.dispatchEvent(new Event("change", { bubbles: true }));
            }
            saveSignupDraft();
        });
    }

    if (registrationTypeSelect) {
        registrationTypeSelect.addEventListener("change", function () {
            updateStep2State();
        });
    }
}
