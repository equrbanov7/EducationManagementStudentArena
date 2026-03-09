/* Lab detail page logic */
(function () {
    'use strict';

    const LAB_ID = window.LAB_CONFIG.labId;
    const CSRF = window.LAB_CONFIG.csrf;
    const END_TIME = new Date(window.LAB_CONFIG.endTime);
    const TOTAL_QUESTIONS = window.LAB_CONFIG.totalQuestions;
    const I18N = window.LAB_I18N || {};
    const t = (key, fallback) => I18N[key] || fallback;
    const finishConfirmModalEl = document.getElementById('finishLabConfirmModal');
    const finishConfirmMessage = document.getElementById('finishLabConfirmMessage');
    const finishUnansweredNotice = document.getElementById('finishLabUnansweredNotice');
    const confirmFinishLabBtn = document.getElementById('confirmFinishLabBtn');
    let finishConfirmModal = null;

    let labStartTime = localStorage.getItem('lab_' + LAB_ID + '_start');
    if (!labStartTime) {
        labStartTime = new Date().toISOString();
        localStorage.setItem('lab_' + LAB_ID + '_start', labStartTime);
    }
    labStartTime = new Date(labStartTime);

    document.querySelectorAll('.file-input').forEach((input) => {
        input.addEventListener('change', function () {
            const questionId = this.id.replace('file-', '');
            const preview = document.getElementById('preview-' + questionId);

            if (this.files && this.files[0]) {
                preview.classList.remove('d-none');
                preview.querySelector('.file-name').textContent = this.files[0].name;
                const textarea = document.querySelector('[name="answer_' + questionId + '"]');
                const answerText = textarea ? textarea.value : '';

                const formData = new FormData();
                formData.append('question_id', questionId);
                formData.append('answer', answerText);
                formData.append('answer_file', this.files[0]);

                fetch('/labs/' + LAB_ID + '/auto-save/', {
                    method: 'POST',
                    body: formData,
                    headers: { 'X-CSRFToken': CSRF },
                })
                    .then((r) => r.json())
                    .then((data) => {
                        const statusEl = document.getElementById('status-' + questionId);
                        statusEl.innerHTML = data.success
                            ? '<i class="fas fa-check-circle text-success"></i> ' + t('statusSaved', 'Saved')
                            : '<i class="fas fa-exclamation-circle text-danger"></i> ' + t('statusError', 'Error');
                    })
                    .catch(() => {
                        // Keep silent; per-question state already visible
                    });
            }
        });
    });

    window.removeFile = function (questionId) {
        document.getElementById('file-' + questionId).value = '';
        document.getElementById('preview-' + questionId).classList.add('d-none');
    };

    function updateTimers() {
        const now = new Date();
        const elapsed = Math.floor((now - labStartTime) / 1000);
        const elapsedEl = document.getElementById('elapsedTimer');
        if (elapsedEl) elapsedEl.textContent = formatTime(elapsed);

        const remaining = Math.max(0, Math.floor((END_TIME - now) / 1000));
        const remainingEl = document.getElementById('remainingTimer');
        if (remainingEl) remainingEl.textContent = formatDuration(remaining);

        if (remaining <= 0) {
            const form = document.getElementById('labForm');
            if (form) form.submit();
        }
    }

    function formatTime(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    }

    function formatDuration(seconds) {
        const days = Math.floor(seconds / 86400);
        const h = Math.floor((seconds % 86400) / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        if (days > 0) {
            return (
                String(days).padStart(2, '0') +
                ':' +
                String(h).padStart(2, '0') +
                ':' +
                String(m).padStart(2, '0') +
                ':' +
                String(s).padStart(2, '0')
            );
        }
        return formatTime(seconds);
    }

    setInterval(updateTimers, 1000);
    updateTimers();

    function updateProgress() {
        const answeredEl = document.getElementById('answeredCount');
        const progressEl = document.getElementById('progressBar');
        if (!answeredEl || !progressEl) return;

        let answered = 0;
        document.querySelectorAll('.answer-textarea').forEach((ta) => {
            if (ta.value.trim()) answered += 1;
        });

        answeredEl.textContent = answered;
        progressEl.style.width = (answered / TOTAL_QUESTIONS) * 100 + '%';
    }

    const saveTimeouts = {};

    document.querySelectorAll('.answer-textarea').forEach((ta) => {
        ta.addEventListener('input', function () {
            const card = this.closest('.question-card');
            const qId = card.dataset.questionId;

            clearTimeout(saveTimeouts[qId]);
            saveTimeouts[qId] = setTimeout(() => {
                autoSave(qId, ta.value);
            }, 800);
        });
    });

    function autoSave(questionId, answer) {
        const statusEl = document.getElementById('status-' + questionId);
        statusEl.innerHTML = '<i class="fas fa-spinner fa-spin text-primary"></i> ' + t('statusSaving', 'Saving...');

        fetch('/labs/' + LAB_ID + '/auto-save/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF,
            },
            body: JSON.stringify({
                question_id: questionId,
                answer: answer,
            }),
        })
            .then((r) => r.json())
            .then((data) => {
                statusEl.innerHTML = data.success
                    ? '<i class="fas fa-check-circle text-success"></i> ' + t('statusSaved', 'Saved')
                    : '<i class="fas fa-exclamation-circle text-danger"></i> ' + t('statusError', 'Error');

                updateProgress();
            })
            .catch(() => {
                statusEl.innerHTML = '<i class="fas fa-exclamation-circle text-danger"></i> ' + t('statusError', 'Error');
            });
    }

    updateProgress();

    document.querySelectorAll('.question-toggle-btn').forEach((btn) => {
        btn.addEventListener('click', function () {
            const questionId = this.dataset.toggleQuestion;
            const card = document.getElementById('question-' + questionId);
            if (!card) return;
            const collapsed = card.classList.toggle('question-collapsed');
            const icon = this.querySelector('i');
            if (icon) {
                icon.classList.toggle('fa-chevron-down', collapsed);
                icon.classList.toggle('fa-chevron-up', !collapsed);
            }
        });
    });

    const labForm = document.getElementById('labForm');
    if (!labForm) return;

    function getUnansweredCount() {
        const answeredEl = document.getElementById('answeredCount');
        const answered = answeredEl ? parseInt(answeredEl.textContent, 10) : 0;
        return TOTAL_QUESTIONS - (isNaN(answered) ? 0 : answered);
    }

    function setSubmitButtonState(isSubmitting) {
        const btn = document.getElementById('submitBtn');
        if (!btn) return;
        btn.disabled = isSubmitting;
        btn.innerHTML = isSubmitting
            ? '<span class="spinner-border spinner-border-sm me-2"></span> ' + t('actionSubmitting', 'Submitting...')
            : '<i class="fas fa-paper-plane me-2"></i> ' + t('actionFinishLab', 'Finish Lab');
    }

    function setConfirmButtonState(isSubmitting) {
        if (confirmFinishLabBtn) confirmFinishLabBtn.disabled = isSubmitting;
    }

    function updateFinishConfirmContent(unanswered) {
        if (finishConfirmMessage) {
            finishConfirmMessage.textContent = t(
                'confirmFinishDescription',
                'After finishing the lab, you will not be able to return and edit it.'
            );
        }

        if (!finishUnansweredNotice) return;

        if (unanswered > 0) {
            finishUnansweredNotice.textContent = t('confirmUnanswered', '{count} questions are unanswered. Submit?').replace(
                '{count}',
                unanswered
            );
            finishUnansweredNotice.classList.remove('d-none');
        } else {
            finishUnansweredNotice.textContent = '';
            finishUnansweredNotice.classList.add('d-none');
        }
    }

    function getFinishConfirmModal() {
        if (!finishConfirmModalEl || !window.bootstrap) return null;
        if (!finishConfirmModal) {
            finishConfirmModal = new window.bootstrap.Modal(finishConfirmModalEl);
        }
        return finishConfirmModal;
    }

    function submitLabForm() {
        setSubmitButtonState(true);
        setConfirmButtonState(true);

        fetch('/labs/' + LAB_ID + '/submit/', {
            method: 'POST',
            body: new FormData(labForm),
            headers: { 'X-CSRFToken': CSRF },
        })
            .then((r) => r.json())
            .then((data) => {
                if (data.success) {
                    localStorage.removeItem('lab_' + LAB_ID + '_start');
                    window.location.href = data.redirect_url || '/';
                } else {
                    alert(t('errorPrefix', 'Error') + ': ' + (data.error || t('errorUnknown', 'Unknown error')));
                    setSubmitButtonState(false);
                    setConfirmButtonState(false);
                }
            })
            .catch(() => {
                alert(t('errorServer', 'Server error'));
                setSubmitButtonState(false);
                setConfirmButtonState(false);
            });
    }

    if (confirmFinishLabBtn) {
        confirmFinishLabBtn.addEventListener('click', function () {
            const modal = getFinishConfirmModal();
            if (modal) modal.hide();
            submitLabForm();
        });
    }

    labForm.addEventListener('submit', function (e) {
        e.preventDefault();

        const unanswered = getUnansweredCount();

        const modal = getFinishConfirmModal();
        if (!modal) {
            let confirmText = t(
                'confirmFinishDescription',
                'After finishing the lab, you will not be able to return and edit it.'
            );
            if (unanswered > 0) {
                confirmText +=
                    '\n\n' +
                    t('confirmUnanswered', '{count} questions are unanswered. Submit?').replace('{count}', unanswered);
            }
            if (!confirm(confirmText)) return;
            submitLabForm();
            return;
        }

        updateFinishConfirmContent(unanswered);
        modal.show();
    });
})();
