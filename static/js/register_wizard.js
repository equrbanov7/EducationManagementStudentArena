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

    var initialRoleField = document.getElementById("initialRoleField");
    var autoRoleInfoField = document.getElementById("autoRoleInfoField");
    var autoRoleInfoText = document.getElementById("autoRoleInfoText");
    var initialRoleSelect = document.getElementById("id_initial_role");

    var lookupData = window.SIGNUP_LOOKUP_DATA || {};
    var organizations = lookupData.organizations || [];

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
                autoRoleInfoText.textContent = tr(
                    "auto_role_info_student_join",
                    "Email təsdiqindən sonra seçdiyiniz quruma tələbə kimi qoşulacaqsınız."
                );
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
            organizationSelect.required = isStudentJoinMode;
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

            populateJoinOrganizationOptions(organizationSearchInput.value);
            renderOrganizationSearchList(organizationSearchInput.value);
        });

        organizationSearchInput.addEventListener("focus", function () {
            if (currentSelection().mode !== "student_join") return;
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

    updateStep2State();

    // If form has errors, reveal the relevant step.
    var hasErrors = document.querySelector(".register-global-errors, .register-field-error");
    if (hasErrors) {
        var step2Error = document.querySelector("#step2 .register-field-error");
        wizardNext(step2Error ? 2 : 3);
    }
});

function wizardNext(step) {
    var panels = document.querySelectorAll(".wizard-panel");
    panels.forEach(function (panel) {
        panel.hidden = true;
    });

    var target = document.getElementById("step" + step);
    if (target) target.hidden = false;

    var steps = document.querySelectorAll(".wizard-step");
    steps.forEach(function (item) {
        var currentStep = parseInt(item.dataset.step, 10);
        item.classList.toggle("active", currentStep === step);
        item.classList.toggle("completed", currentStep < step);
    });
}

function wizardBack(step) {
    wizardNext(step);
}
