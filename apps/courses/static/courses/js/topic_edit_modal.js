/*
 * topic_edit_modal.js
 * Source: apps/courses/templates/courses/partials/_topic_edit_modal.html
 * Edit-topic modal: window.editTopic opener, shown-event fill, AJAX submit.
 * i18n / debug strings read from #topicEditModalConfig data-*.
 */
(function () {
    "use strict";

    var bound = false;
    var pendingTopicData = null;

    function init() {
        var cfg = document.getElementById("topicEditModalConfig");
        if (!cfg || bound) { return; }
        var d = cfg.dataset;

        var modalEl = document.getElementById("topicEditModal");
        var form = document.getElementById("topicEditForm");

        if (!modalEl || !form) {
            console.error(d.logModalNotFound);
            return;
        }
        bound = true;

        function showFormErrors(containerId, errors) {
            var container = document.getElementById(containerId);
            if (!container) { return; }
            var errorHtml = "<strong>" + d.i18nErrorsHeader + ":</strong><ul class=\"mb-0\">";
            for (var field in errors) {
                if (Object.prototype.hasOwnProperty.call(errors, field)) {
                    var messages = errors[field];
                    var msg = (Array.isArray(messages) && messages[0]) ? messages[0] : d.i18nError;
                    errorHtml += "<li>" + msg + "</li>";
                }
            }
            errorHtml += "</ul>";
            container.innerHTML = errorHtml;
            container.classList.remove("d-none");
        }

        modalEl.addEventListener("shown.bs.modal", function () {
            if (pendingTopicData) {
                console.log(d.logModalOpened, pendingTopicData);

                document.getElementById("editTopicId").value = pendingTopicData.id || "";
                document.getElementById("editTopicTitle").value = pendingTopicData.title || "";
                document.getElementById("editTopicDescription").value = pendingTopicData.description || "";

                var errContainer = document.getElementById("topicEditErrors");
                if (errContainer) {
                    errContainer.classList.add("d-none");
                    errContainer.innerHTML = "";
                }

                setTimeout(function () {
                    document.getElementById("editTopicTitle").focus();
                }, 100);

                pendingTopicData = null;
            }
        });

        window.editTopic = function (topicId, title, description) {
            console.log(d.logEditTopicCalled, { topicId: topicId, title: title, description: description });

            pendingTopicData = {
                id: topicId,
                title: title,
                description: description
            };

            var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
        };

        form.addEventListener("submit", function (e) {
            e.preventDefault();

            var topicId = document.getElementById("editTopicId").value;

            if (!topicId) {
                alert(d.i18nTopicIdNotFound);
                return;
            }

            var formData = new FormData(this);
            var actionUrl = "/courses/topic/" + topicId + "/edit/";

            var submitBtn = this.querySelector('button[type="submit"]');
            var originalText = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ' + d.i18nUpdating;

            fetch(actionUrl, {
                method: "POST",
                body: formData,
                headers: { "X-Requested-With": "XMLHttpRequest" }
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) {
                        var modal = bootstrap.Modal.getInstance(modalEl);
                        if (modal) { modal.hide(); }

                        if (typeof notify === "function") {
                            notify(data.message || d.i18nTopicUpdated, "success");
                        }

                        setTimeout(function () { location.reload(); }, 1000);
                    } else {
                        showFormErrors("topicEditErrors", data.errors || {});
                    }
                })
                .catch(function (err) {
                    console.error(d.logError, err);
                    if (typeof notify === "function") {
                        notify(d.i18nErrorRetry, "error");
                    } else {
                        alert(d.i18nError);
                    }
                })
                .finally(function () {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalText;
                });
        });

        console.log("✓ Topic Edit Modal initialized");
    }

    if (window.EMSReady) { window.EMSReady(init); }
    else { document.addEventListener("DOMContentLoaded", init); }
})();
