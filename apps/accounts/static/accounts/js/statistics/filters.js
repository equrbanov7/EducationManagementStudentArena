(function (window, document) {
  "use strict";

  var ns = window.EMSStatistics || (window.EMSStatistics = {});

  function init() {
    var statsFilterForm = document.getElementById("statsFilterForm");
    if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.init === "function" && statsFilterForm) {
      window.EMSBootstrapSelect.init(statsFilterForm);
    }

    if (statsFilterForm && statsFilterForm.getAttribute("data-stats-auto-submit") === "true") {
      statsFilterForm.addEventListener("change", function (event) {
        var target = event.target;
        if (!target || target.name === "section") {
          return;
        }

        if (typeof statsFilterForm.requestSubmit === "function") {
          statsFilterForm.requestSubmit();
          return;
        }
        statsFilterForm.submit();
      });
    }
  }

  ns.filters = {
    init: init
  };
})(window, document);
