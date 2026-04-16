/**
 * Statistics section — charts, AI summary, filter UX, table search/sort.
 */
document.addEventListener("DOMContentLoaded", function () {
    "use strict";

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

    var data = window.STATS_DATA;
    if (!data || !data.summary) {
        return;
    }

    var i18n = window.STATS_I18N || {};
    var role = data.role || "student";
    var COLORS = {
        primary: "#0d6efd",
        success: "#198754",
        warning: "#ffc107",
        danger: "#dc3545",
        info: "#0dcaf0",
        secondary: "#6c757d",
    };
    var CHART_PALETTE = [
        "#0d6efd", "#198754", "#ffc107", "#dc3545", "#0dcaf0",
        "#6f42c1", "#fd7e14", "#20c997", "#d63384", "#6c757d"
    ];

    function pct(numerator, denominator) {
        if (!denominator) {
            return 0;
        }
        return Math.round((Number(numerator || 0) * 1000) / Number(denominator)) / 10;
    }

    function getCtx(id) {
        var el = document.getElementById(id);
        return el ? el.getContext("2d") : null;
    }

    function truncateLabel(value) {
        var text = String(value || "");
        return text.length > 22 ? text.slice(0, 22) + "..." : text;
    }

    /* ── Trend chart ───────────────────────────────────────────── */
    var trendCtx = getCtx("statsTrendChart");
    if (trendCtx && data.trend && data.trend.labels && data.trend.labels.length) {
        new Chart(trendCtx, {
            type: "line",
            data: {
                labels: data.trend.labels,
                datasets: [{
                    label: role === "student" ? (i18n.avg_score_pct || "Avg score (%)") : (i18n.submissions || "Submissions"),
                    data: data.trend.values,
                    borderColor: COLORS.primary,
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

    /* ── Breakdown doughnut ───────────────────────────────────── */
    var breakdownCtx = getCtx("statsBreakdownChart");
    if (breakdownCtx) {
        var breakdownLabels;
        var breakdownData;
        var breakdownColors;

        if (role === "student") {
            breakdownLabels = [i18n.passed || "Passed", i18n.failed || "Failed"];
            breakdownData = [data.summary.pass_count || 0, data.summary.fail_count || 0];
            breakdownColors = [COLORS.success, COLORS.danger];
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
            breakdownColors = [COLORS.primary, COLORS.success, COLORS.warning, COLORS.info];
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

    /* ── Comparison chart ─────────────────────────────────────── */
    var compCtx = getCtx("statsComparisonChart");
    if (compCtx) {
        var comparisonLabels = [];
        var comparisonData = [];
        var comparisonLabel = "";

        if (role === "superadmin" && Array.isArray(data.org_comparison)) {
            comparisonLabels = data.org_comparison.slice(0, 8).map(function (item) { return truncateLabel(item.name); });
            comparisonData = data.org_comparison.slice(0, 8).map(function (item) { return item.members; });
            comparisonLabel = i18n.members || "Members";
        } else if (role === "org_admin" && Array.isArray(data.course_rankings)) {
            comparisonLabels = data.course_rankings.slice(0, 8).map(function (item) { return truncateLabel(item.course__title); });
            comparisonData = data.course_rankings.slice(0, 8).map(function (item) { return item.student_count; });
            comparisonLabel = i18n.student_count || "Student count";
        } else if (role === "teacher" && Array.isArray(data.group_comparison)) {
            comparisonLabels = data.group_comparison.slice(0, 8).map(function (item) { return truncateLabel(item.name); });
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
                        backgroundColor: CHART_PALETTE.slice(0, comparisonLabels.length)
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

    /* ── Grading status stacked bar ───────────────────────────── */
    var gradingCtx = getCtx("statsGradingChart");
    if (gradingCtx) {
        var summary = data.summary;
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
                    { label: i18n.graded || "Graded", data: gradedValues, backgroundColor: COLORS.success },
                    { label: i18n.pending || "Pending", data: pendingValues, backgroundColor: COLORS.warning }
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

    /* ── Student content chart ────────────────────────────────── */
    var contentCtx = getCtx("statsContentBarChart");
    if (contentCtx && data.score_breakdown) {
        var scoreBreakdown = data.score_breakdown;
        new Chart(contentCtx, {
            type: "bar",
            data: {
                labels: [
                    i18n.exam || "Exam",
                    i18n.assignment || "Assignment",
                    i18n.lab || "Lab",
                    i18n.project || "Project"
                ],
                datasets: [{
                    label: i18n.avg_score_pct || "Avg score (%)",
                    data: [
                        scoreBreakdown.exam_avg || 0,
                        scoreBreakdown.assignment_avg || 0,
                        scoreBreakdown.lab_avg || 0,
                        scoreBreakdown.project_avg || 0
                    ],
                    backgroundColor: [COLORS.primary, COLORS.success, COLORS.warning, COLORS.info]
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

    /* ── Balance radar chart ──────────────────────────────────── */
    var balanceCtx = getCtx("statsBalanceRadarChart");
    if (balanceCtx) {
        var balanceLabels;
        var balanceValues;

        if (role === "student") {
            balanceLabels = ["Orta bal", "Keçid", "Yoxlanma", "Vaxtında", "Canlı dəqiqlik"];
            balanceValues = [
                data.summary.avg_score || 0,
                data.summary.pass_rate || 0,
                pct((data.summary.total_items || 0) - (data.summary.pending_items || 0), data.summary.total_items || 0),
                pct(data.summary.on_time_count || 0, (data.summary.on_time_count || 0) + (data.summary.late_count || 0)),
                data.summary.live_accuracy || 0
            ];
        } else {
            balanceLabels = ["İmtahan yoxlama", "Tapşırıq yoxlama", "Lab yoxlama", "Layihə yoxlama", "Təqdimetmə"];
            balanceValues = [
                pct(data.summary.checked_attempts || 0, data.summary.total_attempts || 0),
                pct(data.summary.assignment_graded || 0, data.summary.assignment_total || 0),
                pct(data.summary.lab_graded || 0, data.summary.lab_total || 0),
                pct(data.summary.project_graded || 0, data.summary.project_total || 0),
                pct(data.summary.submitted_attempts || 0, data.summary.total_attempts || 0)
            ];
        }

        new Chart(balanceCtx, {
            type: "radar",
            data: {
                labels: balanceLabels,
                datasets: [{
                    label: "Balans",
                    data: balanceValues,
                    borderColor: COLORS.primary,
                    backgroundColor: "rgba(13,110,253,0.16)",
                    pointBackgroundColor: COLORS.primary
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

    /* ── Detail chart ─────────────────────────────────────────── */
    var detailCtx = getCtx("statsDetailChart");
    if (detailCtx) {
        var detailConfig = null;

        if (role === "superadmin" && Array.isArray(data.org_comparison) && data.org_comparison.length) {
            var orgRows = data.org_comparison.slice(0, 8);
            detailConfig = {
                data: {
                    labels: orgRows.map(function (item) { return truncateLabel(item.name); }),
                    datasets: [
                        { type: "bar", label: "Kurs", data: orgRows.map(function (item) { return item.courses; }), backgroundColor: CHART_PALETTE[0] },
                        { type: "bar", label: "İmtahan", data: orgRows.map(function (item) { return item.exams; }), backgroundColor: CHART_PALETTE[1] },
                        { type: "line", label: "Cəhd", data: orgRows.map(function (item) { return item.attempts; }), borderColor: CHART_PALETTE[3], backgroundColor: "rgba(220,53,69,0.14)", tension: 0.3, yAxisID: "y1" }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: "bottom" } },
                    scales: {
                        y: { beginAtZero: true },
                        y1: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false } }
                    }
                }
            };
        } else if (role === "org_admin" && Array.isArray(data.teacher_overview) && data.teacher_overview.length) {
            var teacherRows = data.teacher_overview.slice(0, 8);
            detailConfig = {
                data: {
                    labels: teacherRows.map(function (item) { return truncateLabel(item.name); }),
                    datasets: [
                        { type: "bar", label: "Kurs", data: teacherRows.map(function (item) { return item.course_count; }), backgroundColor: CHART_PALETTE[0] },
                        { type: "bar", label: "İmtahan", data: teacherRows.map(function (item) { return item.exam_count; }), backgroundColor: CHART_PALETTE[1] },
                        { type: "line", label: "Orta bal %", data: teacherRows.map(function (item) { return item.avg_score; }), borderColor: CHART_PALETTE[4], backgroundColor: "rgba(13,202,240,0.14)", tension: 0.3, yAxisID: "y1" }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: "bottom" } },
                    scales: {
                        y: { beginAtZero: true },
                        y1: { beginAtZero: true, max: 100, position: "right", grid: { drawOnChartArea: false } }
                    }
                }
            };
        } else if (role === "teacher" && Array.isArray(data.course_overview) && data.course_overview.length) {
            var courseRows = data.course_overview.slice(0, 8);
            detailConfig = {
                data: {
                    labels: courseRows.map(function (item) { return truncateLabel(item.title); }),
                    datasets: [
                        { type: "bar", label: "Cəhd", data: courseRows.map(function (item) { return item.attempt_count; }), backgroundColor: CHART_PALETTE[0] },
                        { type: "line", label: "Orta bal %", data: courseRows.map(function (item) { return item.avg_score; }), borderColor: CHART_PALETTE[1], backgroundColor: "rgba(25,135,84,0.14)", tension: 0.3, yAxisID: "y1" },
                        { type: "line", label: "Keçid %", data: courseRows.map(function (item) { return item.pass_rate; }), borderColor: CHART_PALETTE[2], backgroundColor: "rgba(255,193,7,0.14)", tension: 0.3, yAxisID: "y1" }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: "bottom" } },
                    scales: {
                        y: { beginAtZero: true },
                        y1: { beginAtZero: true, max: 100, position: "right", grid: { drawOnChartArea: false } }
                    }
                }
            };
        }

        if (detailConfig) {
            new Chart(detailCtx, detailConfig);
        }
    }

    /* ── Table sorting ─────────────────────────────────────────── */
    document.querySelectorAll(".stats-sortable-table").forEach(function (table) {
        var headers = table.querySelectorAll("th.stats-sortable");
        headers.forEach(function (th, colIndex) {
            th.addEventListener("click", function () {
                var isAsc = th.classList.contains("sort-asc");
                headers.forEach(function (header) {
                    header.classList.remove("sort-asc", "sort-desc");
                });
                th.classList.add(isAsc ? "sort-desc" : "sort-asc");

                var tbody = table.querySelector("tbody");
                var rows = Array.from(tbody.querySelectorAll("tr"));
                var direction = isAsc ? -1 : 1;

                rows.sort(function (rowA, rowB) {
                    var aValue = rowA.cells[colIndex] ? rowA.cells[colIndex].textContent.trim() : "";
                    var bValue = rowB.cells[colIndex] ? rowB.cells[colIndex].textContent.trim() : "";
                    var aNum = parseFloat(aValue.replace(/[^0-9.\-]/g, ""));
                    var bNum = parseFloat(bValue.replace(/[^0-9.\-]/g, ""));

                    if (!isNaN(aNum) && !isNaN(bNum)) {
                        return (aNum - bNum) * direction;
                    }
                    return aValue.localeCompare(bValue) * direction;
                });

                rows.forEach(function (row) {
                    tbody.appendChild(row);
                });
            });
        });
    });

    /* ── Table search ──────────────────────────────────────────── */
    function bindTableSearch(inputId, tableId) {
        var input = document.getElementById(inputId);
        var table = document.getElementById(tableId);
        if (!input || !table) {
            return;
        }

        input.addEventListener("input", function () {
            var query = input.value.toLowerCase().trim();
            table.querySelectorAll("tbody tr").forEach(function (row) {
                row.style.display = row.textContent.toLowerCase().indexOf(query) !== -1 ? "" : "none";
            });
        });
    }

    bindTableSearch("statsTableSearchOrg", "statsOrgTable");
    bindTableSearch("statsTableSearchTeacher", "statsTeacherTable");
    bindTableSearch("statsTableSearchCourse", "statsCourseTable");
    bindTableSearch("statsTableSearchGroup", "statsGroupTable");
    bindTableSearch("statsTableSearchTeacherCourse", "statsTeacherCourseTable");

    /* ── AI summary ────────────────────────────────────────────── */
    var aiBtn = document.getElementById("statsAiSummaryBtn");
    var aiBody = document.getElementById("statsAiSummaryBody");
    var aiMeta = document.getElementById("statsAiSummaryMeta");
    var aiBtnLabel = aiBtn ? aiBtn.querySelector(".stats-ai-btn__label") : null;
    var aiDefaultLabel = aiBtnLabel ? aiBtnLabel.textContent : "";

    if (aiBtn && aiBody) {
        aiBtn.addEventListener("click", function () {
            var loadingMsg = i18n.ai_loading || "AI summary is loading...";
            aiBtn.disabled = true;
            aiBtn.classList.add("is-loading");

            if (aiBtnLabel) {
                aiBtnLabel.textContent = loadingMsg;
            }

            aiBody.innerHTML =
                '<div class="stats-ai-state stats-ai-state--loading">' +
                '<div class="spinner-border spinner-border-sm text-primary" role="status"></div>' +
                '<span class="ms-2 text-muted">' + loadingMsg + "</span>" +
                "</div>";

            if (aiMeta) {
                aiMeta.innerHTML =
                    '<span class="stats-ai-meta__pill">Cari filtrlər tətbiq olunur</span>' +
                    '<span class="stats-ai-meta__pill">AI cavabı hazırlanır</span>';
            }

            var params = new URLSearchParams(window.location.search);
            params.set("section", "statistics");
            params.set("stat_ai_summary", "1");

            fetch(window.location.pathname + "?" + params.toString(), {
                headers: { "X-Requested-With": "XMLHttpRequest" },
                credentials: "same-origin"
            })
                .then(function (response) { return response.json(); })
                .then(function (json) {
                    if (json.ok && json.summary) {
                        aiBody.innerHTML = '<div class="ai-summary-content">' + markdownToHtml(json.summary) + "</div>";
                        if (aiMeta) {
                            var metaParts = ['<span class="stats-ai-meta__pill">Filtr üzrə AI xülasə</span>'];
                            if (json.remaining !== undefined) {
                                metaParts.push(
                                    '<span class="stats-ai-meta__pill">' +
                                    (i18n.ai_remaining || "Remaining requests") + ": " + json.remaining + "/" + (json.limit || "?") +
                                    "</span>"
                                );
                            }
                            if (json.cached) {
                                metaParts.push('<span class="stats-ai-meta__pill stats-ai-meta__pill--success">Keşdən cavab</span>');
                            }
                            aiMeta.innerHTML = metaParts.join("");
                        }
                    } else {
                        aiBody.innerHTML =
                            '<div class="stats-ai-state stats-ai-state--warning">' +
                            (json.error || i18n.ai_not_received || "AI summary could not be received.") +
                            "</div>";
                        if (aiMeta) {
                            aiMeta.innerHTML = '<span class="stats-ai-meta__pill stats-ai-meta__pill--warning">AI xülasə alınmadı</span>';
                        }
                    }
                })
                .catch(function () {
                    aiBody.innerHTML =
                        '<div class="stats-ai-state stats-ai-state--error">' +
                        (i18n.ai_error || "An error occurred during the AI request.") +
                        "</div>";
                    if (aiMeta) {
                        aiMeta.innerHTML = '<span class="stats-ai-meta__pill stats-ai-meta__pill--danger">AI xətası</span>';
                    }
                })
                .finally(function () {
                    aiBtn.disabled = false;
                    aiBtn.classList.remove("is-loading");
                    if (aiBtnLabel) {
                        aiBtnLabel.textContent = aiDefaultLabel;
                    }
                });
        });
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }

    function renderInlineMarkdown(value) {
        return escapeHtml(value)
            .replace(/`([^`]+)`/g, "<code>$1</code>")
            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
            .replace(/\*([^*]+)\*/g, "<em>$1</em>");
    }

    function markdownToHtml(markdown) {
        if (!markdown) {
            return "";
        }

        var lines = String(markdown).replace(/\r\n?/g, "\n").split("\n");
        var html = [];
        var paragraph = [];
        var listItems = [];
        var listType = null;

        function flushParagraph() {
            if (!paragraph.length) {
                return;
            }
            html.push("<p>" + paragraph.map(renderInlineMarkdown).join("<br>") + "</p>");
            paragraph = [];
        }

        function flushList() {
            if (!listItems.length || !listType) {
                return;
            }
            html.push(
                "<" + listType + ">" +
                listItems.map(function (item) { return "<li>" + renderInlineMarkdown(item) + "</li>"; }).join("") +
                "</" + listType + ">"
            );
            listItems = [];
            listType = null;
        }

        lines.forEach(function (line) {
            var trimmed = line.trim();
            var headingMatch = trimmed.match(/^(#{1,3})\s+(.+)$/);
            var unorderedMatch = trimmed.match(/^[-*]\s+(.+)$/);
            var orderedMatch = trimmed.match(/^\d+\.\s+(.+)$/);

            if (!trimmed) {
                flushParagraph();
                flushList();
                return;
            }

            if (headingMatch) {
                flushParagraph();
                flushList();
                var level = Math.min(headingMatch[1].length + 2, 5);
                html.push("<h" + level + ">" + renderInlineMarkdown(headingMatch[2]) + "</h" + level + ">");
                return;
            }

            if (unorderedMatch) {
                flushParagraph();
                if (listType && listType !== "ul") {
                    flushList();
                }
                listType = "ul";
                listItems.push(unorderedMatch[1]);
                return;
            }

            if (orderedMatch) {
                flushParagraph();
                if (listType && listType !== "ol") {
                    flushList();
                }
                listType = "ol";
                listItems.push(orderedMatch[1]);
                return;
            }

            flushList();
            paragraph.push(trimmed);
        });

        flushParagraph();
        flushList();
        return html.join("");
    }
});
