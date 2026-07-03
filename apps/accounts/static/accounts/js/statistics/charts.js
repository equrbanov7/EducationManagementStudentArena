(function (window) {
  "use strict";

  var ns = window.EMSStatistics || (window.EMSStatistics = {});
  var u = ns.utils;

  function renderTrend(ctx) {
    var data = ctx.data;
    var i18n = ctx.i18n;
    var trendCtx = u.getCtx("statsTrendChart");
    if (trendCtx && data.trend && data.trend.labels && data.trend.labels.length) {
      new Chart(trendCtx, {
        type: "line",
        data: {
          labels: data.trend.labels,
          datasets: [{
            label: ctx.role === "student" ? (i18n.avg_score_pct || "Avg score (%)") : (i18n.submissions || "Submissions"),
            data: data.trend.values,
            borderColor: ctx.COLORS.primary,
            backgroundColor: "rgba(13,110,253,0.12)",
            tension: 0.3,
            fill: true,
            pointRadius: 4,
            pointHoverRadius: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true } }
        }
      });
    }
  }

  function renderBreakdown(ctx) {
    var data = ctx.data;
    var i18n = ctx.i18n;
    var breakdownCtx = u.getCtx("statsBreakdownChart");
    if (!breakdownCtx) {
      return;
    }
    var breakdownLabels;
    var breakdownData;
    var breakdownColors;

    if (ctx.role === "student") {
      breakdownLabels = [i18n.passed || "Passed", i18n.failed || "Failed"];
      breakdownData = [data.summary.pass_count || 0, data.summary.fail_count || 0];
      breakdownColors = [ctx.COLORS.success, ctx.COLORS.danger];
    } else {
      breakdownLabels = [
        i18n.exam || "Exam",
        i18n.assignment || "Assignment",
        i18n.lab || "Lab",
        i18n.project || "Project"
      ];
      breakdownData = [
        data.summary.total_attempts || data.summary.total_exams || 0,
        data.summary.assignment_total || 0,
        data.summary.lab_total || 0,
        data.summary.project_total || 0
      ];
      breakdownColors = [ctx.COLORS.primary, ctx.COLORS.success, ctx.COLORS.warning, ctx.COLORS.info];
    }

    new Chart(breakdownCtx, {
      type: "doughnut",
      data: {
        labels: breakdownLabels,
        datasets: [{ data: breakdownData, backgroundColor: breakdownColors }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } }
        }
      }
    });
  }

  function renderComparison(ctx) {
    var data = ctx.data;
    var i18n = ctx.i18n;
    var compCtx = u.getCtx("statsComparisonChart");
    if (!compCtx) {
      return;
    }
    var comparisonLabels = [];
    var comparisonData = [];
    var comparisonLabel = "";

    if (ctx.role === "superadmin" && Array.isArray(data.org_comparison)) {
      comparisonLabels = data.org_comparison.slice(0, 8).map(function (item) { return u.truncateLabel(item.name); });
      comparisonData = data.org_comparison.slice(0, 8).map(function (item) { return item.members; });
      comparisonLabel = i18n.members || "Members";
    } else if (ctx.role === "org_admin" && Array.isArray(data.course_rankings)) {
      comparisonLabels = data.course_rankings.slice(0, 8).map(function (item) { return u.truncateLabel(item.course__title); });
      comparisonData = data.course_rankings.slice(0, 8).map(function (item) { return item.student_count; });
      comparisonLabel = i18n.student_count || "Student count";
    } else if (ctx.role === "teacher" && Array.isArray(data.group_comparison)) {
      comparisonLabels = data.group_comparison.slice(0, 8).map(function (item) { return u.truncateLabel(item.name); });
      comparisonData = data.group_comparison.slice(0, 8).map(function (item) { return item.avg_score; });
      comparisonLabel = i18n.avg_score || "Avg score (%)";
    }

    if (comparisonLabels.length) {
      new Chart(compCtx, {
        type: "bar",
        data: {
          labels: comparisonLabels,
          datasets: [{
            label: comparisonLabel,
            data: comparisonData,
            backgroundColor: ctx.CHART_PALETTE.slice(0, comparisonLabels.length)
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          indexAxis: comparisonLabels.length > 6 ? "y" : "x",
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true } }
        }
      });
    }
  }

  function renderGrading(ctx) {
    var gradingCtx = u.getCtx("statsGradingChart");
    if (!gradingCtx) {
      return;
    }
    var i18n = ctx.i18n;
    var summary = ctx.data.summary;
    var gradingLabels = [
      i18n.exam || "Exam",
      i18n.assignment || "Assignment",
      i18n.lab || "Lab",
      i18n.project || "Project"
    ];
    var gradedValues = [
      summary.checked_attempts || 0,
      summary.assignment_graded || 0,
      summary.lab_graded || 0,
      summary.project_graded || 0
    ];
    var pendingValues = [
      Math.max((summary.total_attempts || 0) - (summary.checked_attempts || 0), 0),
      Math.max((summary.assignment_total || 0) - (summary.assignment_graded || 0), 0),
      Math.max((summary.lab_total || 0) - (summary.lab_graded || 0), 0),
      Math.max((summary.project_total || 0) - (summary.project_graded || 0), 0)
    ];

    new Chart(gradingCtx, {
      type: "bar",
      data: {
        labels: gradingLabels,
        datasets: [
          { label: i18n.graded || "Graded", data: gradedValues, backgroundColor: ctx.COLORS.success },
          { label: i18n.pending || "Pending", data: pendingValues, backgroundColor: ctx.COLORS.warning }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
        scales: {
          x: { stacked: true },
          y: { stacked: true, beginAtZero: true }
        }
      }
    });
  }

  function renderContent(ctx) {
    var contentCtx = u.getCtx("statsContentBarChart");
    if (contentCtx && ctx.data.score_breakdown) {
      var scoreBreakdown = ctx.data.score_breakdown;
      new Chart(contentCtx, {
        type: "bar",
        data: {
          labels: [
            ctx.i18n.exam || "Exam",
            ctx.i18n.assignment || "Assignment",
            ctx.i18n.lab || "Lab",
            ctx.i18n.project || "Project"
          ],
          datasets: [{
            label: ctx.i18n.avg_score_pct || "Avg score (%)",
            data: [
              scoreBreakdown.exam_avg || 0,
              scoreBreakdown.assignment_avg || 0,
              scoreBreakdown.lab_avg || 0,
              scoreBreakdown.project_avg || 0
            ],
            backgroundColor: [ctx.COLORS.primary, ctx.COLORS.success, ctx.COLORS.warning, ctx.COLORS.info]
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, max: 100 } }
        }
      });
    }
  }

  function renderBalance(ctx) {
    var balanceCtx = u.getCtx("statsBalanceRadarChart");
    if (!balanceCtx) {
      return;
    }
    var balanceLabels;
    var balanceValues;

    if (ctx.role === "student") {
      balanceLabels = ["Orta bal", gettext("Keçid"), "Yoxlanma", gettext("Vaxtında")];
      balanceValues = [
        ctx.data.summary.avg_score || 0,
        ctx.data.summary.pass_rate || 0,
        u.pct((ctx.data.summary.total_items || 0) - (ctx.data.summary.pending_items || 0), ctx.data.summary.total_items || 0),
        u.pct(ctx.data.summary.on_time_count || 0, (ctx.data.summary.on_time_count || 0) + (ctx.data.summary.late_count || 0))
      ];
    } else {
      balanceLabels = [gettext("İmtahan yoxlama"), gettext("Tapşırıq yoxlama"), "Lab yoxlama", gettext("Layihə yoxlama"), gettext("Təqdimetmə")];
      balanceValues = [
        u.pct(ctx.data.summary.checked_attempts || 0, ctx.data.summary.total_attempts || 0),
        u.pct(ctx.data.summary.assignment_graded || 0, ctx.data.summary.assignment_total || 0),
        u.pct(ctx.data.summary.lab_graded || 0, ctx.data.summary.lab_total || 0),
        u.pct(ctx.data.summary.project_graded || 0, ctx.data.summary.project_total || 0),
        u.pct(ctx.data.summary.submitted_attempts || 0, ctx.data.summary.total_attempts || 0)
      ];
    }

    new Chart(balanceCtx, {
      type: "radar",
      data: {
        labels: balanceLabels,
        datasets: [{
          label: "Balans",
          data: balanceValues,
          borderColor: ctx.COLORS.primary,
          backgroundColor: "rgba(13,110,253,0.16)",
          pointBackgroundColor: ctx.COLORS.primary
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          r: {
            beginAtZero: true,
            max: 100,
            ticks: { stepSize: 20, backdropColor: "transparent" }
          }
        }
      }
    });
  }

  function buildDetailConfig(ctx) {
    var data = ctx.data;
    if (ctx.role === "superadmin" && Array.isArray(data.org_comparison) && data.org_comparison.length) {
      var orgRows = data.org_comparison.slice(0, 8);
      return {
        data: {
          labels: orgRows.map(function (item) { return u.truncateLabel(item.name); }),
          datasets: [
            { type: "bar", label: "Kurs", data: orgRows.map(function (item) { return item.courses; }), backgroundColor: ctx.CHART_PALETTE[0] },
            { type: "bar", label: gettext("İmtahan"), data: orgRows.map(function (item) { return item.exams; }), backgroundColor: ctx.CHART_PALETTE[1] },
            { type: "line", label: gettext("Cəhd"), data: orgRows.map(function (item) { return item.attempts; }), borderColor: ctx.CHART_PALETTE[3], backgroundColor: "rgba(220,53,69,0.14)", tension: 0.3, yAxisID: "y1" }
          ]
        },
        options: detailOptions(false)
      };
    } else if (ctx.role === "org_admin" && Array.isArray(data.teacher_overview) && data.teacher_overview.length) {
      var teacherRows = data.teacher_overview.slice(0, 8);
      return {
        data: {
          labels: teacherRows.map(function (item) { return u.truncateLabel(item.name); }),
          datasets: [
            { type: "bar", label: "Kurs", data: teacherRows.map(function (item) { return item.course_count; }), backgroundColor: ctx.CHART_PALETTE[0] },
            { type: "bar", label: gettext("İmtahan"), data: teacherRows.map(function (item) { return item.exam_count; }), backgroundColor: ctx.CHART_PALETTE[1] },
            { type: "line", label: "Orta bal %", data: teacherRows.map(function (item) { return item.avg_score; }), borderColor: ctx.CHART_PALETTE[4], backgroundColor: "rgba(13,202,240,0.14)", tension: 0.3, yAxisID: "y1" }
          ]
        },
        options: detailOptions(true)
      };
    } else if (ctx.role === "teacher" && Array.isArray(data.course_overview) && data.course_overview.length) {
      var courseRows = data.course_overview.slice(0, 8);
      return {
        data: {
          labels: courseRows.map(function (item) { return u.truncateLabel(item.title); }),
          datasets: [
            { type: "bar", label: gettext("Cəhd"), data: courseRows.map(function (item) { return item.attempt_count; }), backgroundColor: ctx.CHART_PALETTE[0] },
            { type: "line", label: "Orta bal %", data: courseRows.map(function (item) { return item.avg_score; }), borderColor: ctx.CHART_PALETTE[1], backgroundColor: "rgba(25,135,84,0.14)", tension: 0.3, yAxisID: "y1" },
            { type: "line", label: gettext("Keçid %"), data: courseRows.map(function (item) { return item.pass_rate; }), borderColor: ctx.CHART_PALETTE[2], backgroundColor: "rgba(255,193,7,0.14)", tension: 0.3, yAxisID: "y1" }
          ]
        },
        options: detailOptions(true)
      };
    }
    return null;
  }

  function detailOptions(percentAxis) {
    var y1 = { beginAtZero: true, position: "right", grid: { drawOnChartArea: false } };
    if (percentAxis) {
      y1.max = 100;
    }
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" } },
      scales: {
        y: { beginAtZero: true },
        y1: y1
      }
    };
  }

  function renderDetail(ctx) {
    var detailCtx = u.getCtx("statsDetailChart");
    if (!detailCtx) {
      return;
    }
    var detailConfig = buildDetailConfig(ctx);
    if (detailConfig) {
      new Chart(detailCtx, detailConfig);
    }
  }

  function init(ctx) {
    renderTrend(ctx);
    renderBreakdown(ctx);
    renderComparison(ctx);
    renderGrading(ctx);
    renderContent(ctx);
    renderBalance(ctx);
    renderDetail(ctx);
  }

  ns.charts = {
    init: init
  };
})(window);
