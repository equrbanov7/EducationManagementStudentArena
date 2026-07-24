/*
 * teacher_exam_results.js
 * Source: exams/teacher/teacher_exam_results.html
 *
 * Results page glue: per-row countdown timers, optional bulk-delete wiring
 * (initResultsBulkActions from the shared results_bulk_actions.js), and a
 * loading overlay on sort/pagination/filter navigation. The can-delete flag is
 * bridged via the #ter-results-config JSON island.
 */
(function () {
    "use strict";

    function readIsland(id) {
        var el = document.getElementById(id);
        if (!el) { return {}; }
        try { return JSON.parse(el.textContent) || {}; }
        catch (err) { return {}; }
    }

    document.addEventListener('DOMContentLoaded', function() {
        var CFG = readIsland("ter-results-config");

        const rows = document.querySelectorAll('tr[data-seconds-remaining]');

        rows.forEach(row => {
            let secondsLeft = parseInt(row.dataset.secondsRemaining, 10) || 0;
            if (secondsLeft <= 0) return;
            const timerDisplay = row.querySelector('.timer-display');
            if (!timerDisplay) return;

            const updateTimer = () => {
                if (secondsLeft <= 0) {
                    window.location.reload();
                    return;
                }
                const minutes = Math.floor(secondsLeft / 60);
                const seconds = secondsLeft % 60;
                timerDisplay.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
                secondsLeft--;
            };

            updateTimer();
            const interval = setInterval(updateTimer, 1000);
            window.addEventListener('beforeunload', () => clearInterval(interval));
        });

        if (CFG.canDeleteAttempts && window.initResultsBulkActions) {
            window.initResultsBulkActions({
                checkboxSelector: '.js-attempt-checkbox',
                selectedCountSelector: '#selectedAttemptCount',
                selectAllSelector: '#selectAllAttemptsBtn',
                clearSelector: '#clearAttemptsBtn',
                deleteSelectedSelector: '#deleteSelectedAttemptsBtn',
                singleDeleteSelector: '.js-single-delete-attempt',
                deleteFormSelector: '#deleteAttemptsForm',
                deleteInputsSelector: '#deleteAttemptsInputs',
                confirmButtonSelector: '#confirmDeleteAttemptsBtn',
                confirmModalSelector: '#deleteAttemptsConfirmModal',
                inputName: 'attempt_ids',
                singleDeleteDataAttribute: 'attemptId'
            });
        }

        var loadingOverlay = document.getElementById("loadingOverlay");
        function showLoading() { if (loadingOverlay) loadingOverlay.classList.add("show"); }
        document.querySelectorAll(".ter-sort-link, .pagination-wrapper a").forEach(function(el) {
            el.addEventListener("click", showLoading);
        });
        var filtersForm = document.getElementById("resultsFiltersForm");
        if (filtersForm) {
            filtersForm.addEventListener("submit", showLoading);
        }
    });
})();
