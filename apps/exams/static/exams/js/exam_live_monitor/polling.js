(function (window, document) {
  "use strict";

  var ns = window.EMSExamLiveMonitor || (window.EMSExamLiveMonitor = {});
  var u = ns.utils;

  function fetchData(ctx) {
    return fetch(ctx.POLL_URL + window.location.search, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json(); })
      .then(function (d) { ns.render.renderAll(ctx, d); })
      .catch(function () { /* keep last good state */ });
  }

  function startPolling(ctx) {
    ctx.polling = true;
    u.$("pollStatus").classList.remove("is-paused");
    u.$("pollStatusText").textContent = u.t(ctx, "poll_auto_refresh", gettext("Avtomatik yenilənir"));
    u.$("togglePollBtn").innerHTML = '<i class="fas fa-pause"></i> ' + u.t(ctx, "btn_pause_poll", gettext("Dayandır"));
    clearInterval(ctx.pollTimer);
    ctx.pollTimer = setInterval(ctx.fetchData, ctx.POLL_INTERVAL);
  }

  function stopPolling(ctx) {
    ctx.polling = false;
    u.$("pollStatus").classList.add("is-paused");
    u.$("pollStatusText").textContent = u.t(ctx, "poll_paused", gettext("Dayandırılıb"));
    u.$("togglePollBtn").innerHTML = '<i class="fas fa-play"></i> ' + u.t(ctx, "btn_continue_poll", "Davam et");
    clearInterval(ctx.pollTimer);
  }

  function installDateFilters() {
    var dateInput = u.$("dateInput");
    if (dateInput) {
      dateInput.addEventListener("change", function () {
        window.location.search = this.value ? "?date=" + this.value : "";
      });
    }
    var dateSelect = u.$("dateSelect");
    if (dateSelect) {
      dateSelect.addEventListener("change", function () {
        if (this.value) window.location.search = "?date=" + this.value;
      });
    }
  }

  function install(ctx) {
    ctx.fetchData = function () {
      return fetchData(ctx);
    };
    u.$("togglePollBtn").addEventListener("click", function () {
      ctx.polling ? stopPolling(ctx) : startPolling(ctx);
    });
    u.$("refreshNowBtn").addEventListener("click", ctx.fetchData);
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) {
        clearInterval(ctx.pollTimer);
      } else if (ctx.polling) {
        ctx.fetchData();
        startPolling(ctx);
      }
    });
    installDateFilters();
    if (ctx.state) {
      ns.render.renderAll(ctx, ctx.state);
    } else {
      ctx.fetchData();
    }
    startPolling(ctx);
  }

  ns.polling = {
    install: install,
    startPolling: startPolling,
    stopPolling: stopPolling
  };
})(window, document);
