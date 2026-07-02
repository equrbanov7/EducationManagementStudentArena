/* Step 1: country selection. */

function initRegisterWizardStep1() {
    if (countrySelect) {
        countrySelect.addEventListener("change", function () {
            updateStep2State();
        });
    }
}
