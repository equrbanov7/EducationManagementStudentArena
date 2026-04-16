/**
 * Statistics section — Chart.js rendering, AI summary, table sorting/search.
 *
 * Reads window.STATS_DATA (set by the inline <script> in the template)
 * and builds all charts + interactive features.
 */
document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    var data = window.STATS_DATA;
    if (!data || !data.summary) return;

    var role = data.role || "student";
    var COLORS = {
        primary: "#0d6efd",
        success: "#198754",
        warning: "#ffc107",
        danger: "#dc3545",
        info: "#0dcaf0",
        secondary: "#6c757d",
        light: "#f8f9fa",
    };
    var CHART_PALETTE = [
        "#0d6efd", "#198754", "#ffc107", "#dc3545", "#0dcaf0",
        "#6f42c1", "#fd7e14", "#20c997", "#d63384", "#6c757d",
    ];

    function getCtx(id) {
        var el = document.getElementById(id);
        return el ? el.getContext("2d") : null;
    }

    /* ── Trend chart (line) ────────────────────────────────────── */
    var trendCtx = getCtx("statsTrendChart");
    if (trendCtx && data.trend && data.trend.labels && data.trend.labels.length) {
        new Chart(trendCtx, {
            type: "line",
            data: {
                labels: data.trend.labels,
                datasets: [{
                    label: role === "student" ? "Orta bal (%)" : "Təqdimlər",
                    data: data.trend.values,
                    borderColor: COLORS.primary,
                    backgroundColor: "rgba(13,110,253,0.1)",
                    tension: 0.3,
                    fill: true,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true },
                },
            },
        });
    }

    /* ── Breakdown doughnut ────────────────────────────────────── */
    var breakdownCtx = getCtx("statsBreakdownChart");
    if (breakdownCtx) {
        var bLabels, bData, bColors;
        if (role === "student" && data.summary) {
            bLabels = ["Keçənlər", "Qalan"];
            bData = [data.summary.pass_count || 0, data.summary.fail_count || 0];
            bColors = [COLORS.success, COLORS.danger];
        } else {
            bLabels = ["İmtahan", "Tapşırıq", "Lab", "Layihə"];
            bData = [
                data.summary.total_attempts || data.summary.total_exams || 0,
                data.summary.assignment_total || 0,
                data.summary.lab_total || 0,
                data.summary.project_total || 0,
            ];
            bColors = [COLORS.primary, COLORS.success, COLORS.warning, COLORS.info];
        }
        new Chart(breakdownCtx, {
            type: "doughnut",
            data: {
                labels: bLabels,
                datasets: [{
                    data: bData,
                    backgroundColor: bColors,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 11 } } },
                },
            },
        });
    }

    /* ── Comparison bar chart (teacher groups / org admin courses / superadmin orgs) */
    var compCtx = getCtx("statsComparisonChart");
    if (compCtx) {
        var cLabels = [], cData = [], cLabel = "";
        if (role === "superadmin" && data.org_comparison) {
            cLabels = data.org_comparison.map(function(o) { return o.name.substring(0, 20); });
            cData = data.org_comparison.map(function(o) { return o.members; });
            cLabel = "Üzvlər";
        } else if (role === "org_admin" && data.course_rankings) {
            cLabels = data.course_rankings.map(function(c) { return (c.course__title || "").substring(0, 20); });
            cData = data.course_rankings.map(function(c) { return c.student_count; });
            cLabel = "Tələbə sayı";
        } else if (role === "teacher" && data.group_comparison) {
            cLabels = data.group_comparison.map(function(g) { return g.name.substring(0, 20); });
            cData = data.group_comparison.map(function(g) { return g.avg_score; });
            cLabel = "Orta bal (%)";
        }
        if (cLabels.length) {
            new Chart(compCtx, {
                type: "bar",
                data: {
                    labels: cLabels,
                    datasets: [{
                        label: cLabel,
                        data: cData,
                        backgroundColor: CHART_PALETTE.slice(0, cLabels.length),
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    indexAxis: cLabels.length > 8 ? "y" : "x",
                    plugins: { legend: { display: false } },
                    scales: { y: { beginAtZero: true } },
                },
            });
        }
    }

    /* ── Grading status stacked bar (teacher / org admin / superadmin) */
    var gradingCtx = getCtx("statsGradingChart");
    if (gradingCtx) {
        var gLabels = ["İmtahan", "Tapşırıq", "Lab", "Layihə"];
        var gGraded, gPending;
        var s = data.summary;
        if (role === "teacher") {
            gGraded = [s.checked_attempts || 0, s.assignment_graded || 0, s.lab_graded || 0, s.project_graded || 0];
            gPending = [
                (s.total_attempts || 0) - (s.checked_attempts || 0),
                (s.assignment_total || 0) - (s.assignment_graded || 0),
                (s.lab_total || 0) - (s.lab_graded || 0),
                (s.project_total || 0) - (s.project_graded || 0),
            ];
        } else {
            gGraded = [s.checked_attempts || 0, s.assignment_graded || 0, s.lab_graded || 0, s.project_graded || 0];
            gPending = [
                (s.total_attempts || 0) - (s.checked_attempts || 0),
                (s.assignment_total || 0) - (s.assignment_graded || 0),
                (s.lab_total || 0) - (s.lab_graded || 0),
                (s.project_total || 0) - (s.project_graded || 0),
            ];
        }
        new Chart(gradingCtx, {
            type: "bar",
            data: {
                labels: gLabels,
                datasets: [
                    { label: "Qiymətləndirilmiş", data: gGraded, backgroundColor: COLORS.success },
                    { label: "Gözləyən", data: gPending, backgroundColor: COLORS.warning },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
                scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } },
            },
        });
    }

    /* ── Student content-type bar chart ────────────────────────── */
    var contentCtx = getCtx("statsContentBarChart");
    if (contentCtx && data.score_breakdown) {
        var sb = data.score_breakdown;
        new Chart(contentCtx, {
            type: "bar",
            data: {
                labels: ["İmtahan", "Tapşırıq", "Lab", "Layihə"],
                datasets: [{
                    label: "Orta bal (%)",
                    data: [sb.exam_avg || 0, sb.assignment_avg || 0, sb.lab_avg || 0, sb.project_avg || 0],
                    backgroundColor: [COLORS.primary, COLORS.success, COLORS.warning, COLORS.info],
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true, max: 100 } },
            },
        });
    }

    /* ── Table sorting ─────────────────────────────────────────── */
    document.querySelectorAll(".stats-sortable-table").forEach(function (table) {
        var headers = table.querySelectorAll("th.stats-sortable");
        headers.forEach(function (th, colIndex) {
            th.addEventListener("click", function () {
                var isAsc = th.classList.contains("sort-asc");
                headers.forEach(function (h) { h.classList.remove("sort-asc", "sort-desc"); });
                th.classList.add(isAsc ? "sort-desc" : "sort-asc");
                var tbody = table.querySelector("tbody");
                var rows = Array.from(tbody.querySelectorAll("tr"));
                var dir = isAsc ? -1 : 1;
                rows.sort(function (a, b) {
                    var aVal = a.cells[colIndex] ? a.cells[colIndex].textContent.trim() : "";
                    var bVal = b.cells[colIndex] ? b.cells[colIndex].textContent.trim() : "";
                    var aNum = parseFloat(aVal.replace(/[^0-9.\-]/g, ""));
                    var bNum = parseFloat(bVal.replace(/[^0-9.\-]/g, ""));
                    if (!isNaN(aNum) && !isNaN(bNum)) return (aNum - bNum) * dir;
                    return aVal.localeCompare(bVal) * dir;
                });
                rows.forEach(function (r) { tbody.appendChild(r); });
            });
        });
    });

    /* ── Table search ──────────────────────────────────────────── */
    function bindTableSearch(inputId, tableId) {
        var input = document.getElementById(inputId);
        var table = document.getElementById(tableId);
        if (!input || !table) return;
        input.addEventListener("input", function () {
            var q = input.value.toLowerCase().trim();
            var rows = table.querySelectorAll("tbody tr");
            rows.forEach(function (row) {
                var text = row.textContent.toLowerCase();
                row.style.display = text.indexOf(q) !== -1 ? "" : "none";
            });
        });
    }
    bindTableSearch("statsTableSearchOrg", "statsOrgTable");
    bindTableSearch("statsTableSearchTeacher", "statsTeacherTable");

    /* ── AI summary ────────────────────────────────────────────── */
    var aiBtn = document.getElementById("statsAiSummaryBtn");
    var aiCard = document.getElementById("statsAiSummaryCard");
    var aiBody = document.getElementById("statsAiSummaryBody");
    var aiCloseBtn = document.getElementById("statsAiCloseBtn");

    if (aiBtn && aiCard && aiBody) {
        aiBtn.addEventListener("click", function () {
            aiCard.classList.remove("d-none");
            aiBody.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm text-primary"></div> <span class="ms-2 text-muted">AI xülasə hazırlanır...</span></div>';

            var params = new URLSearchParams(window.location.search);
            params.set("section", "statistics");
            params.set("stat_ai_summary", "1");

            fetch(window.location.pathname + "?" + params.toString(), {
                headers: { "X-Requested-With": "XMLHttpRequest" },
                credentials: "same-origin",
            })
            .then(function (res) { return res.json(); })
            .then(function (json) {
                if (json.ok && json.summary) {
                    aiBody.innerHTML = '<div class="ai-summary-content">' + _mdToHtml(json.summary) + '</div>';
                    if (json.remaining !== undefined) {
                        aiBody.innerHTML += '<div class="text-muted small mt-2">Qalan sorğu: ' + json.remaining + '/' + (json.limit || '?') + '</div>';
                    }
                } else {
                    aiBody.innerHTML = '<div class="alert alert-warning mb-0">' + (json.error || "AI xülasə alınmadı.") + '</div>';
                }
            })
            .catch(function () {
                aiBody.innerHTML = '<div class="alert alert-danger mb-0">AI sorğusu zamanı xəta baş verdi.</div>';
            });
        });

        if (aiCloseBtn) {
            aiCloseBtn.addEventListener("click", function () {
                aiCard.classList.add("d-none");
            });
        }
    }

    /* Simple markdown-to-HTML converter */
    function _mdToHtml(md) {
        if (!md) return "";
        var html = md
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/^### (.+)$/gm, "<h5>$1</h5>")
            .replace(/^## (.+)$/gm, "<h4>$1</h4>")
            .replace(/^# (.+)$/gm, "<h3>$1</h3>")
            .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
            .replace(/\*(.+?)\*/g, "<em>$1</em>")
            .replace(/^- (.+)$/gm, "<li>$1</li>")
            .replace(/(<li>[\s\S]*?<\/li>)/g, "<ul>$1</ul>")
            .replace(/<\/ul>\s*<ul>/g, "")
            .replace(/\n{2,}/g, "</p><p>")
            .replace(/\n/g, "<br>");
        return "<p>" + html + "</p>";
    }
});
