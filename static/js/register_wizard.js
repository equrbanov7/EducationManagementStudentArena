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

    var lookupData = window.SIGNUP_LOOKUP_DATA || {};
    var institutions = lookupData.institutions || [];
    var institutionById = {};
    institutions.forEach(function (institution) {
        institutionById[String(institution.id)] = institution;
    });

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
        institutionSelect.innerHTML = '<option value="">Müəssisə seçin</option>';
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

    function updateInstitutionRequirements() {
        var orgType = orgTypeSelect ? orgTypeSelect.value : "";
        var isIndividual = orgType === "individual";
        var needsOfficialIdentifier = orgType === "school" || orgType === "university";
        var selectedInstitution = institutionById[String(institutionSelect ? institutionSelect.value : "")];
        var hasManualInstitution = institutionNotListedInput && institutionNotListedInput.value.trim() !== "";

        if (orgFields) orgFields.hidden = isIndividual;

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
            orgIdentifierInput.required = !isIndividual && needsOfficialIdentifier && !institutionHasCode;
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
                orgIdentifierHelp.textContent = "School/University üçün rəsmi identifikator məcburidir.";
            } else {
                orgIdentifierHelp.textContent = "Course Center üçün identifikator opsionaldır.";
            }
        }
    }

    function refreshInstitutions() {
        var orgType = orgTypeSelect ? orgTypeSelect.value : "";
        if (orgType === "individual") {
            if (institutionSelect) institutionSelect.innerHTML = '<option value="">Müəssisə seçin</option>';
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
