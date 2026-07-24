/*
 * detail.js
 * Source: apps/assignments/templates/assignments/detail.html (legacy detail page)
 * AJAX submit of the draft-answer form. i18n from data-* on #submitForm;
 * submit URL is the form's own action; CSRF from EMSCore.
 */
(function () {
    "use strict";

    window.EMSReady(function () {
        var submitForm = document.getElementById("submitForm");
        if (!submitForm || submitForm.dataset.dBound === "1") { return; }
        submitForm.dataset.dBound = "1";

        var d = submitForm.dataset;
        var submitBtn = submitForm.querySelector('button[type="submit"]');

        submitForm.addEventListener("submit", function (e) {
            e.preventDefault();

            var originalBtnText = submitBtn.innerHTML;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> ' + d.i18nSubmitting;
            submitBtn.disabled = true;

            var formData = new FormData(this);

            fetch(submitForm.action, {
                method: "POST",
                body: formData,
                headers: { "X-CSRFToken": EMSCore.getCsrfToken() }
            })
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    if (data.success) {
                        location.reload();
                    } else {
                        alert(d.i18nErrorPrefix + ": " + JSON.stringify(data.errors));
                        submitBtn.innerHTML = originalBtnText;
                        submitBtn.disabled = false;
                    }
                })
                .catch(function () {
                    alert(d.i18nGenericError);
                    submitBtn.innerHTML = originalBtnText;
                    submitBtn.disabled = false;
                });
        });
    });
})();
