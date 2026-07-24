/*
 * grading_queue_actions.js
 * Source: extracted verbatim from the inline <script> in
 * _grading_queue_js.html (CSP inline-removal, 2026-07).
 *
 * submitGrade() stays a GLOBAL (window.submitGrade): the shared
 * static/js/csp_event_handlers.js invokes it via callGlobal() for
 * [data-submit-grade-id] form submits and [data-submit-grade-next] clicks.
 * i18n strings are bridged via data-* on #gradeQueueI18n.
 */
(function () {
    "use strict";

    function cfg(key, fallback) {
        var el = document.getElementById("gradeQueueI18n");
        return el ? (el.getAttribute(key) || fallback) : (fallback || "");
    }

    function submitGrade(event, submissionId, goToNext) {
        event.preventDefault();

        var form = event.target.closest('form');
        var formData = new FormData(form);
        var row = form.closest('tr');
        var gradeUrl = form.getAttribute('action');

        // Show loading
        document.getElementById('loadingSpinner').classList.add('active');

        // AJAX submission
        fetch(gradeUrl, {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value,
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(function (response) { return response.json(); })
        .then(function (data) {
            document.getElementById('loadingSpinner').classList.remove('active');

            if (data.success) {
                // Remove the row
                row.style.transition = 'opacity 0.3s';
                row.style.opacity = '0';
                setTimeout(function () { row.remove(); }, 300);

                // Update stats
                updateStats();

                // Show success message
                showMessage('success', cfg('data-success'));

                if (goToNext) {
                    // Scroll to next submission
                    var nextRow = row.nextElementSibling;
                    if (nextRow) {
                        nextRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        nextRow.querySelector('.grade-input').focus();
                    }
                }
            } else {
                showMessage('error', data.error || cfg('data-error-generic'));
            }
        })
        .catch(function (error) {
            document.getElementById('loadingSpinner').classList.remove('active');
            showMessage('error', cfg('data-error-prefix') + ': ' + error.message);
        });
    }

    function updateStats() {
        // Reload page to update stats
        // In production, this should be an AJAX call
        setTimeout(function () { location.reload(); }, 1000);
    }

    function showMessage(type, message) {
        // Create toast notification
        var toast = document.createElement('div');
        toast.className = 'alert alert-' + (type === 'success' ? 'success' : 'danger') + ' alert-dismissible fade show';

        var icon = document.createElement('i');
        icon.className = 'fas fa-' + (type === 'success' ? 'check-circle' : 'exclamation-circle') + ' me-2';

        var messageNode = document.createTextNode(message);

        var closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'btn-close';
        closeBtn.setAttribute('data-bs-dismiss', 'alert');

        toast.appendChild(icon);
        toast.appendChild(messageNode);
        toast.appendChild(closeBtn);

        var container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }

        container.appendChild(toast);

        setTimeout(function () {
            toast.classList.add('fade-out');
            setTimeout(function () { toast.remove(); }, 300);
        }, 3000);
    }

    function viewSubmission(button) {
        var submissionId = button.dataset.submissionId;
        var contentTemplate = document.getElementById('submission-content-' + submissionId);
        var content = contentTemplate ? contentTemplate.textContent.trim() : '';

        document.getElementById('submissionPreviewTitle').textContent = button.dataset.assignment || '';
        document.getElementById('submissionPreviewStudent').textContent = button.dataset.student || '';
        document.getElementById('submissionPreviewContent').textContent = content;

        if (window.bootstrap && window.bootstrap.Modal) {
            var modal = window.bootstrap.Modal.getOrCreateInstance(document.getElementById('submissionPreviewModal'));
            modal.show();
        }
    }

    // submitGrade is called from static/js/csp_event_handlers.js via callGlobal().
    window.submitGrade = submitGrade;

    window.EMSReady(function () {
        document.querySelectorAll('.js-view-submission').forEach(function (button) {
            if (button.dataset.gqBound === "1") { return; }
            button.dataset.gqBound = "1";
            button.addEventListener('click', function (event) {
                event.preventDefault();
                viewSubmission(this);
            });
        });

        // Auto-submit on course selection change
        var courseSelect = document.getElementById('course');
        if (courseSelect && courseSelect.dataset.gqBound !== "1") {
            courseSelect.dataset.gqBound = "1";
            courseSelect.addEventListener('change', function () {
                // Load assignments for selected course via AJAX
                // For now, just submit the form
                // document.getElementById('filterForm').submit();
            });
        }
    });
})();
