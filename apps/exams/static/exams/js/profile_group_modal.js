/* Backward-compatible loader for the split profile group modal scripts. */
(function (window, document) {
  "use strict";

  var ns = window.EMSProfileGroupModal;
  if (ns && typeof ns.init === "function") {
    ns.init(null);
    return;
  }

  var currentScript = document.currentScript;
  var currentSrc = currentScript && currentScript.src ? currentScript.src : "";
  var queryIndex = currentSrc.indexOf("?");
  var queryString = queryIndex !== -1 ? currentSrc.slice(queryIndex) : "";
  var baseUrl = currentSrc
    ? currentSrc.replace(/profile_group_modal\.js(?:\?.*)?$/, "profile_group_modal/")
    : "/static/exams/js/profile_group_modal/";
  var files = ["namespace.js", "checklist.js", "controller.js", "entry.js"];

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
