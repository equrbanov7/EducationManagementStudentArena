/* system_monitoring_renderers.js — ətraflı (drill-down) tabların renderləri.
 * 2026-10-01 redizayn: köhnə «İcmal» tabı «Ümumi vəziyyət» (`system_monitoring_summary.js`)
 * ilə əvəz olundu; inline `style` atributları CSS class-larına çevrildi; filtr/səhifələmə
 * select-ləri layihənin stilli komponentindədir (`format.selectMarkup`); insident əməlləri
 * yalnız API `can_manage` verəndə (superadmin) görünür — RİM rəhbəri oxu-only görür.
 * 2026-10-05: «Təhlükəsizlik» tabı öz moduluna (`system_monitoring_security.js`) köçdü — burada nümayəndə.
 */
(function () {
    "use strict";

    var namespace = window.EMSSystemMonitoring = window.EMSSystemMonitoring || {};

    // /jsi18n/ kataloqu base.html-də bu fayldan SONRA yüklənir. Ona görə
    // window.gettext-i modul yüklənəndə deyil, hər çağırışda oxuyuruq.
    function gettext(text) {
        return window.gettext ? window.gettext(text) : text;
    }

    namespace.createRenderers = function (context) {
        var body = context.body;
        var states = context.states;
        var escapeHtml = context.escapeHtml;
        var selected = context.selected;
        var formatBytes = context.formatBytes;
        var formatDuration = context.formatDuration;
        var percent = context.percent;
        var number = context.number;
        var statusClass = context.statusClass;
        var card = context.card;
        var dot = context.dot;
        var pill = context.pill;
        var chartGrid = context.chartGrid;
        var lineChart = context.lineChart;
        var rowsFrom = context.rowsFrom;
        var pager = context.pager;
        var t = context.t || function (key) { return key; };

        function selectMarkup(attrs, options, current, label) {
            return namespace.format.selectMarkup(attrs, options, current, label);
        }

        function renderServer(data) {
            var summary = data.summary || {};
            var chart = data.charts || {};
            var loadCapacity = summary.cores ? summary.load5 / summary.cores * 100 : null;
            var html = '<div class="smx-cards">';
            html += card(gettext("Uptime"), escapeHtml(formatDuration(summary.uptime_seconds)));
            html += card(gettext("CPU nüvələri"), number(summary.cores));
            html += card(
                gettext("Load 1/5/15"),
                number(summary.load1, 1) + " / " + number(summary.load5, 1) + " / " + number(summary.load15, 1)
            );
            html += card(gettext("Load doluluğu"), percent(loadCapacity), statusClass(loadCapacity, 70, 90));
            html += card(
                "RAM",
                formatBytes(summary.mem_total && summary.mem_available ? summary.mem_total - summary.mem_available : null) +
                    " <small>/ " + formatBytes(summary.mem_total) + "</small>"
            );
            html += card(
                gettext("Disk boş"),
                formatBytes(summary.disk_free) + " <small>/ " + formatBytes(summary.disk_total) + "</small>"
            );
            html += card(gettext("Inode boş"), percent(summary.inode_free_percent));
            html += card(gettext("Proseslər"), number(summary.processes));
            html += card(gettext("Fayl deskriptorları"), number(summary.file_descriptors)) + "</div>";
            html += chartGrid([
                ["CPU %", "smx-c-cpu"],
                ["RAM %", "smx-c-mem"],
                ["Swap %", "smx-c-swap"],
                [gettext("Load (1 dəq)"), "smx-c-load"],
                [gettext("Disk istifadəsi %"), "smx-c-disk"],
                ["Disk I/O %", "smx-c-io"],
                [gettext("Node exporter şəbəkəsi (B/s) — RX/TX"), "smx-c-net"],
            ]);
            body.innerHTML = html;
            lineChart("smx-c-cpu", chart.cpu, { percent: true });
            lineChart("smx-c-mem", chart.memory, { percent: true });
            lineChart("smx-c-swap", chart.swap, { percent: true });
            lineChart("smx-c-load", chart.load);
            lineChart("smx-c-disk", chart.disk_used_percent, { percent: true });
            lineChart("smx-c-io", chart.disk_io, { percent: true });
            var network = (chart.net_rx || []).map(function (item) {
                return Object.assign({}, item, { label: "RX" });
            }).concat((chart.net_tx || []).map(function (item) {
                return Object.assign({}, item, { label: "TX" });
            }));
            lineChart("smx-c-net", network);
        }

        function renderContainers(data) {
            var rows = rowsFrom(data, "containers");
            if (!rows.length) {
                body.innerHTML = '<div class="smx-empty">' +
                    escapeHtml(gettext("Konteyner məlumatı yoxdur (cAdvisor işə düşməyib?)")) + "</div>";
                return;
            }
            var html = '<div class="smx-table-wrap"><table class="smx-table"><thead><tr>' +
                "<th></th><th>" + escapeHtml(gettext("Konteyner")) + "</th><th>" +
                escapeHtml(gettext("Uptime")) + "</th><th>CPU</th><th>RAM</th><th>" +
                escapeHtml(gettext("Limit")) + "</th>" +
                "<th>" + escapeHtml(gettext("Restart (24s)")) + "</th><th>OOM</th><th>RX/TX</th><th>" +
                escapeHtml(gettext("Image")) + "</th></tr></thead><tbody>";
            rows.forEach(function (row) {
                html += "<tr><td>" + dot(row.alive) + "</td><td><b>" + escapeHtml(row.name) + "</b></td>" +
                    "<td>" + escapeHtml(formatDuration(row.uptime_seconds)) + "</td>" +
                    "<td>" + number(row.cpu_percent, 1) + "%</td>" +
                    "<td>" + formatBytes(row.memory_bytes) + "</td>" +
                    "<td>" + (row.memory_limit_bytes ? formatBytes(row.memory_limit_bytes) : "—") + "</td>" +
                    '<td class="' + (row.restarts_24h > 3 ? "smx-crit-text" : "") + '">' +
                    row.restarts_24h + "</td>" +
                    '<td class="' + (row.oom_events > 0 ? "smx-crit-text" : "") + '">' +
                    row.oom_events + "</td>" +
                    "<td>" + formatBytes(row.net_rx_bps) + "/s · " + formatBytes(row.net_tx_bps) + "/s</td>" +
                    '<td class="smx-ellipsis">' +
                    escapeHtml(row.image) + "</td></tr>";
            });
            body.innerHTML = html + "</tbody></table></div>" + pager(data, rows.length);
        }

        function topTable(title, rows, unit) {
            var html = '<div class="smx-panel smx-panel--spaced"><h4>' + escapeHtml(title) + "</h4>";
            if (!rows || !rows.length) {
                return html + '<div class="smx-empty smx-empty--compact">' +
                    escapeHtml(gettext("Məlumat yoxdur")) + "</div></div>";
            }
            html += '<table class="smx-table"><tbody>';
            rows.forEach(function (row) {
                html += '<tr><td class="smx-wrap">' + escapeHtml(row.path) + '</td><td class="smx-num">' +
                    number(row.value, 3) + " " + unit + "</td></tr>";
            });
            return html + "</tbody></table></div>";
        }

        function renderApplication(data) {
            var summary = data.summary || {};
            var chart = data.charts || {};
            var html = '<div class="smx-cards">';
            ["p50", "p95", "p99"].forEach(function (key) {
                html += card(
                    key,
                    summary[key] == null ? "—" : (summary[key] * 1000).toFixed(0) + " <small>ms</small>",
                    key === "p50" ? "" : statusClass(summary[key], 2, 5)
                );
            });
            ["2xx", "3xx", "4xx", "5xx", "429"].forEach(function (key) {
                var value = summary["status_" + key + "_15m"];
                html += card(
                    key + (key === "2xx" ? " " + gettext("(15 dəq)") : ""),
                    number(value),
                    key === "5xx" ? ((value || 0) > 0 ? "warn" : "ok") : ""
                );
            });
            html += "</div>" + chartGrid([
                [gettext("Sorğu axını (req/s)"), "smx-a-rate"],
                [gettext("5xx nisbəti %"), "smx-a-err"],
                [gettext("p95 gecikmə (s)"), "smx-a-p95"],
                [gettext("p99 gecikmə (s)"), "smx-a-p99"],
            ]);
            html += topTable(gettext("Ən yavaş endpoint-lər (orta, 30 dəq)"), summary.slow_endpoints, "s");
            html += topTable(
                gettext("Ən çox 5xx verən endpoint-lər (30 dəq)"),
                summary.error_endpoints,
                gettext("xəta")
            );
            body.innerHTML = html;
            lineChart("smx-a-rate", chart.request_rate);
            lineChart("smx-a-err", chart.error_rate, { percent: true });
            lineChart("smx-a-p95", chart.latency_p95);
            lineChart("smx-a-p99", chart.latency_p99);
        }

        function renderDatabase(data) {
            var summary = data.summary || {};
            var chart = data.charts || {};
            var html = '<div class="smx-cards">';
            html += card(
                "PostgreSQL",
                dot(summary.pg_up === 1) + (summary.pg_up === 1 ? gettext("işləyir") : gettext("DAYANIB")),
                summary.pg_up === 1 ? "ok" : "crit"
            );
            html += card(
                gettext("Bağlantılar"),
                number(summary.total_connections) + " <small>/ " + number(summary.max_connections) + "</small>",
                statusClass(summary.max_connections ? 100 * summary.total_connections / summary.max_connections : null, 80, 95)
            );
            html += card(
                gettext("Aktiv / Boşda"),
                number(summary.active_connections) + " / " + number(summary.idle_connections)
            );
            html += card(
                gettext("Cache hit"),
                percent(summary.cache_hit_ratio),
                summary.cache_hit_ratio != null && summary.cache_hit_ratio < 95 ? "warn" : "ok"
            );
            html += card(gettext("Baza ölçüsü"), formatBytes(summary.db_size_bytes));
            html += card(
                gettext("Deadlock (1s)"),
                number(summary.deadlocks_1h),
                (summary.deadlocks_1h || 0) > 0 ? "crit" : "ok"
            );
            html += card(gettext("Temp fayllar (1s)"), number(summary.temp_files_1h));
            html += card(
                gettext("Backup yaşı"),
                escapeHtml(formatDuration(summary.backup_age_seconds)),
                summary.backup_age_seconds != null && summary.backup_age_seconds > 93600 ? "crit" : "ok"
            );
            html += '</div><h4 class="smx-subhead">' +
                escapeHtml(gettext("PgBouncer (session mode — RLS üçün dəyişdirilmir)")) + "</h4>";
            html += '<div class="smx-cards">';
            html += card(gettext("Aktiv klientlər"), number(summary.pgbouncer_active_clients));
            html += card(
                gettext("Gözləyən klientlər"),
                number(summary.pgbouncer_waiting_clients),
                (summary.pgbouncer_waiting_clients || 0) > 0 ? "warn" : "ok"
            );
            html += card(gettext("Aktiv server bağlantıları"), number(summary.pgbouncer_active_servers));
            html += card(gettext("Boş server bağlantıları"), number(summary.pgbouncer_idle_servers));
            html += card(gettext("Max gözləmə"), number(summary.pgbouncer_max_wait_seconds, 2) + " <small>s</small>");
            html += "</div>" + chartGrid([
                [gettext("Bağlantı sayı"), "smx-d-conn"],
                [gettext("Tranzaksiya/s"), "smx-d-tps"],
            ]);
            body.innerHTML = html;
            lineChart("smx-d-conn", chart.connections);
            lineChart("smx-d-tps", chart.tps);
        }

        function renderRedisCelery(data) {
            var summary = data.summary || {};
            var chart = data.charts || {};
            var html = '<div class="smx-cards">';
            html += card(
                "Redis",
                dot(summary.redis_up === 1) + (summary.redis_up === 1 ? gettext("işləyir") : gettext("DAYANIB")),
                summary.redis_up === 1 ? "ok" : "crit"
            );
            html += card(
                gettext("Yaddaş"),
                formatBytes(summary.redis_memory_used) +
                    (summary.redis_memory_max ? " <small>/ " + formatBytes(summary.redis_memory_max) + "</small>" : "")
            );
            html += card(gettext("Klientlər"), number(summary.redis_clients));
            html += card(
                gettext("Bloklanmış"),
                number(summary.redis_blocked),
                (summary.redis_blocked || 0) > 10 ? "warn" : "ok"
            );
            html += card(gettext("Hit nisbəti"), percent(summary.redis_hit_ratio));
            html += card(
                gettext("Evicted (cəmi)"),
                number(summary.redis_evicted_total),
                (summary.redis_evicted_total || 0) > 0 ? "crit" : "ok"
            );
            html += card(
                "Celery worker",
                number(summary.celery_workers_online),
                (summary.celery_workers_online || 0) > 0 ? "ok" : "crit"
            );
            html += card(
                gettext("Aktiv / Reserved"),
                number(summary.celery_active_tasks) + " / " + number(summary.celery_reserved_tasks)
            );
            html += card(
                gettext("Növbə uzunluğu"),
                number(summary.celery_queue_length),
                (summary.celery_queue_length || 0) > 200 ? "warn" : "ok"
            );
            html += card(
                gettext("Statistika yaşı"),
                escapeHtml(formatDuration(summary.celery_stats_age_seconds)),
                summary.celery_stats_age_seconds != null && summary.celery_stats_age_seconds > 300 ? "crit" : "ok"
            );
            html += "</div>" + chartGrid([
                [gettext("Redis yaddaş (B)"), "smx-r-mem"],
                [gettext("Redis əmr/s"), "smx-r-ops"],
                [gettext("Celery növbəsi"), "smx-r-q"],
            ]);
            body.innerHTML = html;
            lineChart("smx-r-mem", chart.redis_memory);
            lineChart("smx-r-ops", chart.redis_ops);
            lineChart("smx-r-q", chart.celery_queue);
        }

        function renderExams(data) {
            var database = data.db || {};
            var counters = data.counters || {};
            var chart = data.charts || {};
            var html = data.metrics_degraded ?
                '<div class="smx-degraded"><i class="fas fa-triangle-exclamation"></i> ' +
                escapeHtml(gettext("Metrik servisi əlçatmazdır — yalnız baza sayğacları göstərilir.")) +
                "</div>" : "";
            html += '<div class="smx-cards">';
            html += card(gettext("Aktiv imtahanlar"), number(database.active_exams));
            html += card(gettext("Hazırda imtahanda"), number(database.in_progress_attempts));
            html += card(gettext("Bu gün təhvil verilən"), number(database.submitted_today));
            html += card(gettext("PIN cəhdləri (1s)"), number(counters.pin_attempts_1h));
            html += card(
                gettext("Uğursuz PIN (1s)"),
                number(counters.pin_failures_1h),
                (counters.pin_failures_1h || 0) > 20 ? "warn" : "ok"
            );
            html += card(
                gettext("Autosave xətaları (1s)"),
                number(counters.autosave_errors_1h),
                (counters.autosave_errors_1h || 0) > 0 ? "warn" : "ok"
            );
            html += card(gettext("Nəzarət insidentləri (1s)"), number(counters.supervision_incidents_1h)) + "</div>";
            if (data.charts) {
                html += chartGrid([
                    [gettext("Cəhd başlanğıcları (15 dəq pəncərə)"), "smx-e-start"],
                    [gettext("Təhvillər"), "smx-e-sub"],
                    [gettext("Autosave xətaları"), "smx-e-as"],
                    [gettext("Uğursuz PIN cəhdləri"), "smx-e-pin"],
                ]);
            }
            html += '<p class="smx-foot">' +
                escapeHtml(gettext(
                    "Yalnız aqreqat statistika göstərilir — sual, cavab, PIN və şəxsi məlumat bu modulda YOXDUR."
                )) + "</p>";
            body.innerHTML = html;
            if (data.charts) {
                lineChart("smx-e-start", chart.attempt_starts);
                lineChart("smx-e-sub", chart.submissions);
                lineChart("smx-e-as", chart.autosave_failures);
                lineChart("smx-e-pin", chart.pin_failures);
            }
        }

        // «Təhlükəsizlik» tabı (hadisələr + IP filtri + uğurlu girişlər) 2026-10-05-dən
        // `system_monitoring_security.js`-dədir; modul yüklənməyibsə sadə boş vəziyyət.
        function renderSecurity(data) {
            if (namespace.security && typeof namespace.security.render === "function") {
                namespace.security.render(body, data, context);
                return;
            }
            body.innerHTML = '<div class="smx-empty">' + escapeHtml(gettext("Təhlükəsizlik hadisəsi yoxdur")) + "</div>";
        }

        function renderLogs(data) {
            var state = states.logs;
            var rows = rowsFrom(data, "lines");
            var containers = data.containers || [];
            var html = '<div class="smx-filter">' + selectMarkup(
                'id="smx-log-container" data-live-search="true"',
                [["", gettext("Bütün konteynerlər")]].concat(containers.map(function (name) { return [name, name]; })),
                state.container,
                gettext("Bütün konteynerlər")
            ) + selectMarkup('id="smx-log-level"', [
                ["", gettext("Bütün səviyyələr")], ["error", "error"], ["warning", "warning"], ["critical", "critical"],
            ], state.level, gettext("Bütün səviyyələr")) +
                '<input type="text" class="ems-input" id="smx-log-q" placeholder="' +
                escapeHtml(gettext("Mətn axtarışı…")) + '" maxlength="120" value="' +
                escapeHtml(state.q) + '"><button type="button" class="smx-btn" id="smx-log-go">' +
                '<i class="fas fa-search"></i> ' + escapeHtml(gettext("Axtar")) + "</button></div>";
            if (!rows.length) {
                body.innerHTML = html + '<div class="smx-empty">' +
                    escapeHtml(gettext("Log tapılmadı")) + "</div>";
                return;
            }
            html += '<div class="smx-table-wrap"><table class="smx-table"><tbody>';
            rows.forEach(function (row) {
                html += '<tr><td class="smx-muted">' +
                    escapeHtml(new Date(row.ts).toLocaleTimeString("az")) + "</td><td><b>" +
                    escapeHtml(row.container) + '</b></td><td class="smx-log">' +
                    escapeHtml(row.line) + "</td></tr>";
            });
            body.innerHTML = html + "</tbody></table></div>" + pager(data, rows.length);
        }

        function renderAlerts(data) {
            var rows = data.alerts || [];
            if (!rows.length) {
                body.innerHTML = '<div class="smx-empty">' + escapeHtml(gettext("Aktiv alert yoxdur")) + "</div>";
                return;
            }
            var html = '<div class="smx-table-wrap"><table class="smx-table"><thead><tr>' +
                "<th>" + escapeHtml(gettext("Alert")) + "</th><th>" + escapeHtml(gettext("Önəm")) +
                "</th><th>" + escapeHtml(gettext("Vəziyyət")) + "</th><th>" + escapeHtml(gettext("Başlayıb")) +
                "</th><th>" + escapeHtml(gettext("Xülasə")) + "</th>" +
                "</tr></thead><tbody>";
            rows.forEach(function (row) {
                html += "<tr><td><b>" + escapeHtml(row.name) + "</b></td><td>" +
                    pill(row.severity || "—", row.severity || "info") + "</td><td>" + escapeHtml(row.state) +
                    (row.silenced ? " " + pill(gettext("susdurulub"), "silenced") : "") + "</td><td>" +
                    escapeHtml(row.starts_at ? new Date(row.starts_at).toLocaleString("az") : "—") +
                    '</td><td class="smx-wrap">' + escapeHtml(row.summary) + "</td></tr>";
            });
            body.innerHTML = html + "</tbody></table></div>";
        }

        function renderIncidents(data) {
            var state = states.incidents;
            var rows = rowsFrom(data, "incidents");
            var canManage = data.can_manage === true;
            var html = '<div class="smx-filter">' + selectMarkup('id="smx-inc-status"', [
                ["open", gettext("Açıq olanlar")], ["", gettext("Hamısı")],
                ["resolved", gettext("Həll olunub")], ["silenced", gettext("Susdurulub")],
            ], state.status, gettext("Hamısı")) + "</div>" +
                (canManage ? "" : '<p class="smx-readonly"><i class="fas fa-eye" aria-hidden="true"></i> ' +
                    escapeHtml(t("readOnly")) + "</p>");
            if (!rows.length) {
                body.innerHTML = html + '<div class="smx-empty">' + escapeHtml(gettext("İnsident yoxdur")) + "</div>";
                return;
            }
            html += '<div class="smx-table-wrap"><table class="smx-table"><thead><tr>' +
                "<th>" + escapeHtml(gettext("Başlıq")) + "</th><th>" + escapeHtml(gettext("Önəm")) +
                "</th><th>" + escapeHtml(gettext("Status")) + "</th><th>" + escapeHtml(gettext("Servis")) +
                "</th><th>" + escapeHtml(gettext("Başlayıb")) + "</th><th>" + escapeHtml(gettext("Müddət")) + "</th>" +
                (canManage ? "<th>" + escapeHtml(gettext("Əməliyyat")) + "</th>" : "") + "</tr></thead><tbody>";
            rows.forEach(function (row) {
                var actions = !canManage || row.status === "resolved" ? "" : '<span class="smx-actions">' +
                    '<button type="button" data-inc="' + row.id + '" data-act="acknowledge">' +
                    escapeHtml(gettext("Qəbul et")) + "</button>" +
                    '<button type="button" data-inc="' + row.id + '" data-act="resolve">' +
                    escapeHtml(gettext("Həll olundu")) + "</button>" +
                    '<button type="button" data-inc="' + row.id + '" data-act="silence">' +
                    escapeHtml(gettext("Susdur")) + "</button></span>";
                html += '<tr><td class="smx-wrap"><b>' + escapeHtml(row.title) + "</b>" +
                    (row.resolution_note ? '<div class="smx-muted smx-small">' +
                        escapeHtml(row.resolution_note) + "</div>" : "") +
                    "</td><td>" + pill(row.severity, row.severity) + "</td><td>" +
                    pill(row.status, row.status) + "</td><td>" + escapeHtml(row.service || "—") + "</td><td>" +
                    escapeHtml(row.started_at ? new Date(row.started_at).toLocaleString("az") : "—") + "</td><td>" +
                    escapeHtml(formatDuration(row.duration_seconds)) + "</td>" +
                    (canManage ? "<td>" + actions + "</td>" : "") + "</tr>";
            });
            body.innerHTML = html + "</tbody></table></div>" + pager(data, rows.length);
        }

        return {
            server: renderServer,
            containers: renderContainers,
            application: renderApplication,
            database: renderDatabase,
            "redis-celery": renderRedisCelery,
            exams: renderExams,
            "security-events": renderSecurity,
            logs: renderLogs,
            alerts: renderAlerts,
            incidents: renderIncidents,
        };
    };

    if (typeof namespace.bootPending === "function") {
        namespace.bootPending();
    }
})();
