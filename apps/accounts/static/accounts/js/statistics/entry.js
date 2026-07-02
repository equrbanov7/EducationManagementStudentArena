/**
 * Statistics section — charts, AI summary, filter UX, table search/sort.
 */
(function (window, document) {
  "use strict";

  var ns = window.EMSStatistics || (window.EMSStatistics = {});

  ns.init = function () {
    ns.filters.init();
    var ctx = ns.utils.createContext();
    if (!ctx) {
      return;
    }
    ns.charts.init(ctx);
    ns.tables.init();
    ns.aiSummary.init(ctx);
  };

  document.addEventListener("DOMContentLoaded", ns.init);
})(window, document);
