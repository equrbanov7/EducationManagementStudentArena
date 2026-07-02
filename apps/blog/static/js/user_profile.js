/* Backward-compatible loader for the split user profile post-modal scripts. */
(function (window, document) {
  "use strict";

  var ns = window.EMSUserProfile;
  if (ns && typeof ns.init === "function") {
    ns.init();
    return;
  }

  var currentScript = document.currentScript;
  var currentSrc = currentScript && currentScript.src ? currentScript.src : "";
  var queryIndex = currentSrc.indexOf("?");
  var queryString = queryIndex !== -1 ? currentSrc.slice(queryIndex) : "";
  var baseUrl = currentSrc
    ? currentSrc.replace(/user_profile\.js(?:\?.*)?$/, "user_profile/")
    : "/static/js/user_profile/";
  var files = [
    "namespace.js",
    "context.js",
    "modal.js",
    "create.js",
    "edit.js",
    "delete.js",
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
