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
 */
(function () {
    "use strict";

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
    var fontFamily = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif";
    var tooltipStyle = {
        backgroundColor: "rgba(17,24,39,.92)",
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
        w.innerHTML = '<div class="sd-chart-empty">' + msg + '</div>';
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
        data: { labels: sLabels, datasets: [{ label: T.chartLabelScore || "", data: sScores, backgroundColor: sScores.map(function(_, i){ var c=["#1a56db","#0e7490","#059669","#0284c7","#2563eb"]; return c[i%c.length]; }), borderRadius: 6, borderSkipped: false, barPercentage: 0.7 }] },
        options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: tooltipStyle }, scales: { x: { grid: { color: "#f1f5f9" } }, y: { grid: { display: false }, ticks: { font: { family: fontFamily, size: 11, weight: "bold" } } } } }
    }, hasItems(sScores), T.chartEmptyStudents || "");

    /* Question Accuracy */
    var qLabels = getArr("question_labels");
    var qAcc = getArr("question_accuracy");
    var qShort = qLabels.map(function(_, i){ return "S" + (i+1); });
    mkChart("questionAccuracyChart", {
        type: "bar",
        data: { labels: qShort, datasets: [{ label: T.chartLabelAccuracy || "", data: qAcc, backgroundColor: qAcc.map(function(v){ return v>=70?"#059669":v>=40?"#0284c7":"#dc2626"; }), borderRadius: 6, borderSkipped: false, barPercentage: 0.6 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: Object.assign({}, tooltipStyle, { callbacks: { title: function(items){ var idx=items[0].dataIndex; return qLabels[idx]||("Q"+(idx+1)); }, label: function(item){ return item.raw+"%"; } } }) }, scales: { y: { max: 100, grid: { color: "#f1f5f9" }, ticks: { callback: function(v){return v+"%";} } }, x: { grid: { display: false } } } }
    }, hasItems(qAcc), T.chartEmptyQuestions || "");

    if (EXTRA.isWritten) {
        /* Checked / Unchecked doughnut (written exams) */
        mkChart("checkedUncheckedChart", {
            type: "doughnut",
            data: { labels: [T.chartLabelChecked || "", T.chartLabelUnchecked || ""], datasets: [{ data: [EXTRA.checkedCount, EXTRA.uncheckedCount], backgroundColor: ["#059669","#94a3b8"], borderWidth: 0, hoverOffset: 8 }] },
            options: { responsive: true, maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom", labels: { font: { family: fontFamily, size: 12, weight: "bold" }, padding: 16, usePointStyle: true } }, tooltip: tooltipStyle } }
        }, EXTRA.checkedCount + EXTRA.uncheckedCount > 0, T.chartEmptyChecked || "");
    } else {
        /* Correct / Incorrect doughnut (test exams) */
        var qC = getArr("question_correct"), qI = getArr("question_incorrect");
        var tC = qC.reduce(function(a,b){return a+b;},0), tI = qI.reduce(function(a,b){return a+b;},0);
        mkChart("correctIncorrectChart", {
            type: "doughnut",
            data: { labels: [T.chartLabelCorrect || "", T.chartLabelIncorrect || ""], datasets: [{ data: [tC, tI], backgroundColor: ["#059669","#dc2626"], borderWidth: 0, hoverOffset: 8 }] },
            options: { responsive: true, maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom", labels: { font: { family: fontFamily, size: 12, weight: "bold" }, padding: 16, usePointStyle: true } }, tooltip: tooltipStyle } }
        }, hasPositive([tC, tI]), T.chartEmptyCorrectIncorrect || "");
    }

    /* Pass / Fail doughnut */
    mkChart("passFailChart", {
        type: "doughnut",
        data: { labels: [T.chartLabelPass || "", T.chartLabelFail || ""], datasets: [{ data: [EXTRA.passCount, EXTRA.failCount], backgroundColor: ["#059669","#dc2626"], borderWidth: 0, hoverOffset: 8 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom", labels: { font: { family: fontFamily, size: 12, weight: "bold" }, padding: 16, usePointStyle: true } }, tooltip: tooltipStyle } }
    }, EXTRA.passCount + EXTRA.failCount > 0, T.chartEmptyPassFail || "");

    /* Score Distribution */
    var sdL = getArr("score_distribution_labels"), sdC = getArr("score_distribution_counts");
    mkChart("scoreDistributionChart", {
        type: "bar",
        data: { labels: sdL, datasets: [{ label: T.chartLabelParticipants || "", data: sdC, backgroundColor: "rgba(14,116,144,.82)", borderColor: "#0e7490", borderWidth: 1.5, borderRadius: 8, borderSkipped: false, maxBarThickness: 48 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: tooltipStyle }, scales: { y: { beginAtZero: true, grid: { color: "#f1f5f9" }, ticks: { precision: 0 } }, x: { grid: { display: false } } } }
    }, hasItems(sdC), T.chartEmptyDistribution || "");

    /* Group charts */
    var gLabels = getArr("group_labels"), gAvg = getArr("group_avg_scores"), gPass = getArr("group_pass_rates");
    if (hasItems(gLabels)) {
        var gColors = gLabels.map(function(_, i){ var c=["#1a56db","#059669","#d97706","#dc2626","#7c3aed","#0e7490"]; return c[i%c.length]; });
        mkChart("groupAvgScoreChart", {
            type: "bar",
            data: { labels: gLabels, datasets: [{ label: T.chartLabelAvgScore || "", data: gAvg, backgroundColor: gColors, borderRadius: 6, borderSkipped: false }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: tooltipStyle }, scales: { y: { grid: { color: "#f1f5f9" } }, x: { grid: { display: false } } } }
        }, true, "");

        mkChart("groupPassRateChart", {
            type: "bar",
            data: { labels: gLabels, datasets: [{ label: T.chartLabelPassRate || "", data: gPass, backgroundColor: gColors, borderRadius: 6, borderSkipped: false }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: tooltipStyle }, scales: { y: { max: 100, grid: { color: "#f1f5f9" }, ticks: { callback: function(v){return v+"%";} } }, x: { grid: { display: false } } } }
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
            var q = (searchEl ? searchEl.value : "").toLowerCase().trim();
            filtered = rows.filter(function(r){ return !q || (r.dataset.question||r.textContent||"").toLowerCase().indexOf(q)!==-1; });
            page = 1; render();
        }
        function render() {
            var tp = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
            if (page > tp) page = tp;
            var s = (page-1)*PAGE_SIZE, e = s+PAGE_SIZE;
            rows.forEach(function(r){r.classList.add("sd-hidden");});
            filtered.forEach(function(r,i){if(i>=s&&i<e)r.classList.remove("sd-hidden");});
            renderPag(pagEl, page, tp, filtered.length);
        }
        function renderPag(el, pg, tot, cnt) {
            if (!el) return; el.innerHTML = "";
            if (tot<=1 && cnt<=PAGE_SIZE) return;
            var prev = document.createElement("button"); prev.textContent="‹"; prev.disabled=pg<=1; prev.onclick=function(){page--;render();}; el.appendChild(prev);
            var ms=7,sp=Math.max(1,pg-Math.floor(ms/2)),ep=Math.min(tot,sp+ms-1);
            if(ep-sp<ms-1) sp=Math.max(1,ep-ms+1);
            for(var i=sp;i<=ep;i++){var b=document.createElement("button");b.textContent=i;if(i===pg)b.className="is-active";(function(p){b.onclick=function(){page=p;render();};})(i);el.appendChild(b);}
            var info=document.createElement("span");info.className="sd-pagination__info";info.textContent=cnt+" "+(T.paginationResults || "");el.appendChild(info);
            var nx=document.createElement("button");nx.textContent="›";nx.disabled=pg>=tot;nx.onclick=function(){page++;render();};el.appendChild(nx);
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
            aiContent.innerHTML = '<div class="sd-ai-loading" aria-hidden="true">' +
                '<div style="display:flex;flex-direction:column;gap:.5rem;width:100%">' +
                '<span class="skeleton skeleton-line skeleton-line--lg"></span>' +
                '<span class="skeleton skeleton-line"></span>' +
                '<span class="skeleton skeleton-line skeleton-line--sm"></span>' +
                '</div></div>';

            var currentUrl = new URL(window.location.href);
            currentUrl.searchParams.set("ai_summary", "1");

            fetch(currentUrl.toString(), { headers: { "X-Requested-With": "XMLHttpRequest" } })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.ok) {
                        var quotaHtml = "";
                        if (typeof data.remaining !== "undefined") {
                            quotaHtml = '<div class="sd-ai-quota sd-ai-quota-box">'
                                + '<i class="fas fa-info-circle"></i> '
                                + (T.aiQuotaInfo || "") + ': '
                                + '<strong>' + data.remaining + '/' + data.limit + '</strong> (' + data.window + ')'
                                + (data.cached ? ' &middot; <span><i class="fas fa-bolt sd-ai-cached-bolt"></i> ' + (T.aiCached || "") + '</span>' : '')
                                + '</div>';
                        }
                        aiContent.innerHTML = formatMarkdown(data.summary) + quotaHtml;
                    } else {
                        aiContent.innerHTML = '<div class="sd-ai-error"><i class="fas fa-exclamation-triangle"></i> ' + (data.error || (T.aiError || "")) + '</div>';
                    }
                    aiBtn.disabled = false;
                })
                .catch(function() {
                    aiContent.innerHTML = '<div class="sd-ai-error"><i class="fas fa-exclamation-triangle"></i> ' + (T.aiError || "") + '</div>';
                    aiBtn.disabled = false;
                });
        });
    }

    function formatMarkdown(text) {
        /* Simple markdown to HTML conversion */
        var html = text
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
