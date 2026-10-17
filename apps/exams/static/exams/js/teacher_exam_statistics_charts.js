/*
 * teacher_exam_statistics_charts.js
 * Source: exams/teacher/partials/_teacher_exam_statistics_js.html
 *
 * Renders the exam-statistics dashboard charts (Chart.js), the searchable
 * paginated question table, and the on-demand AI summary. All server data comes
 * from JSON islands rendered by the template:
 *   #statsChartData   chart series (labels/scores/etc.)
 *   #statsExtra       scalars/flags (isWritten, checked/unchecked/pass/fail counts)
 *   #statsChartsI18n  translated strings
 * 2026-10-17 (Paket B): qrafik rəngləri `--ems-*` tokenlərindən oxunur (hex palitrası
 * yoxdur), boş vəziyyət/səhifələmə/AI blokları `tes-*` siniflərindədir, səhifələmə
 * düymələri `aria-current` + `aria-label` daşıyır; inline `style`/`onclick` yoxdur.
 */
(function () {
    "use strict";

    // Tolerant axtarış (EMSSearch: az↔en hərfləri, «234king» → «234 K ing»).
    // «İ».toLowerCase() = «i» + U+0307 (birləşən nöqtə) — mətndən atılır.
    function searchMatcher(query) {
        var q = String(query || "").trim();
        var m = window.EMSSearch ? window.EMSSearch.matcher(q) : null;
        var low = q.toLowerCase();
        return function (text) {
            var t = String(text || "").replace(/\u0307/g, "");
            return m ? m(t) : !low || t.toLowerCase().indexOf(low) !== -1;
        };
    }

    function readIsland(id) {
        var el = document.getElementById(id);
        if (!el) { return {}; }
        try { return JSON.parse(el.textContent) || {}; }
        catch (err) { return {}; }
    }

    var CD = readIsland("statsChartData");
    var EXTRA = readIsland("statsExtra");
    var T = readIsland("statsChartsI18n");
    var PAGE_SIZE = 15;
    var fontFamily = window.getComputedStyle(document.body).fontFamily ||
        "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif";
    var rootStyle = window.getComputedStyle(document.documentElement);
    function tok(name, fallback) {
        var v = rootStyle.getPropertyValue(name);
        return (v && v.trim()) || fallback;
    }
    var C = {
        primary: tok("--ems-primary-600", "#2563eb"),
        primaryDark: tok("--ems-primary-800", "#1e40af"),
        sky: tok("--ems-sky-600", "#0284c7"),
        teal: tok("--ems-teal-500", "#14b8a6"),
        success: tok("--ems-success", "#16a34a"),
        danger: tok("--ems-danger", "#dc2626"),
        warning: tok("--ems-warning-500", "#f59e0b"),
        violet: tok("--ems-violet-600", "#7c3aed"),
        muted: tok("--ems-neutral-400", "#94a3b8"),
        grid: tok("--ems-neutral-100", "#f1f5f9"),
        ink: tok("--ems-neutral-900", "#111827")
    };
    var SERIES = [C.primary, C.teal, C.success, C.sky, C.primaryDark];
    var tooltipStyle = {
        backgroundColor: C.ink,
        titleFont: { family: fontFamily, size: 13, weight: "bold" },
        bodyFont: { family: fontFamily, size: 12 },
        cornerRadius: 8, padding: 10
    };

    function getArr(k) { return Array.isArray(CD[k]) ? CD[k] : []; }
    function hasItems(v) { return Array.isArray(v) && v.length > 0; }
    function hasPositive(v) { return hasItems(v) && v.some(function(x){ return Number(x) > 0; }); }

    function showNotice(id, msg) {
        var c = document.getElementById(id);
        if (!c || !c.parentElement) return;
        var w = c.parentElement;
        w.classList.add("is-empty");
        w.textContent = "";
        var p = document.createElement("p");
        p.className = "tes-chart-empty";
        p.textContent = msg;
        w.appendChild(p);
    }

    function mkChart(id, cfg, ok, empty) {
        if (typeof window.Chart !== "function") { showNotice(id, T.chartModuleError || ""); return null; }
        if (!ok) { showNotice(id, empty); return null; }
        var c = document.getElementById(id);
        return c ? new window.Chart(c, cfg) : null;
    }

    /* Student Scores */
    var sLabels = getArr("student_labels");
    var sScores = getArr("student_scores");
    mkChart("studentScoreChart", {
        type: "bar",
        data: { labels: sLabels, datasets: [{ label: T.chartLabelScore || "", data: sScores, backgroundColor: sScores.map(function(_, i){ return SERIES[i % SERIES.length]; }), borderRadius: 6, borderSkipped: false, barPercentage: 0.7 }] },
        options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: tooltipStyle }, scales: { x: { grid: { color: C.grid } }, y: { grid: { display: false }, ticks: { font: { family: fontFamily, size: 11, weight: "bold" } } } } }
    }, hasItems(sScores), T.chartEmptyStudents || "");

    /* Question Accuracy */
    var qLabels = getArr("question_labels");
    var qAcc = getArr("question_accuracy");
    var qShort = qLabels.map(function(_, i){ return "S" + (i+1); });
    mkChart("questionAccuracyChart", {
        type: "bar",
        data: { labels: qShort, datasets: [{ label: T.chartLabelAccuracy || "", data: qAcc, backgroundColor: qAcc.map(function(v){ return v>=70?C.success:v>=40?C.sky:C.danger; }), borderRadius: 6, borderSkipped: false, barPercentage: 0.6 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: Object.assign({}, tooltipStyle, { callbacks: { title: function(items){ var idx=items[0].dataIndex; return qLabels[idx]||("Q"+(idx+1)); }, label: function(item){ return item.raw+"%"; } } }) }, scales: { y: { max: 100, grid: { color: C.grid }, ticks: { callback: function(v){return v+"%";} } }, x: { grid: { display: false } } } }
    }, hasItems(qAcc), T.chartEmptyQuestions || "");

    if (EXTRA.isWritten) {
        /* Checked / Unchecked doughnut (written exams) */
        mkChart("checkedUncheckedChart", {
            type: "doughnut",
            data: { labels: [T.chartLabelChecked || "", T.chartLabelUnchecked || ""], datasets: [{ data: [EXTRA.checkedCount, EXTRA.uncheckedCount], backgroundColor: [C.success, C.muted], borderWidth: 0, hoverOffset: 8 }] },
            options: { responsive: true, maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom", labels: { font: { family: fontFamily, size: 12, weight: "bold" }, padding: 16, usePointStyle: true } }, tooltip: tooltipStyle } }
        }, EXTRA.checkedCount + EXTRA.uncheckedCount > 0, T.chartEmptyChecked || "");
    } else {
        /* Correct / Incorrect doughnut (test exams) */
        var qC = getArr("question_correct"), qI = getArr("question_incorrect");
        var tC = qC.reduce(function(a,b){return a+b;},0), tI = qI.reduce(function(a,b){return a+b;},0);
        mkChart("correctIncorrectChart", {
            type: "doughnut",
            data: { labels: [T.chartLabelCorrect || "", T.chartLabelIncorrect || ""], datasets: [{ data: [tC, tI], backgroundColor: [C.success, C.danger], borderWidth: 0, hoverOffset: 8 }] },
            options: { responsive: true, maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom", labels: { font: { family: fontFamily, size: 12, weight: "bold" }, padding: 16, usePointStyle: true } }, tooltip: tooltipStyle } }
        }, hasPositive([tC, tI]), T.chartEmptyCorrectIncorrect || "");
    }

    /* Pass / Fail doughnut */
    mkChart("passFailChart", {
        type: "doughnut",
        data: { labels: [T.chartLabelPass || "", T.chartLabelFail || ""], datasets: [{ data: [EXTRA.passCount, EXTRA.failCount], backgroundColor: [C.success, C.danger], borderWidth: 0, hoverOffset: 8 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom", labels: { font: { family: fontFamily, size: 12, weight: "bold" }, padding: 16, usePointStyle: true } }, tooltip: tooltipStyle } }
    }, EXTRA.passCount + EXTRA.failCount > 0, T.chartEmptyPassFail || "");

    /* Score Distribution */
    var sdL = getArr("score_distribution_labels"), sdC = getArr("score_distribution_counts");
    mkChart("scoreDistributionChart", {
        type: "bar",
        data: { labels: sdL, datasets: [{ label: T.chartLabelParticipants || "", data: sdC, backgroundColor: C.teal, borderColor: C.teal, borderWidth: 1.5, borderRadius: 8, borderSkipped: false, maxBarThickness: 48 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: tooltipStyle }, scales: { y: { beginAtZero: true, grid: { color: C.grid }, ticks: { precision: 0 } }, x: { grid: { display: false } } } }
    }, hasItems(sdC), T.chartEmptyDistribution || "");

    /* Group charts */
    var gLabels = getArr("group_labels"), gAvg = getArr("group_avg_scores"), gPass = getArr("group_pass_rates");
    if (hasItems(gLabels)) {
        var gPalette = [C.primary, C.success, C.warning, C.danger, C.violet, C.teal];
        var gColors = gLabels.map(function(_, i){ return gPalette[i % gPalette.length]; });
        mkChart("groupAvgScoreChart", {
            type: "bar",
            data: { labels: gLabels, datasets: [{ label: T.chartLabelAvgScore || "", data: gAvg, backgroundColor: gColors, borderRadius: 6, borderSkipped: false }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: tooltipStyle }, scales: { y: { grid: { color: C.grid } }, x: { grid: { display: false } } } }
        }, true, "");

        mkChart("groupPassRateChart", {
            type: "bar",
            data: { labels: gLabels, datasets: [{ label: T.chartLabelPassRate || "", data: gPass, backgroundColor: gColors, borderRadius: 6, borderSkipped: false }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: tooltipStyle }, scales: { y: { max: 100, grid: { color: C.grid }, ticks: { callback: function(v){return v+"%";} } }, x: { grid: { display: false } } } }
        }, true, "");
    }

    /* Table search + pagination */
    function setupTable(tbodyId, searchId, pagId) {
        var tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        var rows = Array.prototype.slice.call(tbody.querySelectorAll("tr"));
        var searchEl = document.getElementById(searchId);
        var pagEl = document.getElementById(pagId);
        var page = 1, filtered = rows;

        function doFilter() {
            var q = (searchEl ? searchEl.value : "").trim();
            var match = searchMatcher(q);
            filtered = rows.filter(function(r){ return !q || match(r.dataset.question||r.textContent||""); });
            page = 1; render();
        }
        function render() {
            var tp = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
            if (page > tp) page = tp;
            var s = (page-1)*PAGE_SIZE, e = s+PAGE_SIZE;
            rows.forEach(function(r){r.classList.add("tes-hidden");});
            filtered.forEach(function(r,i){if(i>=s&&i<e)r.classList.remove("tes-hidden");});
            renderPag(pagEl, page, tp, filtered.length);
        }
        function pagBtn(label, aria, disabled, onClick, current) {
            var b = document.createElement("button");
            b.type = "button";
            b.textContent = label;
            if (aria) b.setAttribute("aria-label", aria);
            b.disabled = !!disabled;
            if (current) b.setAttribute("aria-current", "page");
            b.addEventListener("click", onClick);
            return b;
        }
        function renderPag(el, pg, tot, cnt) {
            if (!el) return;
            el.textContent = "";
            if (tot <= 1 && cnt <= PAGE_SIZE) return;
            el.setAttribute("role", "navigation");
            el.appendChild(pagBtn("\u2039", T.paginationPrev || "", pg <= 1, function(){ page--; render(); }));
            var ms = 7, sp = Math.max(1, pg - Math.floor(ms / 2)), ep = Math.min(tot, sp + ms - 1);
            if (ep - sp < ms - 1) sp = Math.max(1, ep - ms + 1);
            for (var i = sp; i <= ep; i++) {
                (function(p){ el.appendChild(pagBtn(String(p), null, false, function(){ page = p; render(); }, p === pg)); })(i);
            }
            var info = document.createElement("span");
            info.className = "tes-pagination__info";
            info.textContent = cnt + " " + (T.paginationResults || "");
            el.appendChild(info);
            el.appendChild(pagBtn("\u203A", T.paginationNext || "", pg >= tot, function(){ page++; render(); }));
        }
        if (searchEl) searchEl.addEventListener("input", doFilter);
        doFilter();
    }
    setupTable("questionTbody", "questionSearch", "questionPagination");

    /* AI Summary */
    var aiBtn = document.getElementById("aiSummaryBtn");
    var aiContent = document.getElementById("aiSummaryContent");
    if (aiBtn && aiContent) {
        aiBtn.addEventListener("click", function() {
            aiBtn.disabled = true;
            aiBtn.setAttribute("aria-busy", "true");
            aiContent.innerHTML = '<div class="tes-ai__loading" aria-hidden="true">' +
                '<span class="skeleton skeleton-line skeleton-line--lg"></span>' +
                '<span class="skeleton skeleton-line"></span>' +
                '<span class="skeleton skeleton-line skeleton-line--sm"></span>' +
                '</div>';

            var currentUrl = new URL(window.location.href);
            currentUrl.searchParams.set("ai_summary", "1");

            fetch(currentUrl.toString(), { headers: { "X-Requested-With": "XMLHttpRequest" } })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.ok) {
                        var quotaHtml = "";
                        if (typeof data.remaining !== "undefined") {
                            quotaHtml = '<div class="tes-ai__quota">'
                                + '<i class="fas fa-info-circle"></i> '
                                + (T.aiQuotaInfo || "") + ': '
                                + '<strong>' + escapeHtml(data.remaining) + '/' + escapeHtml(data.limit) + '</strong> (' + escapeHtml(data.window) + ')'
                                + (data.cached ? ' &middot; <span class="tes-ai__cached"><i class="fas fa-bolt" aria-hidden="true"></i> ' + (T.aiCached || "") + '</span>' : '')
                                + '</div>';
                        }
                        aiContent.innerHTML = formatMarkdown(data.summary) + quotaHtml;
                    } else {
                        aiContent.innerHTML = '<div class="tes-ai__error"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i> ' + escapeHtml(data.error || (T.aiError || "")) + '</div>';
                    }
                    aiBtn.disabled = false;
                    aiBtn.removeAttribute("aria-busy");
                })
                .catch(function() {
                    aiContent.innerHTML = '<div class="tes-ai__error"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i> ' + (T.aiError || "") + '</div>';
                    aiBtn.disabled = false;
                    aiBtn.removeAttribute("aria-busy");
                });
        });
    }

    /* 2026-09-13 təhlükəsizlik auditi, F-01 (P2): AI xülasəsi LLM çıxışıdır —
       prompt-a sual mətnləri və qrup adları daxil olduğundan dolayı prompt-
       injection ilə HTML gələ bilər. Sibling fayl (exam_center_stats_charts.js)
       kimi ƏVVƏLCƏ escape, sonra markdown → HTML. */
    function escapeHtml(s) {
        var d = document.createElement("div");
        d.textContent = (s == null ? "" : s);
        return d.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function formatMarkdown(text) {
        /* Simple markdown to HTML conversion — giriş əvvəlcə HTML-escape olunur */
        var html = escapeHtml(text)
            .replace(/### (.*)/g, '<h3>$1</h3>')
            .replace(/## (.*)/g, '<h2>$1</h2>')
            .replace(/# (.*)/g, '<h1>$1</h1>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/^- (.*)/gm, '<li>$1</li>')
            .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>');
        return '<p>' + html + '</p>';
    }
})();
