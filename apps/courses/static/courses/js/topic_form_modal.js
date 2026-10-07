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

        // Audit 2026-10-07: xəta mətni (Django choice/validator xətaları istifadəçi
        // girişini əks etdirə bilər) innerHTML ilə YOX, textContent ilə yazılır.
        function showFormErrors(containerId, errors) {
            var container = document.getElementById(containerId);
            if (!container) { return; }
            container.textContent = "";
            var header = document.createElement("strong");
            header.textContent = (d.i18nErrorsHeader || "") + ":";
            var list = document.createElement("ul");
            list.className = "mb-0";
            Object.keys(errors || {}).forEach(function (field) {
                var messages = errors[field];
                var item = document.createElement("li");
                item.textContent = String((Array.isArray(messages) ? messages[0] : messages) || "");
                list.appendChild(item);
            });
            container.appendChild(header);
            container.appendChild(list);
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
            var spinner = document.createElement("i");
            spinner.className = "fas fa-spinner fa-spin";
            submitBtn.textContent = "";
            submitBtn.appendChild(spinner);
            submitBtn.appendChild(document.createTextNode(" " + (d.i18nAdding || "")));

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
