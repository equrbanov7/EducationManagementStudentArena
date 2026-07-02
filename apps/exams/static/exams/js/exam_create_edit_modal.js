/* Backward-compatible loader for the split exam create/edit modal scripts. */
(function (window, document) {
    "use strict";

    var ns = window.EMSExamCreateEditModal;
    if (ns && ns.form && typeof ns.form.openExamModal === "function") {
        return;
    }

    var currentScript = document.currentScript;
    var currentSrc = currentScript && currentScript.src ? currentScript.src : "";
    var queryIndex = currentSrc.indexOf("?");
    var queryString = queryIndex !== -1 ? currentSrc.slice(queryIndex) : "";
    var baseUrl = currentSrc
        ? currentSrc.replace(/exam_create_edit_modal\.js(?:\?.*)?$/, "exam_create_edit_modal/")
        : "/static/exams/js/exam_create_edit_modal/";
    var files = [
        "namespace.js",
        "markup.js",
        "searchable_select.js",
        "toggles.js",
        "form.js",
        "entry.js"
    ];

    function loadNext(index) {
        if (index >= files.length) {
            return;
        }
        var script = document.createElement("script");
        script.src = baseUrl + files[index] + queryString;
        script.async = false;
        script.onload = function () {
            loadNext(index + 1);
        };
        document.head.appendChild(script);
    }

    loadNext(0);
})(window, document);
