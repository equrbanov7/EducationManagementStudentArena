/* «Müəllimlər» / «Tələbələr» kataloqunun ANALİTİKASI — göstəricilər, qrafiklər, AI.
 *
 * Naxış: `_appeal_stats` ilə eyni — AYRICA `data-charts-url` endpoint-i +
 * `<canvas>` + Chart.js. Yeni maşınalıq icad edilmir.
 *
 * FİLTRƏ TABEDİR: `people_directory.js` hər yüklənmədə `people:filters`
 * hadisəsini göndərir (və son sətri `dataset.peopleFilterQuery`-yə yazır), bu
 * modul isə həmin sətirlə analitikanı yenidən çəkir. Səhifə keçidi analitikanı
 * YENİLƏMİR (filtr sətri dəyişmir) — lüzumsuz aqreqat sorğusu getmir.
 *
 * a11y: hər qrafikin altında AÇILAN cədvəl qarşılığı qurulur; məlumat yalnız
 * rənglə verilmir. Rənglər CSS-dəki `--pan-c*` dəyişənlərindən oxunur (onlar
 * mövcud `--ems-*` tokenlərinə bağlıdır) — JS-də sabit rəng icad edilmir.
 *
 * AJAX-safe: `EMSReady` + idempotent boot. İnline stil/script YOXDUR (CSP).
 */
(function () {
    "use strict";

    var PALETTE_VARS = [
        "--pan-c1",
        "--pan-c2",
        "--pan-c3",
        "--pan-c4",
        "--pan-c5",
        "--pan-c6",
        "--pan-c7",
        "--pan-c8"
    ];

    function palette(node) {
        var styles = window.getComputedStyle(node);
        var colors = [];
        PALETTE_VARS.forEach(function (name) {
            var value = (styles.getPropertyValue(name) || "").trim();
            if (value) {
                colors.push(value);
            }
        });
        return colors.length ? colors : ["#2563eb"];
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null) {
            node.textContent = String(text);
        }
        return node;
    }

    function percentOf(count, total) {
        return total ? Math.round((count * 1000) / total) / 10 : 0;
    }

    function whenChart(callback) {
        if (typeof window.Chart === "function") {
            callback();
            return;
        }
        var attempts = 0;
        var timer = window.setInterval(function () {
            if (typeof window.Chart === "function" || attempts > 50) {
                window.clearInterval(timer);
                if (typeof window.Chart === "function") {
                    callback();
                }
            }
            attempts += 1;
        }, 100);
    }

    var MAX_TICK = 26;

    function truncateTick(value) {
        var label = this.getLabelForValue ? this.getLabelForValue(value) : String(value);
        return label.length > MAX_TICK ? label.slice(0, MAX_TICK - 1) + "…" : label;
    }

    /* ── a11y: qrafikin mətn/cədvəl qarşılığı ─────────────────────────────── */
    function dataTable(rows, labels) {
        var details = el("details", "pan__table-wrap");
        details.appendChild(el("summary", "pan__table-toggle", labels.table));
        var table = el("table", "pan__table");
        var head = el("thead");
        var headRow = el("tr");
        headRow.appendChild(el("th", null, labels.indicator));
        headRow.appendChild(el("th", null, labels.count));
        headRow.appendChild(el("th", null, labels.percent));
        head.appendChild(headRow);
        table.appendChild(head);
        var body = el("tbody");
        rows.forEach(function (row) {
            var tr = el("tr");
            tr.appendChild(el("th", null, row.label));
            tr.appendChild(el("td", null, row.count));
            tr.appendChild(el("td", null, row.percent + "%"));
            body.appendChild(tr);
        });
        table.appendChild(body);
        details.appendChild(table);
        return details;
    }

    function chartBox(spec, labels, colors, charts) {
        var box = el("section", "pan__box");
        box.appendChild(el("h4", "pan__box-title", spec.title));

        if (!spec.rows.length) {
            box.appendChild(el("p", "pan__empty", labels.empty));
            return box;
        }

        var wrap = el("div", "pan__canvas-wrap");
        var canvas = document.createElement("canvas");
        // Ekran oxuyucusu üçün: qrafik dekorativdir, məlumat altdakı cədvəldədir.
        canvas.setAttribute("role", "img");
        canvas.setAttribute("aria-label", spec.title);
        wrap.appendChild(canvas);
        box.appendChild(wrap);
        box.appendChild(dataTable(spec.rows, labels));

        var values = spec.rows.map(function (row) {
            return row.count;
        });
        var names = spec.rows.map(function (row) {
            return row.label;
        });
        var doughnut = spec.chart === "doughnut";
        charts.push({
            canvas: canvas,
            config: {
                type: doughnut ? "doughnut" : "bar",
                data: {
                    labels: names,
                    datasets: [
                        {
                            data: values,
                            backgroundColor: doughnut ? colors : colors[0],
                            borderRadius: doughnut ? 0 : 6,
                            borderWidth: doughnut ? 0 : undefined
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    indexAxis: doughnut ? "x" : "y",
                    cutout: doughnut ? "62%" : undefined,
                    plugins: { legend: { display: doughnut, position: "bottom" } },
                    scales: doughnut
                        ? {}
                        : {
                              x: { beginAtZero: true, ticks: { precision: 0 } },
                              // Fakültə/ixtisas adları uzundur; ox etiketi kəsilir,
                              // TAM ad isə tooltip-də və altdakı cədvəldə qalır.
                              y: { ticks: { callback: truncateTick } }
                          }
                }
            }
        });
        return box;
    }

    function workloadBox(items, labels) {
        var box = el("section", "pan__box pan__box--text");
        box.appendChild(el("h4", "pan__box-title", labels.workload));
        var list = el("dl", "pan__facts");
        items.forEach(function (item) {
            list.appendChild(el("dt", null, item.label));
            list.appendChild(el("dd", null, item.value));
        });
        box.appendChild(list);
        return box;
    }

    function renderCards(container, payload, labels) {
        container.textContent = "";
        var cards = [{ label: labels.total, value: payload.total }];
        (payload.status || []).forEach(function (row) {
            cards.push({ label: row.label, value: row.count });
        });
        if (payload.can_view_demographics && payload.age) {
            cards.push({
                label: labels.coverage,
                value: payload.age.coverage_percent + "%"
            });
        }
        cards.forEach(function (card) {
            var node = el("div", "pan__card");
            node.appendChild(el("span", "pan__card-value", card.value));
            node.appendChild(el("span", "pan__card-label", card.label));
            container.appendChild(node);
        });
    }

    function specsFor(payload, labels) {
        var total = payload.total || 0;
        function fromCounts(key, title, rows, chart) {
            return {
                key: key,
                title: title,
                chart: chart,
                rows: (rows || []).map(function (row) {
                    return { label: row.label, count: row.count, percent: percentOf(row.count, total) };
                })
            };
        }
        var specs = [fromCounts("status", labels.status, payload.status, "doughnut")];
        if ((payload.gender || []).length) {
            specs.push(fromCounts("gender", labels.gender, payload.gender, "doughnut"));
        }
        if (payload.age && (payload.age.buckets || []).length) {
            specs.push(fromCounts("age", labels.age, payload.age.buckets, "bar"));
        }
        (payload.breakdowns || []).forEach(function (item) {
            specs.push(item);
        });
        return specs;
    }

    function setup(root) {
        var panel = root.querySelector("[data-people-analytics]");
        if (!panel) {
            return;
        }
        var urls = { charts: root.dataset.chartsUrl, ai: root.dataset.aiUrl };
        var labels = {
            total: panel.dataset.i18nTotal,
            table: panel.dataset.i18nTable,
            indicator: panel.dataset.i18nIndicator,
            count: panel.dataset.i18nCount,
            percent: panel.dataset.i18nPercent,
            empty: panel.dataset.i18nEmpty,
            coverage: panel.dataset.i18nCoverage,
            workload: panel.dataset.i18nWorkload,
            status: panel.dataset.i18nStatus,
            gender: panel.dataset.i18nGender,
            age: panel.dataset.i18nAge,
            aiLoading: panel.dataset.i18nAiLoading,
            aiError: panel.dataset.i18nAiError,
            aiQuota: panel.dataset.i18nAiQuota,
            aiCached: panel.dataset.i18nAiCached
        };
        var cards = panel.querySelector("[data-pan-cards]");
        var grid = panel.querySelector("[data-pan-charts]");
        var aiBlock = panel.querySelector("[data-pan-ai]");
        var aiButton = panel.querySelector("[data-pan-ai-btn]");
        var aiOut = panel.querySelector("[data-pan-ai-out]");
        var instances = [];
        // `null` = heç vaxt yüklənməyib; `load()` sətri DƏRHAL yazır ki, eyni
        // filtr üçün ikinci sorğu getməsin (ilkin yükləmə + hadisə yarışı).
        var query = null;

        function destroyCharts() {
            instances.forEach(function (chart) {
                try {
                    chart.destroy();
                } catch (error) {
                    /* Chart.js artıq təmizləyib — susdur */
                }
            });
            instances = [];
        }

        function render(payload) {
            destroyCharts();
            renderCards(cards, payload, labels);
            grid.textContent = "";
            var colors = palette(panel);
            var pending = [];
            specsFor(payload, labels).forEach(function (spec) {
                grid.appendChild(chartBox(spec, labels, colors, pending));
            });
            if ((payload.workload || []).length) {
                grid.appendChild(workloadBox(payload.workload, labels));
            }
            whenChart(function () {
                pending.forEach(function (item) {
                    instances.push(new window.Chart(item.canvas, item.config));
                });
            });
        }

        function hide() {
            panel.hidden = true;
        }

        function load(nextQuery) {
            query = nextQuery || "";
            window.EMSCore.fetchJSON(urls.charts + (query ? "?" + query : ""))
                .then(function (payload) {
                    if (!payload || !payload.has_access) {
                        // Fail-closed: əhatəsi olmayan istifadəçi BOŞ statistika görür.
                        hide();
                        return;
                    }
                    panel.hidden = false;
                    render(payload);
                })
                .catch(function () {
                    hide();
                });
        }

        if (aiButton && aiOut) {
            aiButton.addEventListener("click", function () {
                aiOut.textContent = "";
                aiOut.appendChild(el("p", "pan__hint", labels.aiLoading));
                aiButton.disabled = true;
                window.EMSCore.fetchJSON(urls.ai + (query ? "?" + query : ""))
                    .then(function (payload) {
                        aiButton.disabled = false;
                        if (!payload || !payload.ok) {
                            // Xəta halında bölmə səssizcə gizlənir, səhifə sınmır.
                            if (aiBlock) {
                                aiBlock.hidden = true;
                            }
                            return;
                        }
                        aiOut.textContent = "";
                        aiOut.appendChild(markdown(payload.summary || ""));
                        if (payload.limit !== undefined && payload.limit !== null) {
                            var quota = labels.aiQuota + ": " + payload.remaining + "/" + payload.limit;
                            if (payload.cached) {
                                quota += " · " + labels.aiCached;
                            }
                            aiOut.appendChild(el("p", "pan__ai-quota", quota));
                        }
                    })
                    .catch(function () {
                        aiButton.disabled = false;
                        if (aiBlock) {
                            aiBlock.hidden = true;
                        }
                    });
            });
        }

        root.addEventListener("people:filters", function (event) {
            var next = (event.detail && event.detail.query) || "";
            if (next === query) {
                return;
            }
            load(next);
        });

        // Skript sırasından asılı olmamaq üçün: kataloq artıq yüklənibsə son
        // filtr sətri `dataset`-dədir, dərhal ondan başlayırıq.
        load(root.dataset.peopleFilterQuery || "");
    }

    /* Backend Markdown qaytarır; yalnız başlıq/siyahı/abzas tanınır və hər şey
     * `textContent` ilə qurulur — HTML injeksiyası mümkün deyil.
     *
     * SƏTİR-SƏTİR oxunur, blok-blok YOX: model başlığın dərhal altına boş sətir
     * qoymadan mətn yazır («## Başlıq\nMətn»), blok yanaşmasında isə belə blok
     * başlıq kimi tanınmayıb ekrana «##» işarələri ilə düşürdü. */
    function markdown(text) {
        var wrap = el("div", "pan__ai-text");
        var list = null;
        var paragraph = [];

        function flushParagraph() {
            if (paragraph.length) {
                wrap.appendChild(el("p", null, paragraph.join(" ")));
                paragraph = [];
            }
        }

        String(text || "")
            .split(/\r?\n/)
            .forEach(function (raw) {
                var line = raw.trim().replace(/\*\*/g, "").replace(/`/g, "");
                if (!line) {
                    flushParagraph();
                    list = null;
                    return;
                }
                var heading = /^#{1,6}\s+(.*)$/.exec(line);
                if (heading) {
                    flushParagraph();
                    list = null;
                    wrap.appendChild(el("h5", "pan__ai-h", heading[1]));
                    return;
                }
                var bullet = /^(?:[-*]|\d+\.)\s+(.*)$/.exec(line);
                if (bullet) {
                    flushParagraph();
                    if (!list) {
                        list = el("ul", "pan__ai-list");
                        wrap.appendChild(list);
                    }
                    list.appendChild(el("li", null, bullet[1]));
                    return;
                }
                list = null;
                paragraph.push(line);
            });
        flushParagraph();
        return wrap;
    }

    function boot() {
        var roots = document.querySelectorAll("[data-people-root]");
        Array.prototype.forEach.call(roots, function (root) {
            if (root.dataset.peopleAnalyticsInit === "1") {
                return;
            }
            root.dataset.peopleAnalyticsInit = "1";
            setup(root);
        });
    }

    if (window.EMSReady) {
        window.EMSReady(boot);
    } else {
        document.addEventListener("DOMContentLoaded", boot);
    }
})();
