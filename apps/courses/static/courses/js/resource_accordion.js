/*
 * resource_accordion.js
 * Source: apps/courses/templates/courses/partials/_resource_accordion.html
 * Global deleteResource() helper (generated POST form). Confirm string read
 * from #resourceAccordionConfig data-*. (Delete clicks on the dashboard are
 * handled by topic_accordion.js's document delegation; this keeps the legacy
 * global helper available, as before.)
 */
(function () {
    "use strict";

    function getCfg() {
        return document.getElementById("resourceAccordionConfig");
    }

    window.deleteResource = function (courseId, resourceId) {
        var cfg = getCfg();
        if (!cfg || !confirm(cfg.dataset.i18nConfirmDeleteResource)) { return; }

        var form = document.createElement("form");
        form.method = "POST";
        form.action = "/courses/" + courseId + "/resource/" + resourceId + "/delete/";

        var csrfToken = document.querySelector("[name=csrfmiddlewaretoken]");
        if (csrfToken) {
            form.appendChild(csrfToken.cloneNode(true));
        }

        document.body.appendChild(form);
        form.submit();
    };
})();
