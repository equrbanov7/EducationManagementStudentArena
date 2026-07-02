(function (window, document) {
  "use strict";

  var ns = window.EMSExamLiveMonitor || (window.EMSExamLiveMonitor = {});
  var wrap = document.querySelector(".live-wrap");

  if (!wrap || wrap.getAttribute("data-live-monitor-ready") === "1") {
    return;
  }
  wrap.setAttribute("data-live-monitor-ready", "1");

  var ctx = ns.utils.createContext(wrap);
  ns.snapshot.install(ctx);
  ns.actions.install(ctx);
  ns.polling.install(ctx);
})(window, document);
