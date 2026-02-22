/**
 * Registration wizard - multi-step form navigation.
 * Steps:
 * 1) Country
 * 2) Registration type + institution
 * 3) Account details
 */
document.addEventListener("DOMContentLoaded", function () {
    var i18n = window.REGISTER_I18N || {};
    function tr(key, fallback) {
        return i18n[key] || fallback;
    }

    var countrySelect = document.getElementById("id_country");
    var orgTypeSelect = document.getElementById("id_organization_type");
    var orgFields = document.getElementById("orgFields");
    var individualOrgFields = document.getElementById("individualOrgFields");
    var joinOrganizationSelect = document.getElementById("id_join_organization");
    var institutionSelect = document.getElementById("id_institution");
    var institutionSearchInput = document.getElementById("institutionSearchInput");
    var institutionNotListedInput = document.getElementById("id_institution_not_listed_name");
    var orgIdentifierInput = document.getElementById("id_organization_identifier");
    var orgIdentifierHelp = document.getElementById("orgIdentifierHelp");
    var institutionSearchLabel = document.getElementById("institutionSearchLabel");
    var institutionTypeHint = document.getElementById("institutionTypeHint");
    var institutionSelectLabel = document.getElementById("institutionSelectLabel");
    var institutionManualLabel = document.getElementById("institutionManualLabel");
    var orgIdentifierLabel = document.getElementById("orgIdentifierLabel");
    var orgIdentifierField = document.getElementById("orgIdentifierField");
    var initialRoleField = document.getElementById("initialRoleField");
    var autoStudentRoleInfo = document.getElementById("autoStudentRoleInfo");
    var initialRoleSelect = document.getElementById("id_initial_role");

    var lookupData = window.SIGNUP_LOOKUP_DATA || {};
    var institutions = lookupData.institutions || [];
    var institutionById = {};
    institutions.forEach(function (institution) {
        institutionById[String(institution.id)] = institution;
    });

    function getSelectEmptyLabel() {
        var selectedType = orgTypeSelect ? orgTypeSelect.value : "";
        if (selectedType === "university") return tr("select_empty_university", "Universitet seçin");
        if (selectedType === "school") return tr("select_empty_school", "Məktəb seçin");
        if (selectedType === "course_center") return tr("select_empty_course_center", "Kurs mərkəzi seçin");
        return tr("select_empty_default", "Müəssisə seçin");
    }

    function filteredInstitutions(searchText) {
        var selectedCountry = (countrySelect ? countrySelect.value : "").toUpperCase();
        var selectedType = orgTypeSelect ? orgTypeSelect.value : "";
        var search = (searchText || "").toLowerCase().trim();

        return institutions.filter(function (institution) {
            if (selectedCountry && institution.country__code !== selectedCountry) return false;
            if (selectedType && institution.institution_type !== selectedType) return false;
            if (search && !institution.name.toLowerCase().includes(search)) return false;
            return true;
        });
    }

    function populateInstitutionOptions(searchText) {
        if (!institutionSelect) return;
        var previousValue = institutionSelect.value;
        var options = filteredInstitutions(searchText);
        institutionSelect.innerHTML = '<option value="">' + getSelectEmptyLabel() + "</option>";
        options.forEach(function (institution) {
            var option = document.createElement("option");
            option.value = institution.id;
            option.textContent = institution.code ? institution.name + " (" + institution.code + ")" : institution.name;
            institutionSelect.appendChild(option);
        });
        if (options.some(function (item) { return String(item.id) === previousValue; })) {
            institutionSelect.value = previousValue;
        }
    }

    function updateInstitutionCopy() {
        var orgType = orgTypeSelect ? orgTypeSelect.value : "";
        var selectedCountry = (countrySelect ? countrySelect.value : "").toUpperCase();

        if (orgType === "university") {
            if (institutionSearchLabel) institutionSearchLabel.textContent = tr("label_search_university", "Universitet axtar");
            if (institutionSearchInput) {
                institutionSearchInput.placeholder = tr("placeholder_search_university", "Universitet adı axtar...");
            }
            if (institutionSelectLabel) institutionSelectLabel.textContent = tr("label_university", "Universitet");
            if (institutionManualLabel) {
                institutionManualLabel.textContent = tr(
                    "label_university_manual",
                    "Universitet adı (Not listed / Other)"
                );
            }
            if (institutionNotListedInput) {
                institutionNotListedInput.placeholder = tr(
                    "placeholder_university_manual",
                    "Universitet siyahıda yoxdursa adını daxil edin..."
                );
            }
            if (orgIdentifierLabel) {
                orgIdentifierLabel.textContent = tr("label_university_identifier", "Universitet kodu / identifikatoru");
            }
            if (institutionTypeHint) {
                institutionTypeHint.textContent =
                    selectedCountry === "AZ"
                        ? tr("hint_university_az", "Azərbaycan universitetləri siyahıdan seçilə bilər.")
                        : tr("hint_university_global", "Ölkə üzrə universitet siyahısından seçim edin.");
            }
        } else if (orgType === "school") {
            if (institutionSearchLabel) {
                institutionSearchLabel.textContent = tr("label_search_school", "Məktəb axtar (ad və ya nömrə)");
            }
            if (institutionSearchInput) {
                institutionSearchInput.placeholder = tr(
                    "placeholder_search_school",
                    "Məktəb adı və ya nömrəsi axtar..."
                );
            }
            if (institutionSelectLabel) {
                institutionSelectLabel.textContent = tr("label_school_optional", "Məktəb (opsional)");
            }
            if (institutionManualLabel) {
                institutionManualLabel.textContent = tr("label_school_manual", "Məktəb adı (Not listed / Other)");
            }
            if (institutionNotListedInput) {
                institutionNotListedInput.placeholder = tr(
                    "placeholder_school_manual",
                    "Məktəb siyahıda yoxdursa adını daxil edin..."
                );
            }
            if (orgIdentifierLabel) {
                orgIdentifierLabel.textContent = tr("label_school_identifier", "Məktəb nömrəsi / kodu (opsional)");
            }
            if (institutionTypeHint) {
                institutionTypeHint.textContent = tr(
                    "hint_school",
                    "Məktəbinizi seçin və ya əl ilə yazın. Məktəb nömrəsi ayrıca daxil edilə bilər."
                );
            }
        } else if (orgType === "course_center") {
            if (institutionSearchLabel) {
                institutionSearchLabel.textContent = tr("label_search_course_center", "Kurs mərkəzi axtar");
            }
            if (institutionSearchInput) {
                institutionSearchInput.placeholder = tr(
                    "placeholder_search_course_center",
                    "Kurs mərkəzi adı axtar..."
                );
            }
            if (institutionSelectLabel) {
                institutionSelectLabel.textContent = tr(
                    "label_course_center_optional",
                    "Kurs mərkəzi (opsional)"
                );
            }
            if (institutionManualLabel) {
                institutionManualLabel.textContent = tr(
                    "label_course_center_manual",
                    "Kurs mərkəzi adı (Not listed / Other)"
                );
            }
            if (institutionNotListedInput) {
                institutionNotListedInput.placeholder = tr(
                    "placeholder_course_center_manual",
                    "Kurs mərkəzi siyahıda yoxdursa adını daxil edin..."
                );
            }
            if (orgIdentifierLabel) {
                orgIdentifierLabel.textContent = tr("label_course_center_identifier", "Mərkəz identifikatoru (opsional)");
            }
            if (institutionTypeHint) {
                institutionTypeHint.textContent = tr(
                    "hint_course_center",
                    "Kurs mərkəzi siyahıdan seçilə və ya Not listed / Other ilə əl ilə daxil edilə bilər."
                );
            }
        } else {
            if (institutionSearchLabel) institutionSearchLabel.textContent = tr("label_search_default", "Müəssisə axtar");
            if (institutionSearchInput) {
                institutionSearchInput.placeholder = tr("placeholder_search_default", "Müəssisə axtar...");
            }
            if (institutionSelectLabel) {
                institutionSelectLabel.textContent = tr("label_institution_default", "Müəssisə");
            }
            if (institutionManualLabel) {
                institutionManualLabel.textContent = tr(
                    "label_institution_manual_default",
                    "Müəssisə adı (Not listed / Other)"
                );
            }
            if (orgIdentifierLabel) {
                orgIdentifierLabel.textContent = tr("label_identifier_default", "Rəsmi identifikator / kod");
            }
            if (institutionTypeHint) institutionTypeHint.textContent = "";
        }
    }

    function updateInstitutionRequirements() {
        var orgType = orgTypeSelect ? orgTypeSelect.value : "";
        var isIndividual = orgType === "individual";
        var needsOfficialIdentifier = orgType === "university";
        var selectedInstitution = institutionById[String(institutionSelect ? institutionSelect.value : "")];
        var hasManualInstitution = institutionNotListedInput && institutionNotListedInput.value.trim() !== "";

        updateInstitutionCopy();
        if (individualOrgFields) individualOrgFields.hidden = !isIndividual;
        if (orgFields) orgFields.hidden = isIndividual;
        if (orgIdentifierField) orgIdentifierField.hidden = isIndividual;
        if (initialRoleField) initialRoleField.hidden = isIndividual;
        if (autoStudentRoleInfo) autoStudentRoleInfo.hidden = !isIndividual;

        if (joinOrganizationSelect) {
            joinOrganizationSelect.required = isIndividual;
            if (!isIndividual) joinOrganizationSelect.value = "";
        }
        if (initialRoleSelect && isIndividual) {
            initialRoleSelect.value = "member";
        }

        if (institutionSelect) {
            institutionSelect.required = !isIndividual && !hasManualInstitution;
            if (isIndividual) institutionSelect.value = "";
        }

        if (institutionNotListedInput) {
            institutionNotListedInput.required = !isIndividual && !institutionSelect.value;
            if (isIndividual) institutionNotListedInput.value = "";
        }

        if (orgIdentifierInput) {
            var institutionHasCode = selectedInstitution && selectedInstitution.code;
            orgIdentifierInput.required = needsOfficialIdentifier && !institutionHasCode;
            if (isIndividual) {
                orgIdentifierInput.value = "";
            } else if (institutionHasCode && !orgIdentifierInput.value) {
                orgIdentifierInput.value = selectedInstitution.code;
            }
        }

        if (orgIdentifierHelp) {
            if (isIndividual) {
                orgIdentifierHelp.textContent = "";
            } else if (needsOfficialIdentifier) {
                orgIdentifierHelp.textContent = tr(
                    "help_identifier_required",
                    "University üçün rəsmi identifikator məcburidir."
                );
            } else {
                orgIdentifierHelp.textContent = tr("help_identifier_optional", "Bu sahə opsionaldır.");
            }
        }
    }

    function refreshInstitutions() {
        var orgType = orgTypeSelect ? orgTypeSelect.value : "";
        if (orgType === "individual") {
            if (institutionSelect) institutionSelect.innerHTML = '<option value="">' + getSelectEmptyLabel() + "</option>";
            updateInstitutionRequirements();
            return;
        }
        populateInstitutionOptions(institutionSearchInput ? institutionSearchInput.value : "");
        updateInstitutionRequirements();
    }

    if (countrySelect) countrySelect.addEventListener("change", refreshInstitutions);
    if (orgTypeSelect) orgTypeSelect.addEventListener("change", refreshInstitutions);
    if (institutionSearchInput) {
        institutionSearchInput.addEventListener("input", function () {
            populateInstitutionOptions(institutionSearchInput.value);
        });
    }
    if (institutionSelect) institutionSelect.addEventListener("change", updateInstitutionRequirements);
    if (institutionNotListedInput) institutionNotListedInput.addEventListener("input", updateInstitutionRequirements);

    refreshInstitutions();

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
