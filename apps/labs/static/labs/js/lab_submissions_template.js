/*
 * lab_submissions_template.js
 * Source: apps/labs/templates/labs/lab_submissions.html (inline skript)
 * Wires the shared results bulk-delete actions when deletion is allowed.
 * can-delete flag read from #labSubmissionsConfig data-*.
 */
(function () {
    "use strict";

    var cfg = document.getElementById("labSubmissionsConfig");
    if (!cfg || cfg.dataset.canDelete !== "1") { return; }
    if (typeof window.initResultsBulkActions !== "function") { return; }

    window.initResultsBulkActions({
        checkboxSelector: ".js-lab-submission-checkbox",
        selectedCountSelector: "#selectedLabCount",
        selectAllSelector: "#selectAllLabsBtn",
        clearSelector: "#clearLabsBtn",
        deleteSelectedSelector: "#deleteSelectedLabsBtn",
        singleDeleteSelector: ".js-single-delete-lab-submission",
        deleteFormSelector: "#deleteLabsForm",
        deleteInputsSelector: "#deleteLabsInputs",
        confirmButtonSelector: "#confirmDeleteLabsBtn",
        confirmModalSelector: "#deleteLabsConfirmModal",
        inputName: "submission_ids",
        singleDeleteDataAttribute: "submissionId"
    });
})();
