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
        if (typeof namespace.createRenderers !== "function") return;
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
        var activeTab = "overview";
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
            "security-events": { page: 1, page_size: 20, type: "" },
            incidents: { page: 1, page_size: 20, status: "open" },
        };

        function byId(id) {
            return scope.querySelector("#" + id);
        }

        function escapeHtml(value) {
            var node = document.createElement("div");
            node.textContent = value == null ? "" : String(value);
            return node.innerHTML;
        }

        function selected(value, current) {
            return String(value) === String(current) ? " selected" : "";
        }

        function formatBytes(value) {
            if (value == null || isNaN(value)) return "—";
            var units = ["B", "KB", "MB", "GB", "TB"];
            var index = 0;
            value = Number(value);
            while (value >= 1024 && index < units.length - 1) {
                value /= 1024;
                index += 1;
            }
            return value.toFixed(value >= 100 ? 0 : 1) + " " + units[index];
        }

        function formatDuration(seconds) {
            if (seconds == null || isNaN(seconds)) return "—";
            seconds = Math.floor(seconds);
            var days = Math.floor(seconds / 86400);
            var hours = Math.floor(seconds % 86400 / 3600);
            var minutes = Math.floor(seconds % 3600 / 60);
            if (days > 0) {
                return interpolate(
                    gettext("%(days)s gün %(hours)s saat"),
                    { days: days, hours: hours },
                    true
                );
            }
            if (hours > 0) {
                return interpolate(
                    gettext("%(hours)s saat %(minutes)s dəq"),
                    { hours: hours, minutes: minutes },
                    true
                );
            }
            return interpolate(
                gettext("%(minutes)s dəq %(seconds)s san"),
                { minutes: minutes, seconds: seconds % 60 },
                true
            );
        }

        function percent(value) {
            return value == null || isNaN(value) ? "—" : Number(value).toFixed(1) + "%";
        }

        function number(value, digits) {
            return value == null || isNaN(value) ? "—" : Number(value).toFixed(digits == null ? 0 : digits);
        }

        function statusClass(value, warning, critical) {
            return value == null ? "" : value >= critical ? "crit" : value >= warning ? "warn" : "ok";
        }

        function card(key, value, klass) {
            return '<div class="smx-card ' + (klass || "") + '"><div class="k">' +
                escapeHtml(key) + '</div><div class="v">' + value + "</div></div>";
        }

        function skeletonCards(count) {
            var s = '<div class="smx-card"><span class="skeleton skeleton-line skeleton-line--sm"></span>' +
                '<span class="skeleton skeleton-line skeleton-line--lg" style="margin-top:8px"></span></div>';
            return '<div class="smx-cards" aria-hidden="true">' + new Array(count || 8).fill(s).join("") + "</div>";
        }

        function dot(up) {
            return '<span class="smx-dot ' + (up == null ? "na" : up ? "ok" : "bad") + '"></span>';
        }

        function pill(text, klass) {
            return '<span class="smx-pill ' + escapeHtml(klass) + '">' + escapeHtml(text) + "</span>";
        }

        function chartPanel(title, id) {
            return '<div class="smx-panel"><h4>' + escapeHtml(title) + '</h4><div class="smx-chart">' +
                '<canvas id="' + id + '"></canvas>' +
                '<div class="smx-chart-empty" hidden>' + escapeHtml(gettext("Məlumat yoxdur")) +
                "</div></div></div>";
        }

        function chartGrid(items) {
            return '<div class="smx-grid2">' + items.map(function (item) {
                return chartPanel(item[0], item[1]);
            }).join("") + "</div>";
        }

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
                var colors = ["#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed"];
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

        function rowsFrom(data, legacyKey) {
            if (Array.isArray(data.items)) return data.items;
            return Array.isArray(data[legacyKey]) ? data[legacyKey] : [];
        }

        function pagination(data, count) {
            var source = data.pagination || data;
            var state = states[activeTab] || {};
            var pageSize = Number(source.page_size || state.page_size || 20);
            var total = Number(source.total == null ? count : source.total);
            var page = Math.max(1, Number(source.page || state.page || 1));
            var pages = Math.max(1, Number(source.total_pages || Math.ceil(total / pageSize)));
            return {
                page: page,
                pageSize: pageSize,
                total: total,
                pages: pages,
                hasPrevious: source.has_previous == null ? page > 1 : source.has_previous,
                hasNext: source.has_next == null ? page < pages : source.has_next,
            };
        }

        function pager(data, count) {
            var meta = pagination(data, count);
            if (!meta.total) return "";
            var start = (meta.page - 1) * meta.pageSize + 1;
            var end = Math.min(meta.total, start + count - 1);
            return '<div class="smx-pagination"><span class="smx-page-summary">' +
                start + "–" + end + " / " + meta.total +
                "</span><label>" + escapeHtml(gettext("Sətir")) + ' <select data-smx-page-size>' +
                '<option value="10"' + selected(10, meta.pageSize) + '>10</option>' +
                '<option value="20"' + selected(20, meta.pageSize) + '>20</option>' +
                '<option value="50"' + selected(50, meta.pageSize) + '>50</option></select></label>' +
                '<button class="smx-btn" data-smx-page="' + (meta.page - 1) + '"' +
                (meta.hasPrevious ? "" : " disabled") + ' aria-label="' +
                escapeHtml(gettext("Əvvəlki səhifə")) + '">‹</button>' +
                "<span>" + meta.page + " / " + meta.pages + "</span>" +
                '<button class="smx-btn" data-smx-page="' + (meta.page + 1) + '"' +
                (meta.hasNext ? "" : " disabled") + ' aria-label="' +
                escapeHtml(gettext("Növbəti səhifə")) + '">›</button></div>';
        }

        function setDegraded(payload) {
            if (payload && payload.status === "degraded") {
                degradedBox.hidden = false;
                degradedText.textContent =
                    (payload.message || gettext("Monitorinq asılılığı əlçatmazdır")) +
                    (payload.last_successful_update ?
                        " · " + interpolate(
                            gettext("son uğurlu yenilənmə: %(time)s"),
                            { time: payload.last_successful_update },
                            true
                        ) : "");
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
        });

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
            lastLoadedAt = Date.now();
            updated.textContent = interpolate(
                gettext("Yeniləndi: %(time)s"),
                { time: new Date().toLocaleTimeString("az") },
                true
            );
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
                    if (!response.ok) {
                        throw new Error(interpolate(
                            gettext("Server xətası: %(status)s"),
                            { status: response.status },
                            true
                        ));
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
            timer = window.setInterval(function () {
                if (!scope.isConnected) {
                    destroy();
                } else if (started && autoRefresh.checked && visible()) {
                    refreshActiveSilently();
                }
            }, 60000);
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
                if (tabButton.dataset.tab === activeTab) return;
                scope.querySelectorAll(".smx-tab").forEach(function (item) {
                    item.classList.remove("active");
                });
                tabButton.classList.add("active");
                activeTab = tabButton.dataset.tab;
                if (observer) observer.disconnect();
                started = true;
                load(activeTab);
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
            } else if (event.target.id === "smx-sec-type") {
                states["security-events"].type = event.target.value;
                resetPagedState("security-events");
                load("security-events", { force: true });
            } else if (event.target.id === "smx-inc-status") {
                states.incidents.status = event.target.value;
                resetPagedState("incidents");
                load("incidents", { force: true });
            }
        });

        body.addEventListener("click", function (event) {
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
            if (document.hidden || !autoRefresh.checked || !started) return;
            if (Date.now() - lastLoadedAt > 60000 && visible()) refreshActiveSilently();
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
