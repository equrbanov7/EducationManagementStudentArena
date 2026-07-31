document.addEventListener('DOMContentLoaded', function() {
    const config = window.projectReviewConfig || {};
    const i18n = config.i18n || {};

    function openSubmission(button) {
        if (!button) return;

        const submissionId = button.dataset.id;
        const student = button.dataset.student;
        const content = button.dataset.content;
        const file = button.dataset.file;
        const filename = button.dataset.filename;
        const grade = button.dataset.grade;
        const feedback = button.dataset.feedback;

        document.getElementById('submission-id').value = submissionId;
        document.getElementById('modal-student').textContent = student;
        document.getElementById('modal-content').textContent = content || i18n.noContent;
        document.getElementById('grade-input').value = grade;
        document.getElementById('feedback-input').value = feedback;

        if (file) {
            document.getElementById('modal-file-container').style.display = 'block';
            document.getElementById('modal-file-link').href = file;
            document.getElementById('modal-file-name').textContent = filename || i18n.download;
        } else {
            document.getElementById('modal-file-container').style.display = 'none';
        }
    }

    document.querySelectorAll('.view-submission-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            openSubmission(this);
        });
    });

    const selectedSubmissionId = config.selectedSubmissionId;
    if (selectedSubmissionId) {
        const targetButton = document.querySelector('.view-submission-btn[data-id="' + selectedSubmissionId + '"]');
        if (targetButton) {
            openSubmission(targetButton);
            if (window.bootstrap && window.bootstrap.Modal) {
                const modal = window.bootstrap.Modal.getOrCreateInstance(document.getElementById('submissionModal'));
                modal.show();
            } else {
                targetButton.click();
            }
        }
    }

    document.getElementById('gradeForm')?.addEventListener('submit', function(e) {
        e.preventDefault();

        const submissionId = document.getElementById('submission-id').value;
        const formData = new FormData(this);
        const btn = this.querySelector('[type=submit]');

        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> ${i18n.sending}`;

        const gradeUrl = (config.gradeUrlTemplate || '').replace('__ID__', submissionId);

        fetch(gradeUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': config.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: formData
        })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    location.reload();
                } else {
                    alert(`${i18n.errorPrefix}${data.error || i18n.unknownError}`);
                    btn.disabled = false;
                    btn.innerHTML = `<i class="fas fa-circle-check"></i> ${i18n.gradeButton}`;
                }
            })
            .catch(err => {
                console.error(err);
                alert(i18n.serverError);
                btn.disabled = false;
                btn.innerHTML = `<i class="fas fa-circle-check"></i> ${i18n.gradeButton}`;
            });
    });
});
