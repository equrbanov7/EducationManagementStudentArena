/* Grade submission interactions */
(function () {
    'use strict';

    const totalInput = document.getElementById('totalScoreInput');
    const useManual = document.getElementById('useManualTotal');
    const useManualHidden = document.getElementById('useManualTotalHidden');
    const scoreInputs = Array.from(document.querySelectorAll('.answer-score-input'));

    function sanitizePerQuestion(input) {
        const max = parseFloat(input.dataset.questionMax || '0');
        let val = parseFloat(input.value || '0');
        if (isNaN(val) || val < 0) val = 0;
        if (max > 0 && val > max) val = max;
        input.value = val;
        return val;
    }

    function recalcTotal() {
        if (!totalInput || !useManual || useManual.checked) return;
        const sum = scoreInputs.reduce((acc, input) => acc + sanitizePerQuestion(input), 0);
        totalInput.value = sum.toFixed(2);
    }

    scoreInputs.forEach((input) => {
        input.addEventListener('input', recalcTotal);
        input.addEventListener('blur', recalcTotal);
    });

    if (useManual && useManualHidden) {
        useManual.addEventListener('change', function () {
            useManualHidden.value = this.checked ? '1' : '0';
            if (!this.checked) recalcTotal();
        });
    }

    recalcTotal();

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
