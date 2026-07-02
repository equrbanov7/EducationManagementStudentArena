/* Backward-compatible loader for the split permission editor scripts. */
(function (window, document) {
    "use strict";

    var ns = window.EMSPermissionEditor;
    if (ns && typeof ns.initAll === "function") {
        ns.initAll(document);
        return;
    }

    var currentScript = document.currentScript;
    var currentSrc = currentScript && currentScript.src ? currentScript.src : "";
    var queryIndex = currentSrc.indexOf("?");
    var queryString = queryIndex !== -1 ? currentSrc.slice(queryIndex) : "";
    var baseUrl = currentSrc
        ? currentSrc.replace(/permission_editor_ui\.js(?:\?.*)?$/, "permission_editor/")
        : "/static/accounts/js/permission_editor/";
    var files = [
        "namespace.js",
        "labels.js",
        "matrix.js",
        "interactions.js",
        "save_state.js",
        "permission_editor.entry.js"
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
