/*
 * resource_accordion.js
 * Source: apps/courses/templates/courses/partials/_resource_accordion.html
 * Global deleteResource() helper (generated POST form). Confirm string read
 * from #resourceAccordionConfig data-*. (Delete clicks on the dashboard are
 * handled by topic_accordion.js's document delegation; this keeps the legacy
 * global helper available, as before.)
 *
 * 2026-10-19: kurs videoları (`<video data-resource-video>`). Brauzer faylı oynada bilməyəndə
 * (məs. iPhone HEVC .MOV Chrome/Android-də) `error` hadisəsi qabarmır — document-də capture ilə
 * tutulur və videonun yanındakı «Yüklə» izahı (`[data-resource-video-error]`) göstərilir.
 */
(function () {
    "use strict";

    function getCfg() {
        return document.getElementById("resourceAccordionConfig");
    }

    function revealVideoError(event) {
        var target = event.target;
        if (!target || !target.closest) { return; }
        var video = target.matches && target.matches("[data-resource-video]") ? target : target.closest("[data-resource-video]");
        if (!video) { return; }
        var box = video.closest("[data-resource-video-box]");
        var note = box && box.querySelector("[data-resource-video-error]");
        if (note) { note.hidden = false; }
        if (box) { box.classList.add("is-unplayable"); }
    }

    if (!window.__emsResourceVideoErrorBound) {
        window.__emsResourceVideoErrorBound = true;
        document.addEventListener("error", revealVideoError, true);
    }

    window.deleteResource = function (courseId, resourceId) {
        var cfg = getCfg();
        if (!cfg) { return; }
        // 2026-09-14 (audit FE-F19): native confirm() → EMSConfirm (vahid dialoq); ləğv = sorğu yoxdur.
        window.EMSConfirm.open({ body: cfg.dataset.i18nConfirmDeleteResource, danger: true }).then(function (ok) {
            if (!ok) { return; }
            var form = document.createElement("form");
            form.method = "POST";
            form.action = "/courses/" + courseId + "/resource/" + resourceId + "/delete/";

            var csrfToken = document.querySelector("[name=csrfmiddlewaretoken]");
            if (csrfToken) {
                form.appendChild(csrfToken.cloneNode(true));
            }

            document.body.appendChild(form);
            form.submit();
        });
    };
})();
