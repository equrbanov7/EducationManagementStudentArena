/* Step 3: institution lookup and explicit join-flow choice handling. */

function hideOrganizationSearchList() {
    if (organizationSearchList) organizationSearchList.hidden = true;
    if (organizationSearchInput) organizationSearchInput.setAttribute("aria-expanded", "false");
}

function setJoinChoice(value) {
    if (joinChoiceInput) joinChoiceInput.value = value || "";
}

function showOrganizationSelectedChip(label, isNeutral) {
    if (!organizationSelectedChip) return;
    if (organizationSelectedChipLabel) organizationSelectedChipLabel.textContent = label || "";
    organizationSelectedChip.classList.toggle("is-neutral", Boolean(isNeutral));
    organizationSelectedChip.hidden = false;
}

function hideOrganizationSelectedChip() {
    if (!organizationSelectedChip) return;
    organizationSelectedChip.hidden = true;
    if (organizationSelectedChipLabel) organizationSelectedChipLabel.textContent = "";
}

function showOrganizationSearchError(message) {
    if (!organizationSearchError) return;
    organizationSearchError.textContent =
        message || tr("choose_organization_from_list", gettext("Zəhmət olmasa siyahıdan təşkilat seçin."));
    organizationSearchError.hidden = false;
    if (organizationSearchInput) organizationSearchInput.setAttribute("aria-invalid", "true");
}

function clearOrganizationSearchError() {
    if (organizationSearchError) {
        organizationSearchError.hidden = true;
        organizationSearchError.textContent = "";
    }
}

function setStep3ContinueEnabled(enabled) {
    if (!step3ContinueBtn) return;
    step3ContinueBtn.disabled = !enabled;
    step3ContinueBtn.setAttribute("aria-disabled", enabled ? "false" : "true");
    step3ContinueBtn.classList.toggle("is-disabled", !enabled);
}

function refreshOrganizationChoiceUI() {
    if (!isJoinMode(currentSelection().mode)) {
        setJoinChoice("");
        hideOrganizationSelectedChip();
        clearOrganizationSearchError();
        setStep3ContinueEnabled(true);
        return;
    }

    var hasOrg = organizationSelect && organizationSelect.value;
    if (hasOrg) {
        setJoinChoice("org");
        showOrganizationSelectedChip(
            selectedOptionText(organizationSelect) ||
                (organizationSearchInput ? organizationSearchInput.value.trim() : ""),
            false
        );
        clearOrganizationSearchError();
    } else if (isNoOrganizationSelected()) {
        setJoinChoice("none");
        showOrganizationSelectedChip(noOrganizationAffiliationLabel(), true);
        clearOrganizationSearchError();
    } else {
        setJoinChoice("");
        hideOrganizationSelectedChip();
    }

    var resolved = Boolean(joinChoiceInput && joinChoiceInput.value);
    setStep3ContinueEnabled(resolved);
    if (organizationSearchInput) {
        organizationSearchInput.setAttribute("aria-invalid", resolved ? "false" : "true");
    }
}

function keepOrganizationSearchFocus(button) {
    if (!button) return;
    button.addEventListener("mousedown", function (event) {
        event.preventDefault();
    });
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
    refreshOrganizationChoiceUI();
    updateSelectionSummary();
    saveSignupDraft();
}

function renderOrganizationSearchList(searchText) {
    if (!organizationSearchList || !organizationSearchInput) return;
    organizationSearchInput.setAttribute("aria-expanded", "true");
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
    keepOrganizationSearchFocus(noOrganizationButton);
    noOrganizationButton.addEventListener("click", function (event) {
        event.preventDefault();
        selectNoOrganization();
    });
    organizationSearchList.appendChild(noOrganizationButton);

    if (!options.length) {
        var empty = document.createElement("div");
        empty.className = "register-search-empty";
        empty.textContent = tr("no_results", gettext("Nəticə tapılmadı"));
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

        keepOrganizationSearchFocus(optionButton);
        optionButton.addEventListener("click", function (event) {
            event.preventDefault();
            if (organizationSelect) {
                organizationSelect.value = String(organization.id);
                organizationSelect.dispatchEvent(new Event("change", { bubbles: true }));
            }
            organizationSearchInput.value = organizationOptionLabel(organization);
            organizationSearchInput.dataset.selectedValue = String(organization.id);
            clearNoOrganizationSelection();
            hideOrganizationSearchList();
            refreshOrganizationChoiceUI();
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

function updateStudentJoinCopy(orgType) {
    if (!organizationSearchLabel || !organizationSearchInput || !studentJoinHint) return;
    var selectedCountry = (countrySelect ? countrySelect.value : "").toUpperCase();

    if (orgType === "university") {
        if (step3Title) step3Title.textContent = tr("choose_university", gettext("Universitet seçin"));
        organizationSearchLabel.textContent = tr("label_search_university", "Universitet axtar");
        organizationSearchInput.placeholder = tr("placeholder_search_university", "Universitet axtar...");
        studentJoinHint.textContent =
            selectedCountry === "AZ"
                ? tr("hint_university_az", gettext("Azərbaycandakı universitetləri siyahıdan seçə bilərsiniz."))
                : tr("hint_university_global", gettext("Ölkənizə uyğun universitet siyahısından seçim edin."));
    } else if (orgType === "school") {
        if (step3Title) step3Title.textContent = tr("choose_school", gettext("Məktəb seçin"));
        organizationSearchLabel.textContent = tr("label_search_school", gettext("Məktəb axtar (ad və ya nömrə)"));
        organizationSearchInput.placeholder = tr(
            "placeholder_search_school",
            gettext("Məktəb adı və ya nömrəsi axtar...")
        );
        studentJoinHint.textContent = tr("hint_school", gettext("Məktəbinizi siyahıdan seçin və ya əl ilə daxil edin."));
    } else if (orgType === "course_center") {
        if (step3Title) step3Title.textContent = tr("choose_course_center", gettext("Kurs mərkəzi seçin"));
        organizationSearchLabel.textContent = tr("label_search_course_center", gettext("Kurs mərkəzi axtar"));
        organizationSearchInput.placeholder = tr("placeholder_search_course_center", gettext("Kurs mərkəzi axtar..."));
        studentJoinHint.textContent = tr(
            "hint_course_center",
            gettext("Kurs mərkəzini siyahıdan seçin və ya əl ilə daxil edin.")
        );
    } else {
        if (step3Title) step3Title.textContent = tr("choose_institution", gettext("Təşkilat seçin"));
        organizationSearchLabel.textContent = tr("label_search_default", gettext("Müəssisə axtar"));
        organizationSearchInput.placeholder = tr("placeholder_search_default", gettext("Müəssisə axtar..."));
        studentJoinHint.textContent = "";
    }
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
    if (departmentField) departmentField.hidden = !(isTeacher || isStaff);
    if (phoneField) phoneField.hidden = !isJoinAny;

    if (specializationInput) specializationInput.required = isStudent;
    if (groupNumberInput) {
        groupNumberInput.required = isStudent;
        groupNumberInput.setAttribute("aria-required", isStudent ? "true" : "false");
        if (!isStudent) {
            clearInlineFieldError(groupNumberInput);
        }
    }
}

function openOrganizationSearchList() {
    if (!isJoinMode(currentSelection().mode)) return;
    if (organizationSearchDebounceTimer) {
        clearTimeout(organizationSearchDebounceTimer);
        organizationSearchDebounceTimer = null;
    }
    populateJoinOrganizationOptions(organizationSearchInput.value);
    renderOrganizationSearchList(organizationSearchInput.value);
}

function initRegisterWizardStep3() {
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

            refreshOrganizationChoiceUI();
            if ((organizationSearchInput.value || "").trim() && !(joinChoiceInput && joinChoiceInput.value)) {
                showOrganizationSearchError();
            } else {
                clearOrganizationSearchError();
            }

            if (organizationSearchDebounceTimer) {
                clearTimeout(organizationSearchDebounceTimer);
            }
            organizationSearchDebounceTimer = window.setTimeout(function () {
                populateJoinOrganizationOptions(organizationSearchInput.value);
                renderOrganizationSearchList(organizationSearchInput.value);
                saveSignupDraft();
            }, 150);
        });

        organizationSearchInput.addEventListener("focus", openOrganizationSearchList);
        organizationSearchInput.addEventListener("click", openOrganizationSearchList);
    }

    if (organizationSelect) {
        organizationSelect.addEventListener("change", function () {
            if (organizationSelect.value) {
                clearNoOrganizationSelection();
            }
            syncSearchInputWithSelectedOrganization();
            refreshOrganizationChoiceUI();
            updateSelectionSummary();
        });
    }

    if (organizationSelectedChipClear) {
        organizationSelectedChipClear.addEventListener("click", function () {
            if (organizationSelect) {
                organizationSelect.value = "";
                organizationSelect.dispatchEvent(new Event("change", { bubbles: true }));
            }
            clearNoOrganizationSelection();
            if (organizationSearchInput) {
                organizationSearchInput.value = "";
                organizationSearchInput.dataset.selectedValue = "";
            }
            refreshOrganizationChoiceUI();
            updateSelectionSummary();
            saveSignupDraft();
            if (organizationSearchInput) organizationSearchInput.focus();
        });
    }

    if (step3ContinueBtn) {
        step3ContinueBtn.addEventListener("click", function (event) {
            if (!isJoinMode(currentSelection().mode)) return;
            if (joinChoiceInput && joinChoiceInput.value) return;
            event.preventDefault();
            event.stopImmediatePropagation();
            showOrganizationSearchError();
            setStep3ContinueEnabled(false);
            if (organizationSearchInput) organizationSearchInput.focus();
        });
    }

    document.addEventListener("click", function (event) {
        if (!organizationSearchInput || !organizationSearchList) return;
        if (!isJoinMode(currentSelection().mode)) return;

        var clickInsideSearchField = organizationSearchField && organizationSearchField.contains(event.target);
        if (!clickInsideSearchField) {
            hideOrganizationSearchList();
        }
    });
}
