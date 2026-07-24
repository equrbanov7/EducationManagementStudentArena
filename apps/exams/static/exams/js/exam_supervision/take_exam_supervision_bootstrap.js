/* take_exam_supervision_bootstrap.js
   Source: exams/student/take_exam.html (supervision-enabled branch).

   Bridges the dynamic supervision config/i18n that used to live in two inline
   <script nonce> blocks out of the template and into the DOM:
     - #supervision-ack-i18n   : <script type="application/json"> i18n map
     - #supervision-config-data: <script type="application/json"> supervision.config
     - #supervision-bootstrap  : root element carrying scalar/URL data-* attrs

   This runs as a CLASSIC (non-module) script so it executes at parse time,
   BEFORE the deferred `exam_supervision.entry.js` module reads these globals.
   It sets EXACTLY the same window globals the inline scripts set, so downstream
   supervision behavior is unchanged. */
(function () {
    "use strict";

    var i18nEl = document.getElementById("supervision-ack-i18n");
    if (i18nEl) {
        try {
            window.SUPERVISION_ACK_I18N = JSON.parse(i18nEl.textContent);
        } catch (e) {
            window.SUPERVISION_ACK_I18N = {};
        }
    }

    var root = document.getElementById("supervision-bootstrap");
    if (!root) {
        return;
    }

    // Where to send the student when a teacher stops / auto-finishes the attempt.
    window.SUPERVISION_RESULT_URL = root.dataset.resultUrl || "";

    var config = {};
    var cfgEl = document.getElementById("supervision-config-data");
    if (cfgEl) {
        try {
            config = JSON.parse(cfgEl.textContent);
        } catch (e) {
            config = {};
        }
    }

    var csrfToken = "";
    if (window.EMSCore && typeof EMSCore.getCsrfToken === "function") {
        csrfToken = EMSCore.getCsrfToken();
    }
    if (!csrfToken) {
        var csrfInput = document.querySelector(
            "#exam-form input[name=csrfmiddlewaretoken]"
        );
        if (csrfInput) {
            csrfToken = csrfInput.value;
        }
    }

    window.EXAM_SUPERVISION_INIT_CONFIG = {
        config: config,
        supervised: root.dataset.supervised === "1",
        attemptId: Number(root.dataset.attemptId),
        csrfToken: csrfToken,
        logEndpoint: root.dataset.logEndpoint,
        statusEndpoint: root.dataset.statusEndpoint,
        violationCount: Number(root.dataset.violationCount || "0"),
        maxViolations: Number(root.dataset.maxViolations || "3"),
        supervisionStatus: root.dataset.supervisionStatus || "active"
    };
})();
