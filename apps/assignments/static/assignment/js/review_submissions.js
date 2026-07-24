/*
 * review_submissions.js
 * Source: apps/assignments/templates/assignments/partials/_review_submissions_js.html
 * Grade-review modal population, integer grade normalization, review
 * countdowns, AJAX grade submit (confirm-gated), and optional bulk delete.
 * i18n / selected-submission / can-delete read from #reviewSubmissionsConfig
 * data-*; CSRF from EMSCore.
 */
(function () {
    "use strict";

    var bound = false;

    function getCfg() {
        return document.getElementById("reviewSubmissionsConfig");
    }

    function parseIntegerGrade(rawValue) {
        var normalized = (rawValue || "").trim().replace(",", ".");
        if (!normalized) { return null; }
        var match = normalized.match(/^-?\d+/);
        if (!match) { return null; }
        var parsed = parseInt(match[0], 10);
        return Number.isNaN(parsed) ? null : parsed;
    }

    function normalizeGradeInput(input) {
        if (!input) { return; }
        var max = parseInt(input.getAttribute("max") || "0", 10);
        var parsed = parseIntegerGrade(input.value);
        if (parsed === null) {
            input.value = "";
            return;
        }
        var nextValue = parsed;
        if (nextValue < 0) { nextValue = 0; }
        if (!Number.isNaN(max) && max > 0 && nextValue > max) { nextValue = max; }
        input.value = String(nextValue);
    }

    function setupReviewCountdowns() {
        document.querySelectorAll("[data-review-countdown]").forEach(function (node) {
            var secondsLeft = parseInt(node.getAttribute("data-review-countdown"), 10);
            if (Number.isNaN(secondsLeft) || secondsLeft <= 0) {
                node.textContent = "00:00:00";
                return;
            }

            function render() {
                var hours = Math.floor(secondsLeft / 3600);
                var minutes = Math.floor((secondsLeft % 3600) / 60);
                var seconds = secondsLeft % 60;
                node.textContent = String(hours).padStart(2, "0") + ":" +
                    String(minutes).padStart(2, "0") + ":" +
                    String(seconds).padStart(2, "0");
            }

            render();
            window.setInterval(function () {
                secondsLeft = Math.max(0, secondsLeft - 1);
                render();
            }, 1000);
        });
    }

    function openSubmission(button) {
        if (!button) { return; }
        var cfg = getCfg();
        var i18n = cfg ? cfg.dataset : {};

        var submissionId = button.dataset.id;
        var student = button.dataset.student;
        var content = button.dataset.content;
        var file = button.dataset.file;
        var filename = button.dataset.filename;
        var grade = button.dataset.grade;
        var feedback = button.dataset.feedback;
        var canEdit = button.dataset.canEdit === "1";
        var actionCode = button.dataset.actionCode;
        var countdownMode = button.dataset.countdownMode;

        var gradeInput = document.getElementById("grade-input");
        var feedbackInput = document.getElementById("feedback-input");
        var submitButton = document.getElementById("gradeSubmitButton");
        var reviewNote = document.getElementById("modal-review-note");

        document.getElementById("submission-id").value = submissionId;
        document.getElementById("modal-student").textContent = student;
        document.getElementById("modal-content").textContent = content || "(" + i18n.i18nNoText + ")";
        gradeInput.value = grade || "";
        feedbackInput.value = feedback;
        normalizeGradeInput(gradeInput);
        gradeInput.disabled = !canEdit;
        feedbackInput.disabled = !canEdit;
        submitButton.classList.toggle("d-none", !canEdit);
        submitButton.innerHTML = '<i class="fa-solid fa-check-circle"></i> ' + (
            actionCode === "recheck" ? i18n.i18nReviewAgain : i18n.i18nReviewNow
        );

        reviewNote.className = "alert d-none";
        reviewNote.textContent = "";
        if (!canEdit) {
            reviewNote.className = "alert alert-secondary";
            reviewNote.textContent = i18n.i18nReviewLocked;
        } else if (countdownMode === "recheck") {
            reviewNote.className = "alert alert-warning";
            reviewNote.textContent = i18n.i18nRecheckWindow;
        } else if (countdownMode === "identity") {
            reviewNote.className = "alert alert-warning";
            reviewNote.textContent = i18n.i18nIdentityWindow;
        }

        var fileContainer = document.getElementById("modal-file-container");
        if (file) {
            fileContainer.classList.remove("d-none");
            document.getElementById("modal-file-link").href = file;
            document.getElementById("modal-file-name").textContent = filename || i18n.i18nDownload;
        } else {
            fileContainer.classList.add("d-none");
        }
    }

    function submitGradeForm() {
        var cfg = getCfg();
        var i18n = cfg ? cfg.dataset : {};
        var submissionId = document.getElementById("submission-id").value;
        var gradeForm = document.getElementById("gradeForm");
        if (!gradeForm) {
            return Promise.resolve(false);
        }
        normalizeGradeInput(document.getElementById("grade-input"));
        var formData = new FormData(gradeForm);
        var btn = document.getElementById("gradeSubmitButton");

        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> ' + i18n.i18nSubmitting;

        return fetch("/assignments/submission/" + submissionId + "/grade/", {
            method: "POST",
            headers: {
                "X-CSRFToken": EMSCore.getCsrfToken(),
                "X-Requested-With": "XMLHttpRequest"
            },
            body: formData
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    location.reload();
                    return true;
                }
                alert(i18n.i18nErrorPrefix + ": " + (data.error || i18n.i18nUnknownError));
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-check-circle"></i> ' + i18n.i18nGradeSubmit;
                return false;
            })
            .catch(function (err) {
                console.error(err);
                alert(i18n.i18nServerError);
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-check-circle"></i> ' + i18n.i18nGradeSubmit;
                return false;
            });
    }

    function init() {
        if (bound) { return; }
        var cfg = getCfg();
        if (!cfg) { return; }
        bound = true;
        var i18n = cfg.dataset;

        if (window.EMSDelegate) {
            window.EMSDelegate.on("click", ".view-submission-btn", function (e, btn) {
                openSubmission(btn);
            });
        } else {
            document.querySelectorAll(".view-submission-btn").forEach(function (btn) {
                btn.addEventListener("click", function () { openSubmission(this); });
            });
        }

        var gradeInputEl = document.getElementById("grade-input");
        if (gradeInputEl) {
            gradeInputEl.addEventListener("blur", function () {
                normalizeGradeInput(this);
            });
        }

        setupReviewCountdowns();

        var selectedSubmissionId = i18n.selectedSubmissionId;
        if (selectedSubmissionId) {
            var targetButton = document.querySelector('.view-submission-btn[data-id="' + selectedSubmissionId + '"]');
            if (targetButton) {
                openSubmission(targetButton);
                if (window.bootstrap && window.bootstrap.Modal) {
                    var modal = window.bootstrap.Modal.getOrCreateInstance(document.getElementById("submissionModal"));
                    modal.show();
                } else {
                    targetButton.click();
                }
            }
        }

        var gradeForm = document.getElementById("gradeForm");
        if (gradeForm) {
            gradeForm.addEventListener("submit", function (e) {
                e.preventDefault();
                if (typeof window.openActionConfirmModal === "function") {
                    var gsb = document.getElementById("gradeSubmitButton");
                    window.openActionConfirmModal({
                        title: i18n.i18nConfirmTitle,
                        message: i18n.i18nConfirmMessage,
                        confirmLabel: (gsb && gsb.textContent.trim()) || i18n.i18nGradeSubmit,
                        confirmButtonClass: "btn btn-success",
                        onConfirm: submitGradeForm
                    });
                    return;
                }
                submitGradeForm();
            });
        }

        if (i18n.canDelete === "1" && typeof window.initResultsBulkActions === "function") {
            window.initResultsBulkActions({
                checkboxSelector: ".js-assignment-submission-checkbox",
                selectedCountSelector: "#selectedAssignmentCount",
                selectAllSelector: "#selectAllAssignmentsBtn",
                clearSelector: "#clearAssignmentsBtn",
                deleteSelectedSelector: "#deleteSelectedAssignmentsBtn",
                singleDeleteSelector: ".js-single-delete-assignment-submission",
                deleteFormSelector: "#deleteAssignmentsForm",
                deleteInputsSelector: "#deleteAssignmentsInputs",
                confirmButtonSelector: "#confirmDeleteAssignmentsBtn",
                confirmModalSelector: "#deleteAssignmentsConfirmModal",
                inputName: "submission_ids",
                singleDeleteDataAttribute: "submissionId"
            });
        }
    }

    if (window.EMSReady) { window.EMSReady(init); }
    else { document.addEventListener("DOMContentLoaded", init); }
})();
