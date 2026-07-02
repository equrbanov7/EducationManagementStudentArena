/* Backward-compatible loader for the split statistics scripts. */
(function (window, document) {
  "use strict";

  var ns = window.EMSStatistics;
  if (ns && typeof ns.init === "function") {
    ns.init();
    return;
  }

  var currentScript = document.currentScript;
  var currentSrc = currentScript && currentScript.src ? currentScript.src : "";
  var queryIndex = currentSrc.indexOf("?");
  var queryString = queryIndex !== -1 ? currentSrc.slice(queryIndex) : "";
  var baseUrl = currentSrc
    ? currentSrc.replace(/statistics\.js(?:\?.*)?$/, "statistics/")
    : "/static/accounts/js/statistics/";
  var files = [
    "namespace.js",
    "utils.js",
    "filters.js",
    "charts.js",
    "tables.js",
    "ai_summary.js",
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
