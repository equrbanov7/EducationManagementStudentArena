/* Lab detail page logic */
(function () {
    'use strict';

    const LAB_ID = window.LAB_CONFIG.labId;
    const CSRF = window.LAB_CONFIG.csrf;
    const END_TIME = new Date(window.LAB_CONFIG.endTime);
    const TOTAL_QUESTIONS = window.LAB_CONFIG.totalQuestions;
    const I18N = window.LAB_I18N || {};
    const t = (key, fallback) => I18N[key] || fallback;

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

                const formData = new FormData();
                formData.append('question_id', questionId);
                formData.append('answer', '');
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
        document.getElementById('elapsedTimer').textContent = formatTime(elapsed);

        const remaining = Math.max(0, Math.floor((END_TIME - now) / 1000));
        document.getElementById('remainingTimer').textContent = formatTime(remaining);

        if (remaining <= 0) {
            document.getElementById('labForm').submit();
        }
    }

    function formatTime(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    }

    setInterval(updateTimers, 1000);
    updateTimers();

    function updateProgress() {
        let answered = 0;
        document.querySelectorAll('.answer-textarea').forEach((ta) => {
            if (ta.value.trim()) answered += 1;
        });

        document.getElementById('answeredCount').textContent = answered;
        document.getElementById('progressBar').style.width = (answered / TOTAL_QUESTIONS) * 100 + '%';
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

    document.getElementById('labForm').addEventListener('submit', function (e) {
        e.preventDefault();

        const answered = parseInt(document.getElementById('answeredCount').textContent, 10);
        const unanswered = TOTAL_QUESTIONS - answered;

        if (unanswered > 0) {
            const confirmText = t('confirmUnanswered', '{count} questions are unanswered. Submit?').replace(
                '{count}',
                unanswered
            );
            if (!confirm(confirmText)) {
                return;
            }
        }

        const btn = document.getElementById('submitBtn');
        btn.disabled = true;
        btn.innerHTML =
            '<span class="spinner-border spinner-border-sm me-2"></span> ' + t('actionSubmitting', 'Submitting...');

        fetch('/labs/' + LAB_ID + '/submit/', {
            method: 'POST',
            body: new FormData(this),
            headers: { 'X-CSRFToken': CSRF },
        })
            .then((r) => r.json())
            .then((data) => {
                if (data.success) {
                    localStorage.removeItem('lab_' + LAB_ID + '_start');
                    window.location.href = data.redirect_url || '/';
                } else {
                    alert(t('errorPrefix', 'Error') + ': ' + (data.error || t('errorUnknown', 'Unknown error')));
                    btn.disabled = false;
                    btn.innerHTML =
                        '<i class="fas fa-paper-plane me-2"></i> ' + t('actionFinishLab', 'Finish Lab');
                }
            })
            .catch(() => {
                alert(t('errorServer', 'Server error'));
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-paper-plane me-2"></i> ' + t('actionFinishLab', 'Finish Lab');
            });
    });
})();
