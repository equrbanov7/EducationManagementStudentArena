/* My lab answers page interactions */
(function () {
    'use strict';

    function formatDuration(totalSeconds) {
        const d = Math.floor(totalSeconds / 86400);
        const h = Math.floor((totalSeconds % 86400) / 3600);
        const m = Math.floor((totalSeconds % 3600) / 60);
        const s = totalSeconds % 60;
        if (d > 0) {
            return (
                String(d).padStart(2, '0') +
                ':' +
                String(h).padStart(2, '0') +
                ':' +
                String(m).padStart(2, '0') +
                ':' +
                String(s).padStart(2, '0')
            );
        }
        return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    }

    const countdownEl = document.getElementById('reviewCountdown');
    if (countdownEl) {
        let remain = parseInt(countdownEl.dataset.seconds || '0', 10);
        const tick = () => {
            if (remain <= 0) {
                countdownEl.textContent = '00:00:00';
                window.location.reload();
                return;
            }
            countdownEl.textContent = formatDuration(remain);
            remain -= 1;
        };
        tick();
        setInterval(tick, 1000);
    }

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
})();
