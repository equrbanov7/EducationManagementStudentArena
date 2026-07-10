/* İmtahan mərkəzi statistikası — qrafiklər + AI analiz.
   Kontrakt: bölmə şablonundakı cədvəl skripti hər yükləmədə document üzərinə
   "ecs:filters" hadisəsi göndərir (detail.query = cari filtr query-si);
   bu modul həmin query ilə /center/stats/charts/ endpointindən aqreqatları
   çəkib Chart.js ilə render edir. Profil SPA panel-swap zamanı skript yenidən
   icra olunur — boot() data-atribut guard ilə idempotentdir. */
(function () {
    "use strict";

    var PALETTE = ["#2563eb", "#0e7490", "#059669", "#d97706", "#7c3aed", "#dc2626", "#0284c7", "#64748b"];
    var FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif";

    function tooltipStyle() {
        return {
            backgroundColor: "rgba(15,23,42,.92)",
            titleFont: { family: FONT, size: 13, weight: "bold" },
            bodyFont: { family: FONT, size: 12 },
            cornerRadius: 8,
            padding: 10
        };
    }

    function escapeHtml(s) {
        var d = document.createElement("div");
        d.textContent = (s == null ? "" : s);
        return d.innerHTML;
    }

    /* Sadə markdown → HTML (AI cavabı üçün); əvvəlcə HTML escape olunur. */
    function formatMarkdown(text) {
        var html = escapeHtml(text)
            .replace(/### (.*)/g, "<h4>$1</h4>")
            .replace(/## (.*)/g, "<h3>$1</h3>")
            .replace(/# (.*)/g, "<h3>$1</h3>")
            .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
            .replace(/\*(.*?)\*/g, "<em>$1</em>")
            .replace(/^[-•] (.*)/gm, "<li>$1</li>")
            .replace(/(<li>[\s\S]*<\/li>)/, "<ul>$1</ul>")
            .replace(/\n\n/g, "</p><p>")
            .replace(/\n/g, "<br>");
        return "<p>" + html + "</p>";
    }

    function initRoot(root) {
        var T = {};
        try { T = JSON.parse(root.querySelector(".js-ecs-i18n").textContent); } catch (e) { T = {}; }
        var chartsUrl = root.dataset.chartsUrl;
        var aiUrl = root.dataset.aiUrl;
        var charts = {};
        var lastQuery = null;
        var fetchSeq = 0;

        function cleanQuery(raw) {
            var p = new URLSearchParams(raw || "");
            p.delete("page");
            p.delete("sort");
            if (typeof p.sort === "function") { p.sort(); }
            return p.toString();
        }

        /* Chart.js profil səhifəsinin sonunda yüklənir — ilk render onu gözləyə bilər. */
        function whenChartReady(cb, tries) {
            if (typeof window.Chart === "function") { cb(); return; }
            if ((tries || 0) > 50) { return; }
            setTimeout(function () { whenChartReady(cb, (tries || 0) + 1); }, 120);
        }

        function setEmpty(canvas, on) {
            var wrap = canvas.parentElement;
            var msg = wrap.querySelector(".ecs-chartbox__empty");
            if (on && !msg) {
                msg = document.createElement("div");
                msg.className = "ecs-chartbox__empty";
                msg.textContent = T.empty || "—";
                wrap.appendChild(msg);
            }
            if (!on && msg) { msg.remove(); }
            canvas.style.display = on ? "none" : "";
        }

        function mk(key, sel, cfg, hasData) {
            var canvas = root.querySelector(sel);
            if (!canvas) { return; }
            if (charts[key]) { charts[key].destroy(); delete charts[key]; }
            setEmpty(canvas, !hasData);
            if (!hasData) { return; }
            charts[key] = new window.Chart(canvas, cfg);
        }

        function hasPositive(arr) {
            return Array.isArray(arr) && arr.some(function (v) { return Number(v) > 0; });
        }

        function render(d) {
            var tip = tooltipStyle();

            /* 1. Nəticə paylanması (faiz zolaqları) */
            var dist = d.distribution || { labels: [], counts: [] };
            mk("dist", ".js-ecs-c-dist", {
                type: "bar",
                data: {
                    labels: dist.labels,
                    datasets: [{
                        label: T.attempts || "",
                        data: dist.counts,
                        backgroundColor: dist.labels.map(function (_, i) {
                            return i < 5 ? "rgba(220,38,38,.72)" : (i < 7 ? "rgba(217,119,6,.75)" : "rgba(5,150,105,.8)");
                        }),
                        borderRadius: 6,
                        borderSkipped: false,
                        maxBarThickness: 46
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false }, tooltip: tip },
                    scales: {
                        y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "#f1f5f9" } },
                        x: { grid: { display: false }, ticks: { font: { family: FONT, size: 11 } } }
                    }
                }
            }, hasPositive(dist.counts));

            /* 2. Aylıq dinamika — cəhd sayı (bar) + orta faiz (xətt) */
            var m = d.monthly || { labels: [], counts: [], avg: [] };
            mk("monthly", ".js-ecs-c-monthly", {
                type: "bar",
                data: {
                    labels: m.labels,
                    datasets: [
                        {
                            type: "bar", label: T.attempts || "", data: m.counts,
                            backgroundColor: "rgba(37,99,235,.72)", borderRadius: 6,
                            yAxisID: "y", maxBarThickness: 34
                        },
                        {
                            type: "line", label: T.avg || "", data: m.avg,
                            borderColor: "#059669", backgroundColor: "#059669",
                            tension: 0.3, spanGaps: true, yAxisID: "y1", pointRadius: 3
                        }
                    ]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: {
                        legend: { position: "bottom", labels: { font: { family: FONT, size: 12 }, usePointStyle: true } },
                        tooltip: tip
                    },
                    scales: {
                        y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "#f1f5f9" } },
                        y1: {
                            position: "right", min: 0, max: 100,
                            grid: { drawOnChartArea: false },
                            ticks: { callback: function (v) { return v + "%"; } }
                        },
                        x: { grid: { display: false } }
                    }
                }
            }, hasPositive(m.counts));

            /* 3. İmtahan tipi üzrə cəhdlər (doughnut) */
            var bt = d.by_type || { labels: [], counts: [], avg: [] };
            mk("type", ".js-ecs-c-type", {
                type: "doughnut",
                data: {
                    labels: bt.labels,
                    datasets: [{
                        data: bt.counts,
                        backgroundColor: bt.labels.map(function (_, i) { return PALETTE[i % PALETTE.length]; }),
                        borderWidth: 0, hoverOffset: 8
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false, cutout: "62%",
                    plugins: {
                        legend: { position: "bottom", labels: { font: { family: FONT, size: 12 }, padding: 14, usePointStyle: true } },
                        tooltip: Object.assign({}, tip, {
                            callbacks: {
                                label: function (item) {
                                    var base = item.label + ": " + item.raw;
                                    var avg = bt.avg[item.dataIndex];
                                    return (avg == null) ? base : base + " · " + (T.avg || "") + ": " + avg + "%";
                                }
                            }
                        })
                    }
                }
            }, hasPositive(bt.counts));

            /* 4. Fənn üzrə orta nəticə (üfüqi bar, top-10) */
            var bs = d.by_subject || { labels: [], counts: [], avg: [] };
            var bsData = bs.avg.map(function (v) { return v == null ? 0 : v; });
            mk("subject", ".js-ecs-c-subject", {
                type: "bar",
                data: {
                    labels: bs.labels,
                    datasets: [{
                        label: T.avg || "", data: bsData,
                        backgroundColor: bsData.map(function (v) {
                            return v >= 70 ? "rgba(5,150,105,.8)" : (v >= 50 ? "rgba(2,132,199,.8)" : "rgba(220,38,38,.72)");
                        }),
                        borderRadius: 6, borderSkipped: false, maxBarThickness: 26
                    }]
                },
                options: {
                    indexAxis: "y", responsive: true, maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: Object.assign({}, tip, {
                            callbacks: {
                                label: function (item) {
                                    var avg = bs.avg[item.dataIndex];
                                    var pctPart = (avg == null) ? "—" : avg + "%";
                                    return (T.avg || "") + ": " + pctPart + " · " + (T.attempts || "") + ": " + bs.counts[item.dataIndex];
                                }
                            }
                        })
                    },
                    scales: {
                        x: { min: 0, max: 100, grid: { color: "#f1f5f9" }, ticks: { callback: function (v) { return v + "%"; } } },
                        y: { grid: { display: false }, ticks: { font: { family: FONT, size: 11 }, autoSkip: false } }
                    }
                }
            }, bs.labels.length > 0);

            /* 5. Keçmə nisbəti (doughnut) */
            var pf = d.pass_fail || { pass: 0, fail: 0, threshold: 50 };
            mk("pass", ".js-ecs-c-pass", {
                type: "doughnut",
                data: {
                    labels: [
                        (T.pass || "") + " (" + pf.threshold + "%+)",
                        T.fail || ""
                    ],
                    datasets: [{ data: [pf.pass, pf.fail], backgroundColor: ["#059669", "#dc2626"], borderWidth: 0, hoverOffset: 8 }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false, cutout: "62%",
                    plugins: {
                        legend: { position: "bottom", labels: { font: { family: FONT, size: 12 }, padding: 14, usePointStyle: true } },
                        tooltip: tip
                    }
                }
            }, (pf.pass + pf.fail) > 0);
        }

        function refresh(rawQuery) {
            var q = cleanQuery(rawQuery);
            if (q === lastQuery) { return; }
            lastQuery = q;
            var seq = ++fetchSeq;
            fetch(chartsUrl + (q ? "?" + q : ""), { headers: { "X-Requested-With": "XMLHttpRequest" } })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (d) {
                    if (!d || seq !== fetchSeq) { return; }
                    whenChartReady(function () { if (seq === fetchSeq) { render(d); } });
                })
                .catch(function () { /* fail-soft: köhnə qrafiklər qalır */ });
        }

        /* AI analiz düyməsi */
        var aiBtn = root.querySelector(".js-ecs-ai-btn");
        var aiOut = root.querySelector(".js-ecs-ai-out");
        if (aiBtn && aiOut) {
            aiBtn.addEventListener("click", function () {
                aiBtn.disabled = true;
                aiOut.innerHTML = '<div class="ecs-ai__loading"><i class="fas fa-spinner fa-spin"></i> ' + escapeHtml(T.ai_loading || "…") + "</div>";
                fetch(aiUrl + (lastQuery ? "?" + lastQuery : ""), { headers: { "X-Requested-With": "XMLHttpRequest" } })
                    .then(function (r) { return r.json(); })
                    .then(function (d) {
                        if (d && d.ok) {
                            var quota = "";
                            if (typeof d.remaining !== "undefined") {
                                quota = '<div class="ecs-ai__quota"><i class="fas fa-info-circle"></i> '
                                    + escapeHtml(T.ai_quota || "") + ": <strong>" + d.remaining + "/" + d.limit + "</strong> (" + escapeHtml(d.window || "") + ")"
                                    + (d.cached ? ' · <span class="ecs-ai__cached"><i class="fas fa-bolt"></i> ' + escapeHtml(T.ai_cached || "") + "</span>" : "")
                                    + "</div>";
                            }
                            aiOut.innerHTML = '<div class="ecs-ai__text">' + formatMarkdown(d.summary) + "</div>" + quota;
                        } else {
                            aiOut.innerHTML = '<div class="ecs-ai__error"><i class="fas fa-exclamation-triangle"></i> '
                                + escapeHtml((d && d.error) || T.ai_error || "") + "</div>";
                        }
                    })
                    .catch(function () {
                        aiOut.innerHTML = '<div class="ecs-ai__error"><i class="fas fa-exclamation-triangle"></i> ' + escapeHtml(T.ai_error || "") + "</div>";
                    })
                    .then(function () { aiBtn.disabled = false; });
            });
        }

        /* Cədvəl skriptinin filtr hadisələri; panel dəyişəndə köhnə listener özünü söndürür. */
        var onFilters = function (e) {
            if (!root.isConnected) { document.removeEventListener("ecs:filters", onFilters); return; }
            refresh(e && e.detail ? e.detail.query : "");
        };
        document.addEventListener("ecs:filters", onFilters);
        refresh("");
    }

    function boot() {
        var roots = document.querySelectorAll(".js-ecs-charts");
        Array.prototype.forEach.call(roots, function (root) {
            if (root.dataset.ecsChartsInit === "1") { return; }
            root.dataset.ecsChartsInit = "1";
            initRoot(root);
        });
    }

    boot();
})();
