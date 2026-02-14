/**
 * Registration wizard - multi-step form navigation.
 * Steps: 1) Country  2) Account type + Organization  3) User details
 */
document.addEventListener('DOMContentLoaded', function () {
    var orgTypeSelect = document.getElementById('id_organization_type');
    var orgSelectField = document.getElementById('orgSelectField');
    var orgSelect = document.getElementById('orgSelect');
    var orgOtherField = document.getElementById('orgOtherField');
    var orgIdInput = document.getElementById('id_organization_id');
    var countryInput = document.getElementById('id_country');

    if (!orgTypeSelect) return;

    // Show/hide organization fields based on type
    function updateOrgFields() {
        var orgType = orgTypeSelect.value;
        if (orgType === 'individual') {
            orgSelectField.hidden = true;
            orgOtherField.hidden = true;
            if (orgIdInput) orgIdInput.value = '';
        } else {
            orgSelectField.hidden = false;
            populateOrgDropdown();
        }
    }

    // Populate organization dropdown based on country + type
    function populateOrgDropdown() {
        var orgs = window.ORGANIZATIONS_DATA || [];
        var country = countryInput ? countryInput.value.toLowerCase().trim() : '';
        var orgType = orgTypeSelect.value;

        // Clear existing options
        orgSelect.innerHTML = '<option value="">-- Təşkilat seçin --</option>';

        // Filter organizations
        var filtered = orgs.filter(function (org) {
            var matchType = org.org_type === orgType;
            var matchCountry = !country || (org.country && org.country.toLowerCase().indexOf(country) !== -1);
            return matchType && matchCountry;
        });

        filtered.forEach(function (org) {
            var option = document.createElement('option');
            option.value = org.id;
            option.textContent = org.name;
            orgSelect.appendChild(option);
        });

        // Add "Other" option
        var otherOption = document.createElement('option');
        otherOption.value = 'other';
        otherOption.textContent = 'Digər (yeni təşkilat)';
        orgSelect.appendChild(otherOption);
    }

    // Handle org select change
    if (orgSelect) {
        orgSelect.addEventListener('change', function () {
            if (this.value === 'other') {
                orgOtherField.hidden = false;
                if (orgIdInput) orgIdInput.value = '';
            } else {
                orgOtherField.hidden = true;
                if (orgIdInput) orgIdInput.value = this.value;
            }
        });
    }

    orgTypeSelect.addEventListener('change', updateOrgFields);

    // Update org dropdown when country changes
    if (countryInput) {
        countryInput.addEventListener('input', function () {
            if (!orgSelectField.hidden) {
                populateOrgDropdown();
            }
        });
    }

    // Initialize
    updateOrgFields();

    // If form has errors, show all steps (jump to step 3)
    var hasErrors = document.querySelector('.register-global-errors, .register-field-error');
    if (hasErrors) {
        wizardNext(3);
    }
});

// Wizard navigation functions
function wizardNext(step) {
    // Hide all panels
    var panels = document.querySelectorAll('.wizard-panel');
    panels.forEach(function (p) { p.hidden = true; });

    // Show target panel
    var target = document.getElementById('step' + step);
    if (target) target.hidden = false;

    // Update step indicators
    var steps = document.querySelectorAll('.wizard-step');
    steps.forEach(function (s) {
        var sStep = parseInt(s.dataset.step);
        s.classList.toggle('active', sStep === step);
        s.classList.toggle('completed', sStep < step);
    });
}

function wizardBack(step) {
    wizardNext(step);
}
