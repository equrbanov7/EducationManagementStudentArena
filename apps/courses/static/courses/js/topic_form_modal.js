/*
 * topic_form_modal.js
 * Source: apps/courses/templates/courses/partials/_topic_form_modal.html
 * Add-topic modal AJAX submit. i18n read from #topicFormModalConfig data-*.
 */
(function () {
    "use strict";

    var bound = false;

    function init() {
        var cfg = document.getElementById("topicFormModalConfig");
        var form = document.getElementById("topicForm");
        if (!cfg || !form || bound) { return; }
        bound = true;
        var d = cfg.dataset;

        function showFormErrors(containerId, errors) {
            var container = document.getElementById(containerId);
            var errorHtml = "<strong>" + d.i18nErrorsHeader + ":</strong><ul class=\"mb-0\">";
            for (var field in errors) {
                if (Object.prototype.hasOwnProperty.call(errors, field)) {
                    errorHtml += "<li>" + errors[field][0] + "</li>";
                }
            }
            errorHtml += "</ul>";
            container.innerHTML = errorHtml;
            container.classList.remove("d-none");
        }

        function showNotification(message, type) {
            notify(message, type || "info");
        }

        form.addEventListener("submit", function (e) {
            e.preventDefault();

            var formData = new FormData(this);
            var actionUrl = this.action;

            var submitBtn = this.querySelector('button[type="submit"]');
            var originalText = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ' + d.i18nAdding;

            fetch(actionUrl, {
                method: "POST",
                body: formData,
                headers: { "X-Requested-With": "XMLHttpRequest" }
            })
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    if (data.success) {
                        bootstrap.Modal.getInstance(document.getElementById("topicFormModal")).hide();
                        document.getElementById("topicForm").reset();
                        showNotification(data.message, "success");
                        setTimeout(function () { location.reload(); }, 1000);
                    } else {
                        showFormErrors("topicErrors", data.errors);
                    }
                })
                .catch(function (error) {
                    console.error("Error:", error);
                    showNotification(d.i18nErrorRetry, "error");
                })
                .finally(function () {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalText;
                });
        });
    }

    if (window.EMSReady) { window.EMSReady(init); }
    else { document.addEventListener("DOMContentLoaded", init); }
})();
