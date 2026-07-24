/* Source: exams/teacher/teacher_pending_attempts.html
   Filter tabs + real-time countdown timers for pending attempts.
   Extracted from an inline <script> for CSP (no unsafe-inline). */
window.EMSReady(function () {
    const tabs = document.querySelectorAll('.filter-tab');
    const rows = document.querySelectorAll('#attemptsTableBody tr');

    // Tab filtering
    tabs.forEach(tab => {
        tab.addEventListener('click', function () {
            tabs.forEach(t => t.classList.remove('active'));
            this.classList.add('active');

            const filter = this.dataset.filter;

            rows.forEach(row => {
                if (filter === 'all') {
                    row.style.display = '';
                } else {
                    row.style.display = row.dataset.type === filter ? '' : 'none';
                }
            });
        });
    });

    // ✅ Real-time countdown timer
    rows.forEach(row => {
        let secondsLeft = parseInt(row.dataset.secondsRemaining) || 0;
        if (secondsLeft <= 0) return;

        const timerDisplay = row.querySelector('.timer-display');

        const updateTimer = () => {
            if (secondsLeft <= 0) {
                window.location.reload();  // Auto-refresh
                return;
            }

            const minutes = Math.floor(secondsLeft / 60);
            const seconds = secondsLeft % 60;
            timerDisplay.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;

            secondsLeft--;
        };

        updateTimer();
        setInterval(updateTimer, 1000);
    });
});
