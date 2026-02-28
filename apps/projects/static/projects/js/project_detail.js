document.addEventListener('DOMContentLoaded', function() {
    const config = window.projectDetailConfig || {};
    const i18n = config.i18n || {};

    const fileInput = document.getElementById('fileInput');
    const fileNameDisplay = document.getElementById('fileNameDisplay');
    const fileName = document.getElementById('fileName');
    const clearFile = document.getElementById('clearFile');

    if (fileInput) {
        fileInput.addEventListener('change', function() {
            if (this.files && this.files[0]) {
                fileName.textContent = this.files[0].name;
                fileNameDisplay.style.display = 'block';
            } else {
                fileNameDisplay.style.display = 'none';
            }
        });
    }

    if (clearFile) {
        clearFile.addEventListener('click', function() {
            fileInput.value = '';
            fileNameDisplay.style.display = 'none';
        });
    }

    const form = document.getElementById('submitForm');
    if (!form) {
        return;
    }

    form.addEventListener('submit', function(e) {
        e.preventDefault();

        const btn = form.querySelector('[type=submit]');
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> ${i18n.sending || 'Sending...'}`;

        const formData = new FormData(form);

        fetch(config.submitUrl, {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': config.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    window.location.reload();
                    return;
                }

                alert(`${i18n.errorPrefix || 'Error: '}${data.error || i18n.unknownError || 'Unknown error'}`);
                btn.disabled = false;
                btn.innerHTML = `<i class="fa-solid fa-paper-plane me-1"></i> ${i18n.submit || 'Submit'}`;
            })
            .catch(() => {
                alert(i18n.serverError || 'Server error');
                btn.disabled = false;
                btn.innerHTML = `<i class="fa-solid fa-paper-plane me-1"></i> ${i18n.submit || 'Submit'}`;
            });
    });
});
