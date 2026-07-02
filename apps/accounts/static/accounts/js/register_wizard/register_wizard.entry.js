/* Registration wizard entrypoint. */
(function () {
    "use strict";

    function initRegisterWizard() {
        if (window.EMSRegisterWizard.initialized) {
            return;
        }
        window.EMSRegisterWizard.initialized = true;

        setupRegisterWizardState();
        exposeRegisterWizardDraftHooks();
        migrateLegacySignupDraft();

        [countrySelect, registrationTypeSelect].forEach(function (select) {
            enhanceBootstrapSelect(select);
        });

        initRegisterWizardStep1();
        initRegisterWizardStep2();
        initRegisterWizardStep3();
        initRegisterWizardSubmitModule();

        clearUnsupportedIndividualSelection();
        updateStep2State();
        updateStep3State();
        revealInitialErrorOrRestoreDraft();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initRegisterWizard);
    } else {
        initRegisterWizard();
    }
})();
