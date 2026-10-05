/* system_monitoring.js — Sistem monitorinqi paneli: tab/yükləmə/keş/avto-yeniləmə,
 * qrafiklər (Chart.js), səhifələmə, insident əməlləri. Saf format köməkçiləri
 * 2026-09-21-də `system_monitoring_format.js`-ə (namespace.format) çıxarıldı —
 * modul ölçü büdcəsi; renderers `system_monitoring_renderers.js`-dədir.
 * 2026-10-01 (sahib): ilk tab «Ümumi vəziyyət» (`summary/`, renderer
 * `system_monitoring_summary.js`) + «AI ilə təhlil et» (`system_monitoring_ai.js`);
 * yeni mətnlər `#smx-i18n` JSON adasından (`t()` / `fmt()`), avto-yeniləmə 30 s
 * (xülasə) / 60 s (ətraflı tablar), səhifə gizli olanda dayanır.
 * 2026-10-05: «Təhlükəsizlik» tabı (IP filtri) `system_monitoring_security.js`-dədir; 400 cavabı
 * (filtr doğrulaması) `data.invalid` kimi renderer-ə gedir ki, filtr zolağı itməsin.
 * Şablon sırası: format → renderers → security → summary → ai → bu fayl (defer; sıra fail-soft).
 */
(function () {
    "use strict";

    var namespace = window.EMSSystemMonitoring = window.EMSSystemMonitoring || {};
    var script = document.currentScript;
    var panel = script && script.closest("[data-profile-section-panel='system-monitoring']");
    var root = panel && panel.querySelector("#smx-root");
    namespace.pendingRoots = namespace.pendingRoots || [];
    if (root && !root.dataset.smxInit && namespace.pendingRoots.indexOf(root) === -1) {
        namespace.pendingRoots.push(root);
    }

    namespace.bootPending = function () {
        if (typeof namespace.createRenderers !== "function" || !namespace.format) return;
        var roots = namespace.pendingRoots.splice(0);
        roots.forEach(function (pendingRoot) {
            if (!pendingRoot.isConnected || pendingRoot.dataset.smxInit) return;
            if (namespace.instance && typeof namespace.instance.destroy === "function") {
                namespace.instance.destroy();
            }
            namespace.instance = createInstance(pendingRoot);
        });
    };
    namespace.bootPending();

    function createInstance(scope) {
        scope.dataset.smxInit = "1";
        var api = scope.dataset.apiBase;
        var csrf = scope.dataset.csrf;
        var body = byId("smx-body");
        var degradedBox = byId("smx-degraded");
        var degradedText = byId("smx-degraded-text");
        var updated = byId("smx-updated");
        var range = byId("smx-range");
        var autoRefresh = byId("smx-auto");
        var refreshButton = byId("smx-refresh");
        var activeTab = "summary";
        var i18n = readI18n();
        var tick = 0;
        var charts = {};
        var cache = {};
        var inFlight = null;
        var requestSequence = 0;
        var timer = null;
        var observer = null;
        var started = false;
        var destroyed = false;
        var lastLoadedAt = 0;
        var cacheTtl = 15000;
        var logCursors = { 1: "" };
        var states = {
            containers: { page: 1, page_size: 20 },
            logs: { page: 1, page_size: 20, container: "", level: "", q: "", anchor_ns: "" },
            "security-events": { page: 1, page_size: 20, type: "", ip: "" },
            incidents: { page: 1, page_size: 20, status: "open" },
        };

        function byId(id) {
            return scope.querySelector("#" + id);
        }

        function readI18n() {
            var host = scope.closest("[data-profile-section-panel]") || document;
            var node = host.querySelector("#smx-i18n");
            try {
                return node ? JSON.parse(node.textContent || "{}") : {};
            } catch (error) {
                return {};
            }
        }

        function t(key) {
            return Object.prototype.hasOwnProperty.call(i18n, key) ? i18n[key] : key;
        }

        function fmt(text, values) {
            return String(text).replace(/\{(\w+)\}/g, function (match, name) {
                return values && values[name] != null ? String(values[name]) : match;
            });
        }

        // Saf format köməkçiləri ayrı fayldadır (system_monitoring_format.js,
        // 2026-09-21 bölgüsü) — eyni adlarla lokal alias, kod dəyişmir.
        var F = namespace.format;
        var escapeHtml = F.escapeHtml, selected = F.selected, formatBytes = F.formatBytes;
        var formatDuration = F.formatDuration, percent = F.percent, number = F.number;
        var statusClass = F.statusClass, card = F.card, skeletonCards = F.skeletonCards;
        var dot = F.dot, pill = F.pill, chartGrid = F.chartGrid, rowsFrom = F.rowsFrom;

        function destroyCharts() {
            Object.keys(charts).forEach(function (key) {
                try { charts[key].destroy(); } catch (error) { /* already removed */ }
            });
            charts = {};
        }

        function formatChartTime(milliseconds) {
            var options = Number(range.value) > 86400 ?
                { month: "2-digit", day: "2-digit", hour: "2-digit" } :
                { hour: "2-digit", minute: "2-digit" };
            return new Date(milliseconds).toLocaleString("az", options);
        }

        function lineChart(id, series, options, retry) {
            var canvas = byId(id);
            if (!canvas) return;
            var empty = canvas.parentNode.querySelector(".smx-chart-empty");
            var datasets = (Array.isArray(series) ? series : []).map(function (item, index) {
                var colors = (options && options.colors) || ["#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed"];
                var points = (item.points || []).map(function (point) {
                    return { x: Number(point[0]) * 1000, y: Number(point[1]) };
                }).filter(function (point) {
                    return Number.isFinite(point.x) && Number.isFinite(point.y);
                }).sort(function (left, right) {
                    return left.x - right.x;
                });
                return {
                    label: item.label || Object.values(item.labels || {}).join(" ") || gettext("seriya"),
                    data: points,
                    borderColor: colors[index % colors.length],
                    backgroundColor: colors[index % colors.length] + "12",
                    borderWidth: 1.75,
                    fill: false,
                    pointRadius: 0,
                    pointHoverRadius: 3,
                    spanGaps: true,
                    tension: 0.2,
                };
            }).filter(function (dataset) {
                return dataset.data.length > 0;
            });
            if (!datasets.length) {
                canvas.hidden = true;
                empty.hidden = false;
                return;
            }
            if (typeof window.Chart !== "function") {
                empty.hidden = false;
                empty.textContent = gettext("Qrafik hazırlanır…");
                if ((retry || 0) < 20) {
                    window.setTimeout(function () {
                        lineChart(id, series, options, (retry || 0) + 1);
                    }, 100);
                }
                return;
            }
            canvas.hidden = false;
            empty.hidden = true;
            var peak = Math.max.apply(null, datasets.reduce(function (values, dataset) {
                return values.concat(dataset.data.map(function (point) { return point.y; }));
            }, [0]));
            var yScale = { beginAtZero: true, ticks: { maxTicksLimit: 5 } };
            if (options && options.percent) {
                yScale.suggestedMax = Math.min(100, Math.max(5, Math.ceil(peak * 1.2 / 5) * 5));
            }
            charts[id] = new window.Chart(canvas, {
                type: "line",
                data: { datasets: datasets },
                options: {
                    animation: false,
                    devicePixelRatio: Math.min(window.devicePixelRatio || 1, 2),
                    interaction: { intersect: false, mode: "index" },
                    maintainAspectRatio: false,
                    normalized: true,
                    parsing: false,
                    responsive: true,
                    resizeDelay: 100,
                    plugins: {
                        decimation: { algorithm: "lttb", enabled: true, samples: 180, threshold: 240 },
                        legend: { display: datasets.length > 1, position: "bottom" },
                        tooltip: {
                            callbacks: {
                                title: function (items) {
                                    return items.length ?
                                        new Date(items[0].parsed.x).toLocaleString("az") : "";
                                },
                            },
                        },
                    },
                    scales: {
                        x: {
                            bounds: "data",
                            grid: { display: false },
                            ticks: { callback: formatChartTime, maxRotation: 0, maxTicksLimit: 6 },
                            type: "linear",
                        },
                        y: yScale,
                    },
                },
            });
        }


        function pager(data, count) {
            return F.pagerMarkup(data, count, states[activeTab] || {});
        }

        function setDegraded(payload) {
            if (payload && payload.status === "degraded") {
                degradedBox.hidden = false;
                degradedText.textContent =
                    (payload.message || gettext("Monitorinq asılılığı əlçatmazdır")) +
                    (payload.last_successful_update ?
                        " · " + interpolate(gettext("son uğurlu yenilənmə: %(time)s"), { time: payload.last_successful_update }, true) : "");
                return true;
            }
            degradedBox.hidden = true;
            return false;
        }

        var renderers = namespace.createRenderers({
            body: body,
            states: states,
            escapeHtml: escapeHtml,
            selected: selected,
            formatBytes: formatBytes,
            formatDuration: formatDuration,
            percent: percent,
            number: number,
            statusClass: statusClass,
            card: card,
            dot: dot,
            pill: pill,
            chartGrid: chartGrid,
            lineChart: lineChart,
            rowsFrom: rowsFrom,
            pager: pager,
            t: t,
            fmt: fmt,
            // Tab modulunun öz filtrləri (məs. «Təhlükəsizlik» IP filtri) üçün: 1-ci səhifədən təzə yüklə.
            reload: function (tab) { resetPagedState(tab); load(tab, { force: true }); },
        });
        var summaryContext = {
            t: t,
            fmt: fmt,
            api: api,
            csrf: csrf,
            escapeHtml: escapeHtml,
            formatBytes: formatBytes,
            formatDuration: formatDuration,
            lineChart: function (id, series) {
                lineChart(id, series, { colors: ["#2563eb", "#dc2626"] });
            },
        };
        renderers.summary = function (data) {
            if (namespace.summary && typeof namespace.summary.render === "function") {
                namespace.summary.render(body, data, summaryContext);
            } else {
                body.innerHTML = '<div class="smx-empty">' + escapeHtml(t("emptyData")) + "</div>";
            }
        };

        function paramsFor(tab) {
            var params = { range: range.value };
            Object.keys(states[tab] || {}).forEach(function (key) {
                var value = states[tab][key];
                if (tab === "logs" && key === "anchor_ns" && states.logs.page === 1) return;
                if (value !== "" && value != null) params[key] = value;
            });
            if (tab === "logs" && states.logs.page > 1 && logCursors[states.logs.page]) {
                params.before_ns = logCursors[states.logs.page];
            }
            return params;
        }

        function keyFor(tab, params) {
            return tab + "?" + new URLSearchParams(params).toString();
        }

        function invalidate(tab) {
            Object.keys(cache).forEach(function (key) {
                if (key.indexOf(tab + "?") === 0) delete cache[key];
            });
        }

        function renderPayload(tab, payload, preserveOnDegraded) {
            if (setDegraded(payload)) {
                if (!preserveOnDegraded) {
                    destroyCharts();
                    body.innerHTML = '<div class="smx-empty">' +
                        escapeHtml(gettext("Monitorinq asılılığı bərpa olunana qədər məlumat yoxdur.")) +
                        "</div>";
                }
                return;
            }
            destroyCharts();
            var data = payload && payload.data || {};
            if (tab === "logs" && data.anchor_ns) {
                states.logs.anchor_ns = data.anchor_ns;
                if (data.next_cursor_ns) logCursors[states.logs.page + 1] = data.next_cursor_ns;
            }
            renderers[tab](data);
            if (tab !== "summary" && window.EMSBootstrapSelect) window.EMSBootstrapSelect.init(body);
            lastLoadedAt = Date.now();
            updated.textContent = interpolate(gettext("Yeniləndi: %(time)s"), { time: new Date().toLocaleTimeString("az") }, true);
        }

        function load(tab, options) {
            options = options || {};
            var params = paramsFor(tab);
            var requestKey = keyFor(tab, params);
            var cached = cache[requestKey];
            if (!options.force && cached && Date.now() - cached.savedAt < cacheTtl) {
                if (inFlight && inFlight.controller) inFlight.controller.abort();
                requestSequence += 1;
                inFlight = null;
                refreshButton.classList.remove("is-loading");
                renderPayload(tab, cached.payload, false);
                return Promise.resolve(cached.payload);
            }
            if (inFlight && inFlight.key === requestKey) return inFlight.promise;
            if (inFlight && inFlight.controller) inFlight.controller.abort();
            var controller = typeof AbortController === "function" ? new AbortController() : null;
            var sequence = ++requestSequence;
            if (!options.silent) {
                destroyCharts();
                body.innerHTML = skeletonCards(8);
            }
            refreshButton.classList.add("is-loading");
            var fetchOptions = {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            };
            if (controller) fetchOptions.signal = controller.signal;
            var promise = fetch(api + tab + "/?" + new URLSearchParams(params), fetchOptions)
                .then(function (response) {
                    if (response.status === 403) {
                        throw new Error(gettext("Bu bölməyə icazəniz yoxdur."));
                    }
                    if (response.status === 400) {
                        // Filtr doğrulaması (məs. yanlış IP): renderer filtr zolağını saxlayıb xətanı yerində göstərir.
                        return response.json().catch(function () { return {}; }).then(function (error) {
                            return { status: "invalid", data: { invalid: error.detail ||
                                interpolate(gettext("Server xətası: %(status)s"), { status: 400 }, true) } };
                        });
                    }
                    if (!response.ok) {
                        throw new Error(interpolate(gettext("Server xətası: %(status)s"), { status: response.status }, true));
                    }
                    return response.json();
                })
                .then(function (payload) {
                    if (destroyed || sequence !== requestSequence ||
                            tab !== activeTab || !scope.isConnected) return payload;
                    if (payload.status !== "degraded") {
                        cache[requestKey] = { payload: payload, savedAt: Date.now() };
                    }
                    renderPayload(tab, payload, options.silent);
                    return payload;
                })
                .catch(function (error) {
                    if (error.name === "AbortError") return null;
                    if (!destroyed && sequence === requestSequence && tab === activeTab) {
                        if (options.silent) {
                            updated.textContent = gettext("Yeniləmə alınmadı");
                        } else {
                            body.innerHTML = '<div class="smx-error">' +
                                '<i class="fas fa-circle-exclamation"></i> ' +
                                escapeHtml(error.message) + "</div>";
                        }
                    }
                    return null;
                })
                .then(function (result) {
                    if (sequence === requestSequence) {
                        inFlight = null;
                        refreshButton.classList.remove("is-loading");
                    }
                    return result;
                });
            inFlight = { controller: controller, key: requestKey, promise: promise };
            return promise;
        }

        function visible() {
            return !document.hidden && scope.isConnected && scope.getClientRects().length > 0;
        }

        function begin() {
            if (started || destroyed || !visible()) return;
            started = true;
            load(activeTab);
        }

        function refreshActiveSilently() {
            if (activeTab === "logs") {
                if (states.logs.page > 1) return;
                states.logs.anchor_ns = "";
                logCursors = { 1: "" }; invalidate("logs");
            }
            load(activeTab, { force: true, silent: true });
        }

        function schedule() {
            // 30 s addım: xülasə hər addımda, ağır ətraflı tablar hər 2-ci addımda (60 s).
            timer = window.setInterval(function () {
                tick += 1;
                if (!scope.isConnected) {
                    destroy();
                } else if (started && autoRefresh.checked && visible() && (activeTab === "summary" || tick % 2 === 0)) {
                    refreshActiveSilently();
                }
            }, 30000);
        }

        function activateTab(tabName) {
            var target = scope.querySelector('.smx-tab[data-tab="' + tabName + '"]');
            if (!target || tabName === activeTab) return;
            scope.querySelectorAll(".smx-tab").forEach(function (item) {
                item.classList.toggle("active", item === target);
                item.setAttribute("aria-selected", item === target ? "true" : "false");
            });
            activeTab = tabName;
            if (observer) observer.disconnect();
            started = true;
            load(activeTab);
            if (typeof target.scrollIntoView === "function") {
                target.scrollIntoView({ block: "nearest", inline: "nearest" });
            }
        }

        function resetPagedState(tab) {
            if (!states[tab]) return;
            states[tab].page = 1;
            if (tab === "logs") {
                states.logs.anchor_ns = ""; logCursors = { 1: "" };
            }
            invalidate(tab);
        }

        scope.querySelectorAll(".smx-tab").forEach(function (tabButton) {
            tabButton.addEventListener("click", function () {
                activateTab(tabButton.dataset.tab);
            });
        });

        refreshButton.addEventListener("click", function () {
            if (activeTab === "logs") {
                states.logs.page = 1; states.logs.anchor_ns = "";
                logCursors = { 1: "" };
            }
            invalidate(activeTab);
            load(activeTab, { force: true });
        });

        range.addEventListener("change", function () {
            cache = {};
            Object.keys(states).forEach(resetPagedState);
            load(activeTab, { force: true });
        });

        body.addEventListener("change", function (event) {
            if (event.target.matches("[data-smx-page-size]")) {
                states[activeTab].page_size = Number(event.target.value);
                resetPagedState(activeTab);
                load(activeTab, { force: true });
            } else if (event.target.id === "smx-inc-status") {
                states.incidents.status = event.target.value;
                resetPagedState("incidents");
                load("incidents", { force: true });
            }
        });

        body.addEventListener("click", function (event) {
            var gotoButton = event.target.closest("[data-smx-goto]");
            if (gotoButton) {
                activateTab(gotoButton.dataset.smxGoto);
                return;
            }
            var pageButton = event.target.closest("[data-smx-page]");
            if (pageButton && !pageButton.disabled) {
                var nextPage = Number(pageButton.dataset.smxPage);
                if (activeTab === "logs" && nextPage === 1) {
                    states.logs.anchor_ns = ""; logCursors = { 1: "" };
                }
                states[activeTab].page = nextPage;
                load(activeTab, { force: true });
                return;
            }
            if (event.target.closest("#smx-log-go")) {
                states.logs.container = (byId("smx-log-container") || {}).value || "";
                states.logs.level = (byId("smx-log-level") || {}).value || "";
                states.logs.q = (byId("smx-log-q") || {}).value || "";
                resetPagedState("logs");
                load("logs", { force: true });
                return;
            }
            var actionButton = event.target.closest("[data-inc]");
            if (!actionButton) return;
            var note = actionButton.dataset.act === "resolve" ?
                (window.prompt(gettext("Həll qeydi (istəyə bağlı):")) || "") : "";
            fetch(api + "incidents/" + actionButton.dataset.inc + "/action/", {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "X-CSRFToken": csrf,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body: new URLSearchParams({
                    action: actionButton.dataset.act,
                    note: note,
                }).toString(),
            }).then(function (response) {
                if (!response.ok) throw new Error(gettext("Əməliyyat icra olunmadı."));
                invalidate("incidents");
                return load("incidents", { force: true });
            }).catch(function (error) {
                body.insertAdjacentHTML(
                    "afterbegin",
                    '<div class="smx-error">' + escapeHtml(error.message) + "</div>"
                );
            });
        });

        body.addEventListener("keydown", function (event) {
            if (event.key === "Enter" && event.target.id === "smx-log-q") {
                event.preventDefault();
                var go = byId("smx-log-go");
                if (go) go.click();
            }
        });

        function onVisibilityChange() {
            if (document.hidden) return;
            // 2026-10-02: arxa plan tabında açılan səhifədə IntersectionObserver begin()-i çağırır, amma
            // visible() false olduğu üçün heç nə yüklənmirdi və observer artıq bağlı idi — kartlar
            // həmişəlik «skeleton»-da qalırdı. Tab görünən olan kimi ilk yükləmə burada başlayır.
            if (!started) {
                begin();
                return;
            }
            if (!autoRefresh.checked) return;
            if (Date.now() - lastLoadedAt > 30000 && visible()) refreshActiveSilently();
        }

        function onSectionLoaded() {
            if (!scope.isConnected) destroy();
        }

        function destroy() {
            if (destroyed) return;
            destroyed = true;
            if (timer) window.clearInterval(timer);
            if (observer) observer.disconnect();
            if (inFlight && inFlight.controller) inFlight.controller.abort();
            document.removeEventListener("visibilitychange", onVisibilityChange);
            document.removeEventListener("profile:section:loaded", onSectionLoaded);
            destroyCharts();
            if (namespace.instance && namespace.instance.root === scope) {
                namespace.instance = null;
            }
        }

        document.addEventListener("visibilitychange", onVisibilityChange);
        document.addEventListener("profile:section:loaded", onSectionLoaded);
        if (typeof IntersectionObserver === "function") {
            observer = new IntersectionObserver(function (entries) {
                if (entries.some(function (entry) { return entry.isIntersecting; })) {
                    observer.disconnect();
                    if (typeof window.requestIdleCallback === "function") {
                        window.requestIdleCallback(begin, { timeout: 500 });
                    } else {
                        window.setTimeout(begin, 0);
                    }
                }
            }, { threshold: 0.01 });
            observer.observe(scope);
        } else {
            window.setTimeout(begin, 0);
        }
        schedule();
        return { destroy: destroy, root: scope };
    }
})();
