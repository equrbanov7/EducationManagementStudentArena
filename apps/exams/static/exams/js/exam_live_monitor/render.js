(function (window) {
  "use strict";

  var ns = window.EMSExamLiveMonitor || (window.EMSExamLiveMonitor = {});
  var u = ns.utils;

  var STATUS_CHART_LABELS = { active: "Aktiv", warned: gettext("Xəbərdarlıq"), locked: "Kilidli", removed: gettext("Çıxarılıb"), resumed: gettext("Bərpa olunub") };
  var STATUS_CHART_COLORS = { active: "#16a34a", warned: "#f59e0b", locked: "#ea580c", removed: "#7f1d1d", resumed: "#2563eb" };

  function renderStats(ctx, d) {
    var c = d.counts || {};
    var stats = [
      { cls: "accent-primary", label: u.t(ctx, "stat_entered", "Daxil olub"), value: c.entered || 0, sub: (d.students ? d.students.length : 0) + " " + u.t(ctx, "stat_students", gettext("tələbə")) },
      { cls: "accent-info", label: u.t(ctx, "stat_in_progress", "Davam edir"), value: c.in_progress || 0, sub: u.t(ctx, "stat_avg_progress", "Ortalama") + " " + (d.avg_progress || 0) + "%", bar: d.avg_progress || 0 },
      { cls: "accent-success", label: u.t(ctx, "stat_finished", gettext("Təslim edib")), value: c.finished || 0, sub: u.t(ctx, "stat_completed", gettext("Tamamlanmış sessiya")) },
      { cls: "accent-danger", label: u.t(ctx, "stat_flagged", "Problemli"), value: c.flagged || 0, sub: (d.total_violations || 0) + " " + u.t(ctx, "stat_violations", "pozuntu") }
    ];
    u.$("liveStats").innerHTML = stats.map(function (s) {
      return '<div class="lstat ' + s.cls + '">' +
        '<div class="lstat-label">' + u.esc(s.label) + '</div>' +
        '<div class="lstat-value">' + s.value + '</div>' +
        '<div class="lstat-meta">' + u.esc(s.sub) + '</div>' +
        (s.bar != null ? '<div class="lstat-bar"><span style="width:' + Math.min(100, s.bar) + '%"></span></div>' : '') +
        '</div>';
    }).join("");
  }

  function renderMap(ctx, d) {
    var map = u.$("studentMap");
    var students = d.students || [];
    if (!students.length) {
      map.innerHTML = "";
      u.$("mapEmpty").style.display = "block";
      u.$("mapFootMeta").textContent = "";
      return;
    }
    u.$("mapEmpty").style.display = "none";
    map.innerHTML = students.map(function (s, i) {
      var vio = s.violation_count > 0 ? '<span class="cell-vio">' + s.violation_count + '</span>' : "";
      var prog = s.state === "in_progress" ? '<span class="cell-prog">' + s.progress_pct + '%</span>' : "";
      var vioCls = (s.violation_level && s.violation_level !== "none") ? " vio-" + s.violation_level : "";
      return '<button type="button" class="smap-cell state-' + s.state + vioCls + '" data-attempt="' + s.attempt_id + '" data-idx="' + i + '">' +
        vio + '<span>' + ("0" + (i + 1)).slice(-2) + '</span>' + prog + '</button>';
    }).join("");
    u.$("mapFootMeta").textContent = students.length + gettext(" tələbə · ") + (ctx.POLL_INTERVAL / 1000) + gettext("sn-də bir yenilənir");
  }

  function renderNotEntered(ctx, d) {
    var list = (d.students || []).filter(function (s) { return s.state === "not_entered"; });
    u.$("notEnteredBadge").textContent = list.length;
    var el = u.$("notEnteredList");
    if (!list.length) {
      el.innerHTML = '<div class="side-empty"><i class="fas fa-check-circle" style="color:#16a34a"></i> ' + u.esc(u.t(ctx, "all_entered", gettext("Bütün tələbələr daxil olub."))) + '</div>';
      return;
    }
    el.innerHTML = list.map(function (s) {
      return '<div class="side-item">' +
        '<div class="avatar">' + u.esc(u.initials(s.name)).toUpperCase() + '</div>' +
        '<div class="si-body"><div class="si-name">' + u.esc(s.name) + '</div>' +
        '<div class="si-meta">' + u.esc(u.t(ctx, "not_entered_yet", gettext("Hələ giriş etməyib"))) + '</div></div></div>';
    }).join("");
  }

  function renderBlocked(ctx, d) {
    var list = (d.students || []).filter(function (s) {
      return s.supervision_status === "locked" || s.supervision_status === "removed";
    }).filter(function (s) { return !s.is_finished; });
    u.$("blockedBadge").textContent = list.length;
    var el = u.$("blockedList");
    if (!list.length) {
      el.innerHTML = '<div class="side-empty"><i class="fas fa-shield-alt" style="color:#16a34a"></i> ' + u.esc(u.t(ctx, "no_blocked", gettext("Bloklanmış tələbə yoxdur."))) + '</div>';
      return;
    }
    el.innerHTML = list.map(function (s) {
      var statusLabel = s.supervision_status === "locked" ? u.t(ctx, "blocked_temp", gettext("Müvəqqəti bloklu")) : u.t(ctx, "blocked_removed", gettext("Çıxarılıb"));
      return '<div class="side-item">' +
        '<div class="avatar" style="background:#fee2e2;color:#b91c1c;">' + u.esc(u.initials(s.name)).toUpperCase() + '</div>' +
        '<div class="si-body"><div class="si-name">' + u.esc(s.name) + '</div>' +
        '<div class="si-meta">' + statusLabel + ' · ' + s.violation_count + ' ' + u.t(ctx, "stat_violations", "pozuntu") + '</div></div>' +
        '<div class="blocked-actions">' +
        '<button type="button" class="btn-sm-action btn-sm-resume" data-blocked-resume="' + s.attempt_id + '" title="' + u.esc(u.t(ctx, "btn_resume", gettext("Bərpa et"))) + '"><i class="fas fa-play"></i></button>' +
        '<button type="button" class="btn-sm-action btn-sm-stop" data-blocked-stop="' + s.attempt_id + '" title="' + u.esc(u.t(ctx, "btn_remove_student", gettext("İmtahandan uzaqlaşdır"))) + '"><i class="fas fa-ban"></i></button>' +
        '</div></div>';
    }).join("");
  }

  function renderFeed(ctx, d) {
    var inc = d.recent_incidents || [];
    var el = u.$("incidentFeed");
    if (!inc.length) {
      el.innerHTML = '<div class="side-empty"><i class="fas fa-shield-alt" style="color:#16a34a"></i> ' + u.esc(u.t(ctx, "no_incidents", gettext("Şübhəli hadisə yoxdur."))) + '</div>';
      return;
    }
    el.innerHTML = inc.map(function (e) {
      var icon = (e.severity === "high" || e.severity === "critical") ? "fa-triangle-exclamation" : (e.severity === "medium") ? "fa-wifi" : "fa-flag";
      return '<div class="side-item">' +
        '<div class="feed-icon sev-' + u.esc(e.severity) + '"><i class="fas ' + icon + '"></i></div>' +
        '<div class="si-body"><div class="si-name" style="font-weight:600">' + u.esc(ctx.EVENT_LABELS[e.event_type] || e.event_type) + '</div>' +
        '<div class="si-meta">' + u.esc(e.student_name) + ' · ' + u.timeAgo(e.timestamp) + '</div></div></div>';
    }).join("");
  }

  function renderStatusChart(ctx, d) {
    if (typeof Chart === "undefined") {
      return;
    }
    var dist = d.status_dist || {};
    var keys = Object.keys(dist).filter(function (k) { return dist[k] > 0; });
    var canvas = u.$("statusChart");
    if (!keys.length) {
      canvas.style.display = "none";
      return;
    }
    canvas.style.display = "";
    var labels = keys.map(function (k) { return STATUS_CHART_LABELS[k] || k; });
    var values = keys.map(function (k) { return dist[k]; });
    var colors = keys.map(function (k) { return STATUS_CHART_COLORS[k] || "#94a3b8"; });
    if (ctx.statusChart) {
      ctx.statusChart.data.labels = labels;
      ctx.statusChart.data.datasets[0].data = values;
      ctx.statusChart.data.datasets[0].backgroundColor = colors;
      ctx.statusChart.update("none");
    } else {
      ctx.statusChart = new Chart(canvas, {
        type: "doughnut",
        data: { labels: labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom", labels: { boxWidth: 12, padding: 14, font: { size: 12 } } } } }
      });
    }
  }

  function renderProgressChart(ctx, d) {
    if (typeof Chart === "undefined") {
      return;
    }
    var buckets = [0, 0, 0, 0, 0];
    var labels = ["0-20%", "21-40%", "41-60%", "61-80%", "81-100%"];
    (d.students || []).forEach(function (s) {
      if (s.state !== "in_progress") {
        return;
      }
      var p = s.progress_pct;
      var idx = p <= 20 ? 0 : p <= 40 ? 1 : p <= 60 ? 2 : p <= 80 ? 3 : 4;
      buckets[idx]++;
    });
    var canvas = u.$("progressChart");
    if (ctx.progressChart) {
      ctx.progressChart.data.datasets[0].data = buckets;
      ctx.progressChart.update("none");
    } else {
      ctx.progressChart = new Chart(canvas, {
        type: "bar",
        data: { labels: labels, datasets: [{ label: gettext("Tələbə sayı"), data: buckets, backgroundColor: "#0ea5e9", borderRadius: 6 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { stepSize: 1, precision: 0 } } } }
      });
    }
  }

  function renderAll(ctx, d) {
    ctx.state = d;
    renderStats(ctx, d);
    renderMap(ctx, d);
    renderBlocked(ctx, d);
    renderNotEntered(ctx, d);
    renderFeed(ctx, d);
    renderStatusChart(ctx, d);
    renderProgressChart(ctx, d);
  }

  ns.render = {
    renderAll: renderAll
  };
})(window);
