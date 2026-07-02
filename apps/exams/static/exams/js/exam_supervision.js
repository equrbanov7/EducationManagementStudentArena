/**
 * Compatibility loader for the split Exam Supervision modules.
 * New templates load exam_supervision/exam_supervision.entry.js directly.
 */
(function (window) {
    "use strict";

    import("./exam_supervision/exam_supervision.entry.js?v=20260611-fresh-csrf").then(function (module) {
        window.ExamSupervision = module.default || module.ExamSupervision;
    });
})(window);
