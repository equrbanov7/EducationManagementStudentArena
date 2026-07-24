/* My lab answers page interactions */
(function () {
    'use strict';

    document.querySelectorAll('.answer-toggle-btn').forEach((btn) => {
        btn.addEventListener('click', function () {
            const id = this.dataset.answerToggle;
            const card = document.getElementById('answer-item-' + id);
            if (!card) return;
            const collapsed = card.classList.toggle('answer-collapsed');
            const icon = this.querySelector('i');
            if (icon) {
                icon.classList.toggle('fa-chevron-down', collapsed);
                icon.classList.toggle('fa-chevron-up', !collapsed);
            }
        });
    });

    const cfgEl = document.getElementById('labAnswersConfig');
    const preopenModalId = (cfgEl && cfgEl.dataset.preopenModal) || window.LAB_ANSWERS_PREOPEN_MODAL;
    if (preopenModalId && window.bootstrap) {
        const modalEl = document.getElementById(preopenModalId);
        if (modalEl) {
            window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }
    }
})();
