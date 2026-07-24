/*
 * resource_form_modal.js
 * Source: apps/courses/templates/courses/partials/_resource_form_modal.html
 * Add-resource modal: file/url section toggle by type, AJAX submit, reset on
 * close. Uses global notify()/showFormErrors(); i18n from
 * #resourceFormModalConfig data-*.
 */
(function () {
    "use strict";

    var bound = false;

    function init() {
        var cfg = document.getElementById("resourceFormModalConfig");
        var form = document.getElementById("resourceForm");
        var modalEl = document.getElementById("resourceFormModal");
        if (!cfg || !form || !modalEl || bound) { return; }
        bound = true;
        var d = cfg.dataset;

        function applyTypeToggle(radio) {
            var fileSection = document.getElementById("fileUploadSection");
            var urlSection = document.getElementById("urlInputSection");
            var fileInput = document.getElementById("resourceFile");
            var urlInput = document.getElementById("resourceUrl");

            if (radio.value === "file" || radio.value === "document" || radio.value === "video") {
                fileSection.classList.remove("d-none");
                urlSection.classList.add("d-none");
                fileInput.required = true;
                urlInput.required = false;
            } else {
                fileSection.classList.add("d-none");
                urlSection.classList.remove("d-none");
                fileInput.required = false;
                urlInput.required = true;
            }
        }

        var radios = document.querySelectorAll('input[name="resource_type"]');
        radios.forEach(function (radio) {
            radio.addEventListener("change", function () {
                applyTypeToggle(this);
            });
        });

        form.addEventListener("submit", function (e) {
            e.preventDefault();

            var formData = new FormData(this);
            var actionUrl = this.action;

            var submitBtn = this.querySelector('button[type="submit"]');
            var originalText = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ' + d.i18nLoading;

            fetch(actionUrl, {
                method: "POST",
                body: formData,
                headers: { "X-Requested-With": "XMLHttpRequest" }
            })
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    if (data.success) {
                        bootstrap.Modal.getInstance(document.getElementById("resourceFormModal")).hide();
                        document.getElementById("resourceForm").reset();
                        if (window.EMSBootstrapSelect) {
                            window.EMSBootstrapSelect.sync(document.getElementById("resourceTopic"));
                        }
                        document.getElementById("resourceModalTopicName").textContent = "";
                        notify(data.message, "success");
                        setTimeout(function () { location.reload(); }, 1000);
                    } else {
                        showFormErrors("resourceErrors", data.errors);
                    }
                })
                .catch(function (error) {
                    console.error("Error:", error);
                    notify(d.i18nErrorRetry, "error");
                })
                .finally(function () {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalText;
                });
        });

        modalEl.addEventListener("hidden.bs.modal", function () {
            document.getElementById("resourceForm").reset();
            if (window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(document.getElementById("resourceTopic"));
            }
            document.getElementById("resourceModalTopicName").textContent = "";
            document.getElementById("resourceErrors").classList.add("d-none");
        });
    }

    if (window.EMSReady) { window.EMSReady(init); }
    else { document.addEventListener("DOMContentLoaded", init); }
})();
