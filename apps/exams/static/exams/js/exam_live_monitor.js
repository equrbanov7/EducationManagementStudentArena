/* Backward-compatible loader for the split live monitor scripts. */
(function (window, document) {
  "use strict";

  var ns = window.EMSExamLiveMonitor;
  if (ns && ns.polling && typeof ns.polling.install === "function") {
    return;
  }

  var currentScript = document.currentScript;
  var currentSrc = currentScript && currentScript.src ? currentScript.src : "";
  var queryIndex = currentSrc.indexOf("?");
  var queryString = queryIndex !== -1 ? currentSrc.slice(queryIndex) : "";
  var baseUrl = currentSrc
    ? currentSrc.replace(/exam_live_monitor\.js(?:\?.*)?$/, "exam_live_monitor/")
    : "/static/exams/js/exam_live_monitor/";
  var files = [
    "namespace.js",
    "utils.js",
    "render.js",
    "snapshot_modal.js",
    "actions.js",
    "polling.js",
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
