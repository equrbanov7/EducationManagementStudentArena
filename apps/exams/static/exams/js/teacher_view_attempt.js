/* Source: exams/teacher/teacher_view_attempt.html
   Anonymous-identity review countdown ([data-review-countdown]).
   Extracted from an inline <script> for CSP (no unsafe-inline). */
(function () {
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
})();
