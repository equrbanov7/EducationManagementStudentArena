/* Grade submission interactions */
(function () {
    'use strict';

    const totalInput = document.getElementById('totalScoreInput');
    const gradeForm = document.getElementById('gradeForm');
    const scoreInputs = Array.from(document.querySelectorAll('.answer-score-input'));

    let manualTotalActive = totalInput && totalInput.dataset.manualTotalInitial === '1';
    let submitConfirmed = false;

    function formatScoreValue(value) {
        return String(value);
    }

    function parseIntegerValue(rawValue) {
        const normalized = (rawValue || '').trim().replace(',', '.');
        if (!normalized) return null;
        const match = normalized.match(/^-?\d+/);
        if (!match) return null;
        const parsed = parseInt(match[0], 10);
        return Number.isNaN(parsed) ? null : parsed;
    }

    function getQuestionMax(input) {
        const parsed = parseInt(input.dataset.questionMax || '0', 10);
        return Number.isNaN(parsed) ? 0 : parsed;
    }

    function normalizePerQuestion(input) {
        const parsed = parseIntegerValue(input.value);
        if (parsed === null) {
            input.value = '';
            return 0;
        }

        let nextValue = parsed;
        if (nextValue < 0) nextValue = 0;
        const max = getQuestionMax(input);
        if (max > 0 && nextValue > max) nextValue = max;
        input.value = formatScoreValue(nextValue);
        return nextValue;
    }

    function recalcTotal() {
        if (!totalInput || !scoreInputs.length || manualTotalActive) return;
        const sum = scoreInputs.reduce((acc, input) => acc + normalizePerQuestion(input), 0);
        totalInput.value = formatScoreValue(sum);
    }

    scoreInputs.forEach((input) => {
        input.addEventListener('input', recalcTotal);
        input.addEventListener('blur', function () {
            normalizePerQuestion(this);
            recalcTotal();
        });
    });

    if (totalInput && !totalInput.disabled) {
        totalInput.addEventListener('input', function () {
            const raw = (this.value || '').trim();
            if (!raw) {
                manualTotalActive = false;
                recalcTotal();
                return;
            }
            manualTotalActive = true;
        });

        totalInput.addEventListener('blur', function () {
            const parsed = parseIntegerValue(this.value);
            if (parsed === null) {
                manualTotalActive = false;
                recalcTotal();
                return;
            }

            let nextValue = parsed;
            if (nextValue < 0) nextValue = 0;
            const max = parseInt(this.getAttribute('max') || '0', 10);
            if (!Number.isNaN(max) && max > 0 && nextValue > max) nextValue = max;
            this.value = formatScoreValue(nextValue);
        });
    }

    if (!manualTotalActive && scoreInputs.length) {
        recalcTotal();
    }

    if (gradeForm) {
        gradeForm.addEventListener('submit', function (event) {
            const submitButton = gradeForm.querySelector('button[type="submit"]');
            if (submitConfirmed || !submitButton || submitButton.disabled) {
                submitConfirmed = false;
                return;
            }

            event.preventDefault();

            if (typeof window.openActionConfirmModal !== 'function') {
                submitConfirmed = true;
                if (typeof gradeForm.requestSubmit === 'function') {
                    gradeForm.requestSubmit();
                } else {
                    gradeForm.submit();
                }
                return;
            }

            window.openActionConfirmModal({
                title: gettext('Qiymətləndirməni təsdiqləyin'),
                message: gettext('Bu bal və rəyi saxlamaq istədiyinizə əminsiniz?'),
                confirmLabel: submitButton.textContent.trim(),
                confirmButtonClass: 'btn btn-success',
                onConfirm: function () {
                    submitConfirmed = true;
                    if (typeof gradeForm.requestSubmit === 'function') {
                        gradeForm.requestSubmit();
                    } else {
                        gradeForm.submit();
                    }
                }
            });
        });
    }

    document.querySelectorAll('.answer-toggle-btn').forEach((btn) => {
        btn.addEventListener('click', function () {
            const id = this.dataset.gradeToggle;
            const card = document.getElementById('grade-answer-' + id);
            if (!card) return;
            const collapsed = card.classList.toggle('answer-collapsed');
            const icon = this.querySelector('i');
            if (icon) {
                icon.classList.toggle('fa-chevron-down', collapsed);
                icon.classList.toggle('fa-chevron-up', !collapsed);
            }
        });
    });
})();
