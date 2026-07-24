// Source: exams/student/student_exam_history.html — debounced search + loading overlay on submit/pagination.

window.EMSReady(function () {
    var loadingOverlay = document.getElementById('loadingOverlay');
    var searchInput = document.getElementById('historySearchInput');
    var searchForm = document.getElementById('historySearchForm');
    var debounceTimer = null;

    function showLoading() {
        if (loadingOverlay) loadingOverlay.classList.add('show');
    }

    // Debounced search (500ms delay)
    if (searchInput && searchForm) {
        searchInput.addEventListener('input', function () {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(function () {
                showLoading();
                searchForm.submit();
            }, 500);
        });
    }

    // Show loading on pagination clicks
    document.querySelectorAll('.pagination-wrapper a').forEach(function (el) {
        el.addEventListener('click', showLoading);
    });
});
