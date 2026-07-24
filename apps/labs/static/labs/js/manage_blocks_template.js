/*
 * manage_blocks_template.js
 * Source: apps/labs/templates/labs/manage_blocks.html (inline config skript)
 * Populates window.LAB_CONFIG / window.LAB_I18N from #manageBlocksConfig data-*
 * BEFORE manage_blocks.js runs. CSRF from EMSCore.
 */
(function () {
    "use strict";

    var el = document.getElementById("manageBlocksConfig");
    if (!el) { return; }
    var d = el.dataset;

    window.LAB_CONFIG = {
        labId: parseInt(d.labId, 10),
        csrf: EMSCore.getCsrfToken()
    };

    window.LAB_I18N = {
        fileExisting: d.i18nFileExisting,
        stateCreating: d.i18nStateCreating,
        stateSaving: d.i18nStateSaving,
        stateAdding: d.i18nStateAdding,
        stateImporting: d.i18nStateImporting,
        actionCreate: d.i18nActionCreate,
        actionSave: d.i18nActionSave,
        actionAdd: d.i18nActionAdd,
        actionImport: d.i18nActionImport,
        successImportDefault: d.i18nSuccessImportDefault,
        errorPrefix: d.i18nErrorPrefix,
        errorUnknown: d.i18nErrorUnknown,
        errorServer: d.i18nErrorServer,
        confirmDeleteBlock: d.i18nConfirmDeleteBlock,
        confirmDeleteQuestion: d.i18nConfirmDeleteQuestion
    };
})();
