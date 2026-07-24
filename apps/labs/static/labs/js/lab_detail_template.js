/*
 * lab_detail_template.js
 * Source: apps/labs/templates/labs/lab_detail.html (inline config skript)
 * Populates window.LAB_CONFIG / window.LAB_I18N from #labDetailConfig data-*
 * BEFORE lab_detail.js runs. CSRF from EMSCore.
 */
(function () {
    "use strict";

    var el = document.getElementById("labDetailConfig");
    if (!el) { return; }
    var d = el.dataset;

    window.LAB_CONFIG = {
        labId: parseInt(d.labId, 10),
        csrf: EMSCore.getCsrfToken(),
        endTime: d.endTime,
        totalQuestions: parseInt(d.totalQuestions, 10)
    };

    window.LAB_I18N = {
        statusSaved: d.i18nStatusSaved,
        statusSaving: d.i18nStatusSaving,
        statusError: d.i18nStatusError,
        confirmUnanswered: d.i18nConfirmUnanswered,
        confirmFinishDescription: d.i18nConfirmFinishDescription,
        actionSubmitting: d.i18nActionSubmitting,
        errorPrefix: d.i18nErrorPrefix,
        errorUnknown: d.i18nErrorUnknown,
        errorServer: d.i18nErrorServer,
        actionFinishLab: d.i18nActionFinishLab
    };
})();
