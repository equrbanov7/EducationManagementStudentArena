/**
 * Registration wizard - multi-step form navigation.
 * Steps:
 * 1) Country
 * 2) Registration type + institution
 * 3) Account details
 */
document.addEventListener("DOMContentLoaded", function () {
    var countrySelect = document.getElementById("id_country");
    var orgTypeSelect = document.getElementById("id_organization_type");
    var orgFields = document.getElementById("orgFields");
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

    var lookupData = window.SIGNUP_LOOKUP_DATA || {};
    var institutions = lookupData.institutions || [];
    var institutionById = {};
    institutions.forEach(function (institution) {
        institutionById[String(institution.id)] = institution;
    });

    function getSelectEmptyLabel() {
        var selectedType = orgTypeSelect ? orgTypeSelect.value : "";
        if (selectedType === "university") return "Universitet seçin";
        if (selectedType === "school") return "Məktəb seçin";
        if (selectedType === "course_center") return "Kurs mərkəzi seçin";
        return "Müəssisə seçin";
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
            if (institutionSearchLabel) institutionSearchLabel.textContent = "Universitet axtar";
            if (institutionSearchInput) institutionSearchInput.placeholder = "Universitet adı axtar...";
            if (institutionSelectLabel) institutionSelectLabel.textContent = "Universitet";
            if (institutionManualLabel) institutionManualLabel.textContent = "Universitet adı (Not listed / Other)";
            if (institutionNotListedInput) {
                institutionNotListedInput.placeholder = "Universitet siyahıda yoxdursa adını daxil edin...";
            }
            if (orgIdentifierLabel) orgIdentifierLabel.textContent = "Universitet kodu / identifikatoru";
            if (institutionTypeHint) {
                institutionTypeHint.textContent =
                    selectedCountry === "AZ"
                        ? "Azərbaycan universitetləri siyahıdan seçilə bilər."
                        : "Ölkə üzrə universitet siyahısından seçim edin.";
            }
        } else if (orgType === "school") {
            if (institutionSearchLabel) institutionSearchLabel.textContent = "Məktəb axtar (ad və ya nömrə)";
            if (institutionSearchInput) institutionSearchInput.placeholder = "Məktəb adı və ya nömrəsi axtar...";
            if (institutionSelectLabel) institutionSelectLabel.textContent = "Məktəb (opsional)";
            if (institutionManualLabel) institutionManualLabel.textContent = "Məktəb adı (Not listed / Other)";
            if (institutionNotListedInput) {
                institutionNotListedInput.placeholder = "Məktəb siyahıda yoxdursa adını daxil edin...";
            }
            if (orgIdentifierLabel) orgIdentifierLabel.textContent = "Məktəb nömrəsi / kodu (opsional)";
            if (institutionTypeHint) {
                institutionTypeHint.textContent =
                    "Məktəbinizi seçin və ya əl ilə yazın. Məktəb nömrəsi ayrıca daxil edilə bilər.";
            }
        } else if (orgType === "course_center") {
            if (institutionSearchLabel) institutionSearchLabel.textContent = "Kurs mərkəzi axtar";
            if (institutionSearchInput) institutionSearchInput.placeholder = "Kurs mərkəzi adı axtar...";
            if (institutionSelectLabel) institutionSelectLabel.textContent = "Kurs mərkəzi (opsional)";
            if (institutionManualLabel) institutionManualLabel.textContent = "Kurs mərkəzi adı (Not listed / Other)";
            if (institutionNotListedInput) {
                institutionNotListedInput.placeholder = "Kurs mərkəzi siyahıda yoxdursa adını daxil edin...";
            }
            if (orgIdentifierLabel) orgIdentifierLabel.textContent = "Mərkəz identifikatoru (opsional)";
            if (institutionTypeHint) {
                institutionTypeHint.textContent =
                    "Kurs mərkəzi siyahıdan seçilə və ya Not listed / Other ilə əl ilə daxil edilə bilər.";
            }
        } else {
            if (institutionSearchLabel) institutionSearchLabel.textContent = "Müəssisə axtar";
            if (institutionSearchInput) institutionSearchInput.placeholder = "Müəssisə axtar...";
            if (institutionSelectLabel) institutionSelectLabel.textContent = "Müəssisə";
            if (institutionManualLabel) institutionManualLabel.textContent = "Müəssisə adı (Not listed / Other)";
            if (orgIdentifierLabel) orgIdentifierLabel.textContent = "Rəsmi identifikator / kod";
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
        if (orgFields) orgFields.hidden = isIndividual;
        if (orgIdentifierField) orgIdentifierField.hidden = isIndividual;

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
                orgIdentifierHelp.textContent = "University üçün rəsmi identifikator məcburidir.";
            } else {
                orgIdentifierHelp.textContent = "Bu sahə opsionaldır.";
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
