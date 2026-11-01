/* UI only: existing canonical joint POST forms remain the write authority. */
(() => {
    'use strict';
    const root = document.querySelector('[data-joint-journal]');
    if (!root) return;
    const dialog = root.querySelector('[data-joint-lesson-dialog]');
    const opener = root.querySelector('[data-joint-open-lesson]');
    if (dialog && opener) {
        opener.addEventListener('click', () => dialog.showModal());
        root.querySelectorAll('[data-joint-close-lesson]').forEach(button => {
            button.addEventListener('click', () => dialog.close());
        });
        dialog.addEventListener('close', () => opener.focus());
    }
    root.querySelectorAll('[data-joint-cell]').forEach(cell => {
        const attendance = cell.querySelector('[data-joint-attendance]');
        const score = cell.querySelector('[data-joint-score]');
        if (!attendance || !score) return;
        const sync = () => { score.disabled = attendance.value === 'absent'; };
        attendance.addEventListener('change', sync);
        score.addEventListener('input', () => {
            if (score.value !== '' && attendance.value !== 'present') {
                attendance.value = 'present';
                attendance.dispatchEvent(new Event('change', {bubbles: true}));
            }
        });
        sync();
    });
})();
