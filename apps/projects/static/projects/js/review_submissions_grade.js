/*
 * review_submissions_grade.js
 * Source: apps/projects/templates/projects/partials/_review_submissions_js.html
 * Cavaba baxış modalı, bal normalizasiyası, geri sayım və AJAX qiymətləndirmə.
 * Config (#project-review-config data-*), CSRF EMSCore-dan. Davranış inline ilə eyni.
 */
window.EMSReady(function () {
    const cfgEl = document.getElementById('project-review-config');
    if (!cfgEl || cfgEl.dataset.prBound === '1') return;
    cfgEl.dataset.prBound = '1';

    const cfg = cfgEl.dataset;
    const i18n = {
        noContent: cfg.i18nNoContent,
        download: cfg.i18nDownload,
        sending: cfg.i18nSending,
        errorPrefix: cfg.i18nErrorPrefix,
        unknownError: cfg.i18nUnknownError,
        serverError: cfg.i18nServerError,
        gradeButton: cfg.i18nGradeButton,
        reviewLocked: cfg.i18nReviewLocked,
        identityWindow: cfg.i18nIdentityWindow,
        recheckWindow: cfg.i18nRecheckWindow,
        reviewNow: cfg.i18nReviewNow,
        reviewAgain: cfg.i18nReviewAgain,
        confirmTitle: cfg.i18nConfirmTitle,
        confirmMessage: cfg.i18nConfirmMessage,
    };
    const selectedSubmissionId = cfg.selectedSubmissionId;
    const gradeUrlTemplate = '/projects/submission/__ID__/grade/';
    const getCsrf = () => (window.EMSCore && EMSCore.getCsrfToken())
        || document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

    function parseIntegerGrade(rawValue) {
        const normalized = (rawValue || '').trim().replace(',', '.');
        if (!normalized) return null;
        const match = normalized.match(/^-?\d+/);
        if (!match) return null;
        const parsed = parseInt(match[0], 10);
        return Number.isNaN(parsed) ? null : parsed;
    }

    function normalizeGradeInput(input) {
        if (!input) return;
        const max = parseInt(input.getAttribute('max') || '0', 10);
        const parsed = parseIntegerGrade(input.value);
        if (parsed === null) {
            input.value = '';
            return;
        }
        let nextValue = parsed;
        if (nextValue < 0) nextValue = 0;
        if (!Number.isNaN(max) && max > 0 && nextValue > max) nextValue = max;
        input.value = String(nextValue);
    }

    function setupReviewCountdowns() {
        document.querySelectorAll('[data-review-countdown]').forEach(function (node) {
            let secondsLeft = parseInt(node.getAttribute('data-review-countdown'), 10);
            if (Number.isNaN(secondsLeft) || secondsLeft <= 0) {
                node.textContent = '00:00:00';
                return;
            }

            function render() {
                const hours = Math.floor(secondsLeft / 3600);
                const minutes = Math.floor((secondsLeft % 3600) / 60);
                const seconds = secondsLeft % 60;
                node.textContent = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            }

            render();
            window.setInterval(function () {
                secondsLeft = Math.max(0, secondsLeft - 1);
                render();
            }, 1000);
        });
    }

    function openSubmission(button) {
        if (!button) return;

        const submissionId = button.dataset.id;
        const student = button.dataset.student;
        const content = button.dataset.content;
        const file = button.dataset.file;
        const filename = button.dataset.filename;
        const grade = button.dataset.grade;
        const feedback = button.dataset.feedback;
        const canEdit = button.dataset.canEdit === '1';
        const actionCode = button.dataset.actionCode;
        const countdownMode = button.dataset.countdownMode;

        const gradeInput = document.getElementById('grade-input');
        const feedbackInput = document.getElementById('feedback-input');
        const submitButton = document.getElementById('gradeSubmitButton');
        const reviewNote = document.getElementById('modal-review-note');

        document.getElementById('submission-id').value = submissionId;
        document.getElementById('modal-student').textContent = student;
        document.getElementById('modal-content').textContent = content || i18n.noContent;
        gradeInput.value = grade || '';
        feedbackInput.value = feedback;
        normalizeGradeInput(gradeInput);
        gradeInput.disabled = !canEdit;
        feedbackInput.disabled = !canEdit;
        submitButton.classList.toggle('d-none', !canEdit);
        submitButton.innerHTML = '<i class="fa-solid fa-check-circle"></i> ' + (
            actionCode === 'recheck' ? i18n.reviewAgain : i18n.reviewNow
        );

        reviewNote.className = 'alert d-none';
        reviewNote.textContent = '';
        if (!canEdit) {
            reviewNote.className = 'alert alert-secondary';
            reviewNote.textContent = i18n.reviewLocked;
        } else if (countdownMode === 'recheck') {
            reviewNote.className = 'alert alert-warning';
            reviewNote.textContent = i18n.recheckWindow;
        } else if (countdownMode === 'identity') {
            reviewNote.className = 'alert alert-warning';
            reviewNote.textContent = i18n.identityWindow;
        }

        if (file) {
            document.getElementById('modal-file-container').style.display = 'block';
            document.getElementById('modal-file-link').href = file;
            document.getElementById('modal-file-name').textContent = filename || i18n.download;
        } else {
            document.getElementById('modal-file-container').style.display = 'none';
        }
    }

    document.querySelectorAll('.view-submission-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            openSubmission(this);
        });
    });

    const projectGradeInput = document.getElementById('grade-input');
    if (projectGradeInput) {
        projectGradeInput.addEventListener('blur', function () {
            normalizeGradeInput(this);
        });
    }

    setupReviewCountdowns();

    if (selectedSubmissionId) {
        const targetButton = document.querySelector('.view-submission-btn[data-id="' + selectedSubmissionId + '"]');
        if (targetButton) {
            openSubmission(targetButton);
            if (window.bootstrap && window.bootstrap.Modal) {
                const modal = window.bootstrap.Modal.getOrCreateInstance(document.getElementById('submissionModal'));
                modal.show();
            } else {
                targetButton.click();
            }
        }
    }

    function submitGradeForm() {
        const submissionId = document.getElementById('submission-id').value;
        const gradeForm = document.getElementById('gradeForm');
        if (!gradeForm) {
            return Promise.resolve(false);
        }
        normalizeGradeInput(document.getElementById('grade-input'));
        const formData = new FormData(gradeForm);
        const btn = document.getElementById('gradeSubmitButton');

        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> ' + i18n.sending;

        const gradeUrl = gradeUrlTemplate.replace('__ID__', submissionId);

        return fetch(gradeUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrf(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData
        })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    location.reload();
                    return true;
                } else {
                    alert(`${i18n.errorPrefix}${data.error || i18n.unknownError}`);
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fa-solid fa-check-circle"></i> ' + i18n.gradeButton;
                    return false;
                }
            })
            .catch(err => {
                console.error(err);
                alert(i18n.serverError);
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-check-circle"></i> ' + i18n.gradeButton;
                return false;
            });
    }

    document.getElementById('gradeForm')?.addEventListener('submit', function(e) {
        e.preventDefault();

        if (typeof window.openActionConfirmModal === 'function') {
            window.openActionConfirmModal({
                title: i18n.confirmTitle,
                message: i18n.confirmMessage,
                confirmLabel: document.getElementById('gradeSubmitButton')?.textContent.trim() || i18n.gradeButton,
                confirmButtonClass: 'btn btn-success',
                onConfirm: submitGradeForm
            });
            return;
        }

        submitGradeForm();
    });

    if (cfg.canDelete === '1') {
        window.initResultsBulkActions({
            checkboxSelector: '.js-project-submission-checkbox',
            selectedCountSelector: '#selectedProjectCount',
            selectAllSelector: '#selectAllProjectsBtn',
            clearSelector: '#clearProjectsBtn',
            deleteSelectedSelector: '#deleteSelectedProjectsBtn',
            singleDeleteSelector: '.js-single-delete-project-submission',
            deleteFormSelector: '#deleteProjectsForm',
            deleteInputsSelector: '#deleteProjectsInputs',
            confirmButtonSelector: '#confirmDeleteProjectsBtn',
            confirmModalSelector: '#deleteProjectsConfirmModal',
            inputName: 'submission_ids',
            singleDeleteDataAttribute: 'submissionId'
        });
    }
});
