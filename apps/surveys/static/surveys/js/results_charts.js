/* =========================================================================
   results_charts.js — «Sorğu nəticələri» qrafik qurucuları (EMSSurveyResults.charts)

   Formalar (dataviz qaydaları): orta bal — üfüqi zolaq + müqayisə İŞARƏLƏRİ
   (universitet/kafedra); Likert — DIVERGING 100% zolaq, neytral «3» mərkəzdə,
   kənarlarda cəm «razı deyil»/«razı» payı; paylanma — sütun histoqramı; dinamika
   — xətt (BİR ox; göstərici açarı ilə); müqayisə — üfüqi zolaq + universitet
   xətti. İncə işarələr (≤ 20px zolaq, 4px yuvarlaq uc, 2px xətt, ≥ 8px nöqtə),
   seqmentlər arasında 2px fon boşluğu, sərhəd xətti yox.

   Nüvəyə (`results_core.js`) YALNIZ çağırış anında müraciət olunur — AJAX
   swap-da skriptlərin icra sırası zəmanətli deyil.
   ========================================================================= */
(function (window, document) {
    "use strict";

    var NS = (window.EMSSurveyResults = window.EMSSurveyResults || {});
    if (NS.charts) {
        return;
    }

    function neg(value) {
        return -(value || 0);
    }

    function questions(canvas, block, t, pal, Chart, C) {
        if (!block || !block.labels || !block.labels.length) {
            return;
        }
        var datasets = [
            {
                type: "bar",
                label: canvas.closest("[data-svr-series]") ? canvas.closest("[data-svr-series]").dataset.svrSeries : t.i18nSelection,
                data: block.values,
                backgroundColor: pal.c1,
                hoverBackgroundColor: pal.c1,
                borderRadius: 4,
                borderSkipped: "start",
                maxBarThickness: 18,
                order: 3
            }
        ];
        function refs(values, color, label) {
            if (values && values.some(C.isNum)) {
                datasets.push({
                    type: "line",
                    label: label,
                    data: values,
                    showLine: false,
                    pointStyle: "line",
                    pointRotation: 90,
                    pointRadius: 9,
                    pointHoverRadius: 10,
                    pointBorderWidth: 3,
                    pointHitRadius: 12,
                    borderColor: color,
                    backgroundColor: color,
                    order: 1
                });
            }
        }
        refs(block.department, pal.c2, t.i18nDepartment);
        refs(block.org, pal.ref, t.i18nOrg);
        C.sizeRows(canvas.parentElement, block.labels.length, 30, 48);
        C.mount(canvas, Chart, {
            type: "bar",
            data: { labels: block.labels, datasets: datasets },
            options: C.base(pal, {
                indexAxis: "y",
                scales: {
                    x: C.axis(pal, { min: 1, max: 5, ticks: { stepSize: 1 } }),
                    y: C.axis(pal, { grid: { display: false }, ticks: { autoSkip: false, callback: C.tickCallback(30) } })
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function (ctx) {
                                return ctx.dataset.label + ": " + C.fmt(ctx.parsed.x);
                            }
                        }
                    }
                }
            })
        });
    }

    function likert(canvas, block, t, pal, Chart, C) {
        if (!block || !block.labels || !block.labels.length) {
            return;
        }
        // Yalnız tam faizlər gəlir (xam say sızmasın — analytics_guard).
        var rows = block.pct || [];
        var scale = block.scale || ["1", "2", "3", "4", "5"];
        function share(index) {
            return rows.map(function (row) {
                return row[index] || 0;
            });
        }
        var half = rows.map(function (row) {
            return (row[2] || 0) / 2;
        });
        function ds(score, values, color) {
            return {
                label: scale[score - 1],
                data: values,
                backgroundColor: color,
                hoverBackgroundColor: color,
                borderColor: pal.surface,
                borderWidth: { left: 1, right: 1, top: 0, bottom: 0 },
                borderSkipped: false,
                maxBarThickness: 20,
                stack: "likert",
                svrScore: score
            };
        }
        // Mənfi tərəf sıfırdan sola yığılır: neytralın yarısı → 2 → 1; müsbət: yarı → 4 → 5.
        var datasets = [
            ds(3, half.map(neg), pal.likert[2]),
            ds(2, share(1).map(neg), pal.likert[1]),
            ds(1, share(0).map(neg), pal.likert[0]),
            ds(3, half, pal.likert[2]),
            ds(4, share(3), pal.likert[3]),
            ds(5, share(4), pal.likert[4])
        ];
        var left = rows.map(function (row) {
            return (row[0] || 0) + (row[1] || 0) + (row[2] || 0) / 2;
        });
        var right = rows.map(function (row) {
            return (row[2] || 0) / 2 + (row[3] || 0) + (row[4] || 0);
        });
        var reach = Math.min(100, Math.max(50, Math.ceil(Math.max.apply(null, left.concat(right, [0])) / 25) * 25));
        var endLabels = {
            id: "svrEndLabels",
            afterDatasetsDraw: function (chart) {
                var ctx = chart.ctx;
                var x = chart.scales.x;
                var y = chart.scales.y;
                ctx.save();
                ctx.font = "600 11px " + pal.font;
                ctx.fillStyle = pal.axis;
                ctx.textBaseline = "middle";
                rows.forEach(function (row, index) {
                    var py = y.getPixelForValue(index);
                    ctx.textAlign = "right";
                    ctx.fillText(C.fmt((row[0] || 0) + (row[1] || 0), 0) + "%", x.getPixelForValue(-left[index]) - 6, py);
                    ctx.textAlign = "left";
                    ctx.fillText(C.fmt((row[3] || 0) + (row[4] || 0), 0) + "%", x.getPixelForValue(right[index]) + 6, py);
                });
                ctx.restore();
            }
        };
        C.sizeRows(canvas.parentElement, block.labels.length, 30, 48);
        C.mount(canvas, Chart, {
            type: "bar",
            data: { labels: block.labels, datasets: datasets },
            plugins: [endLabels],
            options: C.base(pal, {
                indexAxis: "y",
                layout: { padding: { left: 36, right: 36 } },
                scales: {
                    x: C.axis(pal, {
                        stacked: true,
                        min: -reach,
                        max: reach,
                        grid: {
                            color: function (ctx) {
                                return ctx.tick && ctx.tick.value === 0 ? pal.axis : pal.grid;
                            }
                        },
                        ticks: {
                            stepSize: 25,
                            callback: function (value) {
                                return Math.abs(value) + "%";
                            }
                        }
                    }),
                    y: C.axis(pal, { stacked: true, grid: { display: false }, ticks: { autoSkip: false, callback: C.tickCallback(30) } })
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function (ctx) {
                                var score = ctx.dataset.svrScore;
                                var pct = (rows[ctx.dataIndex] || [])[score - 1] || 0;
                                return score + " — " + ctx.dataset.label + ": " + C.fmt(pct, 0) + "%";
                            }
                        }
                    }
                }
            })
        });
    }

    function histogram(canvas, block, t, pal, Chart, C) {
        if (!block || !block.scores) {
            return;
        }
        C.mount(canvas, Chart, {
            type: "bar",
            data: {
                labels: block.scores.map(String),
                datasets: [
                    {
                        label: t.i18nShare,
                        data: block.pct,
                        backgroundColor: pal.c1,
                        hoverBackgroundColor: pal.c1,
                        borderRadius: 4,
                        borderSkipped: "start",
                        maxBarThickness: 24
                    }
                ]
            },
            options: C.base(pal, {
                scales: {
                    x: C.axis(pal, { grid: { display: false }, title: { display: true, text: t.i18nScore, color: pal.axis } }),
                    y: C.axis(pal, {
                        beginAtZero: true,
                        ticks: {
                            precision: 0,
                            callback: function (value) {
                                return value + "%";
                            }
                        }
                    })
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            title: function (items) {
                                return t.i18nScore + ": " + items[0].label;
                            },
                            label: function (ctx) {
                                return t.i18nShare + ": " + C.fmt(ctx.parsed.y, 0) + "%";
                            }
                        }
                    }
                }
            })
        });
    }

    function trend(canvas, block, t, pal, Chart, C, metric) {
        if (!block || !block.labels || !block.labels.length) {
            return;
        }
        var colors = { selection: pal.c1, department: pal.c2, org: pal.ctx };
        var datasets = block.series.map(function (series) {
            var color = colors[series.key] || pal.c3;
            return {
                label: series.label,
                data: metric === "index" ? series.index : series.overall,
                borderColor: color,
                backgroundColor: color,
                borderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6,
                pointBorderColor: pal.surface,
                pointBorderWidth: 2,
                tension: 0.25,
                spanGaps: false,
                svrN: series.n || []
            };
        });
        C.mount(canvas, Chart, {
            type: "line",
            data: { labels: block.labels, datasets: datasets },
            options: C.base(pal, {
                interaction: { mode: "index", intersect: false },
                scales: {
                    x: C.axis(pal, { grid: { display: false }, ticks: { callback: C.tickCallback(18) } }),
                    y: C.axis(pal, { min: 1, max: metric === "index" ? 5 : 10 })
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function (ctx) {
                                var value = ctx.parsed.y;
                                var n = ctx.dataset.svrN[ctx.dataIndex];
                                if (!C.isNum(value)) {
                                    return ctx.dataset.label + ": " + t.i18nHidden;
                                }
                                return ctx.dataset.label + ": " + C.fmt(value) + (n ? " (n: " + n + ")" : "");
                            }
                        }
                    }
                }
            })
        });
    }

    function referenceLine(value, label, pal, C) {
        return {
            id: "svrReference",
            afterDatasetsDraw: function (chart) {
                if (!C.isNum(value)) {
                    return;
                }
                var ctx = chart.ctx;
                var area = chart.chartArea;
                var px = chart.scales.x.getPixelForValue(value);
                ctx.save();
                ctx.strokeStyle = pal.ref;
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.moveTo(px, area.top);
                ctx.lineTo(px, area.bottom);
                ctx.stroke();
                ctx.fillStyle = pal.axis;
                ctx.font = "600 11px " + pal.font;
                ctx.textAlign = "center";
                ctx.fillText(label + " " + C.fmt(value), px, area.top - 6);
                ctx.restore();
            }
        };
    }

    function bars(canvas, series, t, pal, Chart, C, opts) {
        C.sizeRows(canvas.parentElement, series.labels.length, series.datasets.length > 1 ? 40 : 28, 60);
        C.mount(canvas, Chart, {
            type: "bar",
            data: {
                labels: series.labels,
                datasets: series.datasets.map(function (item) {
                    return {
                        label: item.label,
                        data: item.values,
                        backgroundColor: item.color,
                        hoverBackgroundColor: item.color,
                        borderRadius: 4,
                        borderSkipped: "start",
                        maxBarThickness: 16,
                        svrN: series.n || []
                    };
                })
            },
            plugins: opts.reference !== undefined ? [referenceLine(opts.reference, t.i18nOrg, pal, C)] : [],
            options: C.base(pal, {
                indexAxis: "y",
                layout: { padding: { top: 14 } },
                scales: {
                    x: C.axis(pal, { min: 1, max: opts.max }),
                    y: C.axis(pal, { grid: { display: false }, ticks: { autoSkip: false, callback: C.tickCallback(34) } })
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function (ctx) {
                                return ctx.dataset.label + ": " + C.fmt(ctx.parsed.x);
                            },
                            afterBody: function (items) {
                                var n = (series.n || [])[items[0].dataIndex];
                                return n ? t.i18nN + ": " + n : "";
                            }
                        }
                    }
                }
            })
        });
    }

    function showHiddenNote(wrap, hidden, t) {
        var card = wrap.closest(".svr-card");
        var note = card ? card.querySelector("[data-svr-breakdown-hidden], [data-svr-levels-hidden]") : null;
        if (note) {
            note.hidden = !hidden;
            note.textContent = hidden ? hidden + " " + (t.i18nHiddenGroups || "") : "";
        }
    }

    function syncLevelTables(card, level) {
        if (!card) {
            return;
        }
        card.querySelectorAll("[data-svr-level-table]").forEach(function (table) {
            table.hidden = table.getAttribute("data-svr-level-table") !== level;
        });
        card.querySelectorAll("[data-svr-level]").forEach(function (button) {
            button.setAttribute("aria-pressed", button.getAttribute("data-svr-level") === level ? "true" : "false");
        });
    }

    var RENDERERS = {
        questions: function (canvas, data, t, pal, Chart, C) {
            questions(canvas, data.questions, t, pal, Chart, C);
        },
        likert: function (canvas, data, t, pal, Chart, C) {
            likert(canvas, data.likert, t, pal, Chart, C);
        },
        histogram: function (canvas, data, t, pal, Chart, C) {
            histogram(canvas, data.histogram, t, pal, Chart, C);
        },
        trend: function (canvas, data, t, pal, Chart, C, wrap) {
            trend(canvas, data.trend, t, pal, Chart, C, wrap.dataset.metric || "overall");
        },
        breakdown: function (canvas, data, t, pal, Chart, C, wrap) {
            var card = wrap.closest("[data-svr-breakdown]");
            var info = data.breakdown || {};
            var level = wrap.dataset.level || (card && card.dataset.default) || info["default"] || "faculty";
            var block = info[level] || { labels: [], values: [], n: [], hidden: 0 };
            syncLevelTables(card, level);
            showHiddenNote(wrap, block.hidden, t);
            bars(canvas, { labels: block.labels, n: block.n, datasets: [{ label: t.i18nOverall, values: block.values, color: pal.c1 }] }, t, pal, Chart, C, {
                max: 10,
                reference: info.org_avg === null ? undefined : info.org_avg
            });
        },
        levels: function (canvas, data, t, pal, Chart, C, wrap) {
            var card = wrap.closest("[data-svr-levels]");
            var levels = data.levels || {};
            var level = wrap.dataset.level || (card && card.dataset.default) || data.level_default || "faculty";
            var block = levels[level] || { labels: [], satisfaction: [], facilities: [], n: [], hidden: 0 };
            syncLevelTables(card, level);
            showHiddenNote(wrap, block.hidden, t);
            bars(canvas, {
                labels: block.labels,
                n: block.n,
                datasets: [
                    { label: t.i18nSatisfaction, values: block.satisfaction, color: pal.c1 },
                    { label: t.i18nFacilities, values: block.facilities, color: pal.c2 }
                ]
            }, t, pal, Chart, C, { max: 5 });
        }
    };

    /** Konteynerdəki bütün `[data-svr-chart]` qrafiklərini JSON adasından çəkir. */
    function render(container, only) {
        var C = NS.core;
        if (!C || !container) {
            return;
        }
        var scope = container.closest("[data-svr-root], .svr-detail") || document;
        var data = C.readIsland(container.getAttribute("data-svr-charts"), scope);
        if (!data) {
            return;
        }
        C.withChart(container, function (Chart) {
            var t = C.labels(container);
            var pal = C.palette(container);
            container.querySelectorAll("[data-svr-chart]").forEach(function (wrap) {
                var kind = wrap.getAttribute("data-svr-chart");
                if ((only && kind !== only) || !RENDERERS[kind]) {
                    return;
                }
                try {
                    RENDERERS[kind](wrap.querySelector("canvas"), data, t, pal, Chart, C, wrap);
                } catch (err) {
                    if (window.console) {
                        window.console.error("svr chart " + kind + ":", err);
                    }
                }
            });
        });
    }

    function containerOf(node) {
        return node.closest("[data-svr-charts]");
    }

    /* Göstərici / səviyyə açarları — yalnız həmin qrafik yenidən çəkilir. */
    window.EMSDelegate.on("click", "[data-svr-trend-metric]", function (event, button) {
        var card = button.closest(".svr-card");
        var wrap = card ? card.querySelector('[data-svr-chart="trend"]') : null;
        if (!wrap) {
            return;
        }
        wrap.dataset.metric = button.getAttribute("data-svr-trend-metric");
        card.querySelectorAll("[data-svr-trend-metric]").forEach(function (other) {
            other.setAttribute("aria-pressed", other === button ? "true" : "false");
        });
        render(containerOf(card), "trend");
    });

    window.EMSDelegate.on("click", "[data-svr-level]", function (event, button) {
        var card = button.closest("[data-svr-breakdown], [data-svr-levels]");
        var wrap = card ? card.querySelector('[data-svr-chart="breakdown"], [data-svr-chart="levels"]') : null;
        if (!wrap) {
            return;
        }
        wrap.dataset.level = button.getAttribute("data-svr-level");
        render(containerOf(card), wrap.getAttribute("data-svr-chart"));
    });

    NS.charts = { render: render };
})(window, document);
