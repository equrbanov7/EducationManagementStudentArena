/*
 * topic_accordion.js
 * Source: apps/courses/templates/courses/partials/_topic_accordion.html
 * Topic/resource row actions: stop-propagation guards, delete topic/resource
 * (generated POST form), open resource modal with topic context.
 * Config (i18n confirm strings) is read from #topicAccordionConfig data-*.
 */
(function () {
    "use strict";

    function getCfg() {
        return document.getElementById("topicAccordionConfig");
    }

    function csrfInputClone() {
        var token = document.querySelector("[name=csrfmiddlewaretoken]");
        return token ? token.cloneNode(true) : null;
    }

    function deleteTopic(courseId, topicId) {
        var cfg = getCfg();
        if (!cfg || !confirm(cfg.dataset.i18nConfirmDeleteTopic)) { return; }
        var form = document.createElement("form");
        form.method = "POST";
        form.action = "/courses/" + courseId + "/topic/" + topicId + "/delete/";
        var c = csrfInputClone();
        if (c) { form.appendChild(c); }
        document.body.appendChild(form);
        form.submit();
    }

    function deleteResource(courseId, resourceId) {
        var cfg = getCfg();
        if (!cfg || !confirm(cfg.dataset.i18nConfirmDeleteResource)) { return; }
        var form = document.createElement("form");
        form.method = "POST";
        form.action = "/courses/" + courseId + "/resource/" + resourceId + "/delete/";
        var c = csrfInputClone();
        if (c) { form.appendChild(c); }
        document.body.appendChild(form);
        form.submit();
    }

    function openResourceModal(topicId, topicTitle) {
        var modalEl = document.getElementById("resourceFormModal");
        if (!modalEl) {
            var cfg = getCfg();
            console.error(cfg ? cfg.dataset.i18nResourceModalNotFound : "resourceFormModal");
            return;
        }

        var applyTopicContext = function () {
            var topicSelect = document.getElementById("resourceTopic");
            if (topicSelect) {
                topicSelect.value = topicId;
                if (window.EMSBootstrapSelect) {
                    window.EMSBootstrapSelect.sync(topicSelect);
                }
            }
            var topicName = document.getElementById("resourceModalTopicName");
            if (topicName) { topicName.textContent = " - " + topicTitle; }
        };

        modalEl.addEventListener("shown.bs.modal", applyTopicContext, { once: true });
        bootstrap.Modal.getOrCreateInstance(modalEl).show();

        if (modalEl.classList.contains("show")) {
            applyTopicContext();
        }
    }

    window.EMSReady.once("topic-accordion-doc-click", function () {
        document.addEventListener("click", function (event) {
            var editTopicButton = event.target.closest("[data-edit-topic-id]");
            if (editTopicButton) {
                event.preventDefault();
                event.stopPropagation();
                if (typeof window.editTopic === "function") {
                    window.editTopic(
                        editTopicButton.dataset.editTopicId,
                        editTopicButton.dataset.editTopicTitle || "",
                        editTopicButton.dataset.editTopicDescription || ""
                    );
                }
                return;
            }

            var deleteTopicButton = event.target.closest("[data-delete-topic-course-id][data-delete-topic-id]");
            if (deleteTopicButton) {
                event.preventDefault();
                event.stopPropagation();
                deleteTopic(deleteTopicButton.dataset.deleteTopicCourseId, deleteTopicButton.dataset.deleteTopicId);
                return;
            }

            var deleteResourceButton = event.target.closest("[data-delete-resource-course-id][data-delete-resource-id]");
            if (deleteResourceButton) {
                event.preventDefault();
                event.stopPropagation();
                deleteResource(
                    deleteResourceButton.dataset.deleteResourceCourseId,
                    deleteResourceButton.dataset.deleteResourceId
                );
                return;
            }

            var openResourceButton = event.target.closest("[data-open-resource-modal-topic-id]");
            if (openResourceButton) {
                event.preventDefault();
                event.stopPropagation();
                openResourceModal(
                    openResourceButton.dataset.openResourceModalTopicId,
                    openResourceButton.dataset.openResourceModalTitle || ""
                );
            }
        }, true);
    });

    window.EMSReady(function () {
        var stops = document.querySelectorAll("[data-stop-propagation]");
        stops.forEach(function (element) {
            if (element.dataset.spBound === "1") { return; }
            element.dataset.spBound = "1";
            element.addEventListener("click", function (event) {
                event.stopPropagation();
            });
        });
    });
})();
