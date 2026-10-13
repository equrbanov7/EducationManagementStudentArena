// Source: exams/student/student_exam_history.html — debounced search (EMSSearchInput) + loading overlay on pagination.

window.EMSReady(function () {
    var loadingOverlay = document.getElementById('loadingOverlay');
    var searchInput = document.getElementById('historySearchInput');
    var searchForm = document.getElementById('historySearchForm');
    function showLoading() {
        if (loadingOverlay) loadingOverlay.classList.add('show');
    }

    // 2026-10-14: vahid EMSSearchInput (1500 ms, ≥ 2 simvol, Enter dərhal, IME). Tam
    // ekranlı overlay yazdıqca axtarışda göstərilmir (yalnız input altında «Axtarılır…»);
    // yeni səhifədə fokus + kursor axtarış sahəsinə qayıdır.
    if (searchInput && searchForm && window.EMSSearchInput) {
        window.EMSSearchInput.bind(searchInput, {
            onSearch: function () {
                window.EMSSearchInput.busy(searchInput, true);
                window.EMSSearchInput.submitForm(searchForm, { input: searchInput });
            }
        });
    }

    // Show loading on pagination clicks
    document.querySelectorAll('.pagination-wrapper a').forEach(function (el) {
        el.addEventListener('click', showLoading);
    });
});
