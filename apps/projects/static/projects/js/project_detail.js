/*
 * project_detail.js
 * Source: apps/projects/templates/projects/project_detail.html
 * Course-work submit flow: file preview, confirm modal, AJAX submit.
 * Config (submit URL + i18n) is read from data-* on #submitForm; CSRF from EMSCore.
 */
(function () {
    "use strict";

    window.EMSReady(function () {
        var form = document.getElementById("submitForm");
        var fileInput = document.getElementById("fileInput");
        var fileNameDisplay = document.getElementById("fileNameDisplay");
        var fileName = document.getElementById("fileName");
        var clearFile = document.getElementById("clearFile");

        if (fileInput && fileInput.dataset.pdBound !== "1") {
            fileInput.dataset.pdBound = "1";
            fileInput.addEventListener("change", function () {
                if (this.files && this.files[0]) {
                    if (fileName) { fileName.textContent = this.files[0].name; }
                    if (fileNameDisplay) { fileNameDisplay.classList.remove("d-none"); }
                } else if (fileNameDisplay) {
                    fileNameDisplay.classList.add("d-none");
                }
            });
        }

        if (clearFile && clearFile.dataset.pdBound !== "1") {
            clearFile.dataset.pdBound = "1";
            clearFile.addEventListener("click", function () {
                if (fileInput) { fileInput.value = ""; }
                if (fileNameDisplay) { fileNameDisplay.classList.add("d-none"); }
            });
        }

        if (!form || form.dataset.pdBound === "1") { return; }
        form.dataset.pdBound = "1";

        var d = form.dataset;
        var i18n = {
            sending: d.i18nSending,
            submit: d.i18nSubmit,
            errorPrefix: d.i18nErrorPrefix,
            unknownError: d.i18nUnknownError,
            serverError: d.i18nServerError,
            confirmTitle: d.i18nConfirmTitle,
            confirmMessage: d.i18nConfirmMessage,
            confirmSubmit: d.i18nConfirmSubmit
        };
        var submitUrl = d.submitUrl;

        var submitConfirmed = false;
        form.addEventListener("submit", function (e) {
            if (!submitConfirmed && typeof window.openActionConfirmModal === "function") {
                e.preventDefault();
                window.openActionConfirmModal({
                    title: i18n.confirmTitle,
                    message: i18n.confirmMessage,
                    confirmLabel: i18n.confirmSubmit || i18n.submit,
                    confirmButtonClass: "btn btn-success",
                    onConfirm: function () {
                        submitConfirmed = true;
                        window.setTimeout(function () {
                            form.requestSubmit();
                        }, 0);
                        return true;
                    }
                });
                return;
            }

            e.preventDefault();

            var btn = form.querySelector("[type=submit]");
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> ' + (i18n.sending || "Sending...");

            var formData = new FormData(form);

            fetch(submitUrl, {
                method: "POST",
                body: formData,
                headers: {
                    "X-CSRFToken": EMSCore.getCsrfToken(),
                    "X-Requested-With": "XMLHttpRequest"
                }
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) {
                        window.location.reload();
                        return;
                    }
                    submitConfirmed = false;
                    alert((i18n.errorPrefix || "Error: ") + (data.error || i18n.unknownError || "Unknown error"));
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fa-solid fa-paper-plane me-1"></i> ' + (i18n.submit || "Submit");
                })
                .catch(function () {
                    submitConfirmed = false;
                    alert(i18n.serverError || "Server error");
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fa-solid fa-paper-plane me-1"></i> ' + (i18n.submit || "Submit");
                });
        });
    });
})();
