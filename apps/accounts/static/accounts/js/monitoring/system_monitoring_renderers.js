(function () {
    "use strict";

    var namespace = window.EMSSystemMonitoring = window.EMSSystemMonitoring || {};

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

        function renderOverview(data) {
            var server = data.server || {};
            var app = data.app || {};
            var services = data.services || {};
            var exams = data.exams || {};
            var html = '<div class="smx-cards">';
            html += card("CPU", percent(server.cpu_percent), statusClass(server.cpu_percent, 85, 95));
            html += card("RAM", percent(server.memory_percent), statusClass(server.memory_percent, 85, 95));
            html += card("Disk", percent(server.disk_percent), statusClass(server.disk_percent, 80, 90));
            html += card("Uptime", escapeHtml(formatDuration(server.uptime_seconds)));
            html += card("Konteynerlər", number(data.containers_alive) + " <small>işlək</small>");
            html += card("Sorğu axını", number(app.request_rate, 1) + " <small>req/s</small>");
            html += card("5xx nisbəti", percent(app.error_rate_percent), statusClass(app.error_rate_percent, 2, 10));
            html += card(
                "p95 gecikmə",
                app.p95_seconds == null ? "—" : (app.p95_seconds * 1000).toFixed(0) + " <small>ms</small>",
                statusClass(app.p95_seconds, 2, 5)
            );
            ["postgres", "redis", "nginx"].forEach(function (service) {
                var up = services[service + "_up"];
                var title = service === "postgres" ? "PostgreSQL" : service[0].toUpperCase() + service.slice(1);
                html += card(
                    title,
                    dot(up === 1) + (up === 1 ? "işləyir" : up == null ? "—" : "DAYANIB"),
                    up === 1 ? "ok" : "crit"
                );
            });
            var probesUp = services.endpoint_probes_up;
            html += card(
                "Endpoint yoxlamaları",
                dot(probesUp === 1) + (probesUp === 1 ? "işləyir" : probesUp == null ? "—" : "PROBLEM"),
                probesUp === 1 ? "ok" : probesUp == null ? "" : "crit"
            );
            html += card(
                "Celery worker",
                number(services.celery_workers),
                (services.celery_workers || 0) > 0 ? "ok" : "crit"
            );
            html += card(
                "Son backup",
                escapeHtml(formatDuration(services.backup_age_seconds)) + " <small>əvvəl</small>",
                services.backup_age_seconds != null && services.backup_age_seconds > 93600 ? "crit" : "ok"
            );
            html += card("Aktiv imtahanlar", number(exams.active_exams));
            html += card("İmtahandakı tələbələr", number(exams.students_in_exam));
            html += card(
                "Açıq insidentlər",
                number(data.incidents_open),
                (data.incidents_critical_open || 0) > 0 ? "crit" : (data.incidents_open || 0) > 0 ? "warn" : "ok"
            );
            html += card("Təhlükəsizlik (24s)", number(data.security_events_24h)) + "</div>";
            html += '<div class="smx-panel"><h4>Monitorinq hədəfləri (Prometheus job-ları)</h4><div>';
            Object.keys(data.targets || {}).sort().forEach(function (job) {
                html += '<span style="display:inline-block;margin:3px 14px 3px 0">' +
                    dot(data.targets[job]) + escapeHtml(job) + "</span>";
            });
            body.innerHTML = html + "</div></div>";
        }

        function renderServer(data) {
            var summary = data.summary || {};
            var chart = data.charts || {};
            var loadCapacity = summary.cores ? summary.load5 / summary.cores * 100 : null;
            var html = '<div class="smx-cards">';
            html += card("Uptime", escapeHtml(formatDuration(summary.uptime_seconds)));
            html += card("CPU nüvələri", number(summary.cores));
            html += card(
                "Load 1/5/15",
                number(summary.load1, 1) + " / " + number(summary.load5, 1) + " / " + number(summary.load15, 1)
            );
            html += card("Load doluluğu", percent(loadCapacity), statusClass(loadCapacity, 70, 90));
            html += card(
                "RAM",
                formatBytes(summary.mem_total && summary.mem_available ? summary.mem_total - summary.mem_available : null) +
                    " <small>/ " + formatBytes(summary.mem_total) + "</small>"
            );
            html += card(
                "Disk boş",
                formatBytes(summary.disk_free) + " <small>/ " + formatBytes(summary.disk_total) + "</small>"
            );
            html += card("Inode boş", percent(summary.inode_free_percent));
            html += card("Proseslər", number(summary.processes));
            html += card("Fayl deskriptorları", number(summary.file_descriptors)) + "</div>";
            html += chartGrid([
                ["CPU %", "smx-c-cpu"],
                ["RAM %", "smx-c-mem"],
                ["Swap %", "smx-c-swap"],
                ["Load (1 dəq)", "smx-c-load"],
                ["Disk istifadəsi %", "smx-c-disk"],
                ["Disk I/O %", "smx-c-io"],
                ["Node exporter şəbəkəsi (B/s) — RX/TX", "smx-c-net"],
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
                body.innerHTML = '<div class="smx-empty">Konteyner məlumatı yoxdur (cAdvisor işə düşməyib?)</div>';
                return;
            }
            var html = '<div class="smx-table-wrap"><table class="smx-table"><thead><tr>' +
                "<th></th><th>Konteyner</th><th>Uptime</th><th>CPU</th><th>RAM</th><th>Limit</th>" +
                "<th>Restart (24s)</th><th>OOM</th><th>RX/TX</th><th>Image</th></tr></thead><tbody>";
            rows.forEach(function (row) {
                html += "<tr><td>" + dot(row.alive) + "</td><td><b>" + escapeHtml(row.name) + "</b></td>" +
                    "<td>" + escapeHtml(formatDuration(row.uptime_seconds)) + "</td>" +
                    "<td>" + number(row.cpu_percent, 1) + "%</td>" +
                    "<td>" + formatBytes(row.memory_bytes) + "</td>" +
                    "<td>" + (row.memory_limit_bytes ? formatBytes(row.memory_limit_bytes) : "—") + "</td>" +
                    '<td style="' + (row.restarts_24h > 3 ? "color:var(--smx-crit);font-weight:700" : "") + '">' +
                    row.restarts_24h + "</td>" +
                    '<td style="' + (row.oom_events > 0 ? "color:var(--smx-crit);font-weight:700" : "") + '">' +
                    row.oom_events + "</td>" +
                    "<td>" + formatBytes(row.net_rx_bps) + "/s · " + formatBytes(row.net_tx_bps) + "/s</td>" +
                    '<td style="max-width:260px;overflow:hidden;text-overflow:ellipsis">' +
                    escapeHtml(row.image) + "</td></tr>";
            });
            body.innerHTML = html + "</tbody></table></div>" + pager(data, rows.length);
        }

        function topTable(title, rows, unit) {
            var html = '<div class="smx-panel" style="margin-top:12px"><h4>' + escapeHtml(title) + "</h4>";
            if (!rows || !rows.length) {
                return html + '<div class="smx-empty" style="padding:12px">Məlumat yoxdur</div></div>';
            }
            html += '<table class="smx-table"><tbody>';
            rows.forEach(function (row) {
                html += "<tr><td>" + escapeHtml(row.path) + '</td><td style="text-align:right">' +
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
                    key + (key === "2xx" ? " (15 dəq)" : ""),
                    number(value),
                    key === "5xx" ? ((value || 0) > 0 ? "warn" : "ok") : ""
                );
            });
            html += "</div>" + chartGrid([
                ["Sorğu axını (req/s)", "smx-a-rate"],
                ["5xx nisbəti %", "smx-a-err"],
                ["p95 gecikmə (s)", "smx-a-p95"],
                ["p99 gecikmə (s)", "smx-a-p99"],
            ]);
            html += topTable("Ən yavaş endpoint-lər (orta, 30 dəq)", summary.slow_endpoints, "s");
            html += topTable("Ən çox 5xx verən endpoint-lər (30 dəq)", summary.error_endpoints, "xəta");
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
                dot(summary.pg_up === 1) + (summary.pg_up === 1 ? "işləyir" : "DAYANIB"),
                summary.pg_up === 1 ? "ok" : "crit"
            );
            html += card(
                "Bağlantılar",
                number(summary.total_connections) + " <small>/ " + number(summary.max_connections) + "</small>",
                statusClass(summary.max_connections ? 100 * summary.total_connections / summary.max_connections : null, 80, 95)
            );
            html += card("Aktiv / Boşda", number(summary.active_connections) + " / " + number(summary.idle_connections));
            html += card(
                "Cache hit",
                percent(summary.cache_hit_ratio),
                summary.cache_hit_ratio != null && summary.cache_hit_ratio < 95 ? "warn" : "ok"
            );
            html += card("Baza ölçüsü", formatBytes(summary.db_size_bytes));
            html += card("Deadlock (1s)", number(summary.deadlocks_1h), (summary.deadlocks_1h || 0) > 0 ? "crit" : "ok");
            html += card("Temp fayllar (1s)", number(summary.temp_files_1h));
            html += card(
                "Backup yaşı",
                escapeHtml(formatDuration(summary.backup_age_seconds)),
                summary.backup_age_seconds != null && summary.backup_age_seconds > 93600 ? "crit" : "ok"
            );
            html += "</div><h4 style='margin:6px 0;color:var(--smx-navy)'>" +
                "PgBouncer (session mode — RLS üçün dəyişdirilmir)</h4>";
            html += '<div class="smx-cards">';
            html += card("Aktiv klientlər", number(summary.pgbouncer_active_clients));
            html += card(
                "Gözləyən klientlər",
                number(summary.pgbouncer_waiting_clients),
                (summary.pgbouncer_waiting_clients || 0) > 0 ? "warn" : "ok"
            );
            html += card("Aktiv server bağlantıları", number(summary.pgbouncer_active_servers));
            html += card("Boş server bağlantıları", number(summary.pgbouncer_idle_servers));
            html += card("Max gözləmə", number(summary.pgbouncer_max_wait_seconds, 2) + " <small>s</small>");
            html += "</div>" + chartGrid([
                ["Bağlantı sayı", "smx-d-conn"],
                ["Tranzaksiya/s", "smx-d-tps"],
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
                dot(summary.redis_up === 1) + (summary.redis_up === 1 ? "işləyir" : "DAYANIB"),
                summary.redis_up === 1 ? "ok" : "crit"
            );
            html += card(
                "Yaddaş",
                formatBytes(summary.redis_memory_used) +
                    (summary.redis_memory_max ? " <small>/ " + formatBytes(summary.redis_memory_max) + "</small>" : "")
            );
            html += card("Klientlər", number(summary.redis_clients));
            html += card("Bloklanmış", number(summary.redis_blocked), (summary.redis_blocked || 0) > 10 ? "warn" : "ok");
            html += card("Hit nisbəti", percent(summary.redis_hit_ratio));
            html += card(
                "Evicted (cəmi)",
                number(summary.redis_evicted_total),
                (summary.redis_evicted_total || 0) > 0 ? "crit" : "ok"
            );
            html += card(
                "Celery worker",
                number(summary.celery_workers_online),
                (summary.celery_workers_online || 0) > 0 ? "ok" : "crit"
            );
            html += card(
                "Aktiv / Reserved",
                number(summary.celery_active_tasks) + " / " + number(summary.celery_reserved_tasks)
            );
            html += card(
                "Növbə uzunluğu",
                number(summary.celery_queue_length),
                (summary.celery_queue_length || 0) > 200 ? "warn" : "ok"
            );
            html += card(
                "Statistika yaşı",
                escapeHtml(formatDuration(summary.celery_stats_age_seconds)),
                summary.celery_stats_age_seconds != null && summary.celery_stats_age_seconds > 300 ? "crit" : "ok"
            );
            html += "</div>" + chartGrid([
                ["Redis yaddaş (B)", "smx-r-mem"],
                ["Redis əmr/s", "smx-r-ops"],
                ["Celery növbəsi", "smx-r-q"],
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
                "Metrik servisi əlçatmazdır — yalnız baza sayğacları göstərilir.</div>" : "";
            html += '<div class="smx-cards">';
            html += card("Aktiv imtahanlar", number(database.active_exams));
            html += card("Hazırda imtahanda", number(database.in_progress_attempts));
            html += card("Bu gün təhvil verilən", number(database.submitted_today));
            html += card("PIN cəhdləri (1s)", number(counters.pin_attempts_1h));
            html += card(
                "Uğursuz PIN (1s)",
                number(counters.pin_failures_1h),
                (counters.pin_failures_1h || 0) > 20 ? "warn" : "ok"
            );
            html += card(
                "Autosave xətaları (1s)",
                number(counters.autosave_errors_1h),
                (counters.autosave_errors_1h || 0) > 0 ? "warn" : "ok"
            );
            html += card("Nəzarət insidentləri (1s)", number(counters.supervision_incidents_1h)) + "</div>";
            if (data.charts) {
                html += chartGrid([
                    ["Cəhd başlanğıcları (15 dəq pəncərə)", "smx-e-start"],
                    ["Təhvillər", "smx-e-sub"],
                    ["Autosave xətaları", "smx-e-as"],
                    ["Uğursuz PIN cəhdləri", "smx-e-pin"],
                ]);
            }
            html += '<p style="color:#8a97a8;font-size:12px;margin-top:10px">' +
                "Yalnız aqreqat statistika göstərilir — sual, cavab, PIN və şəxsi məlumat bu modulda YOXDUR.</p>";
            body.innerHTML = html;
            if (data.charts) {
                lineChart("smx-e-start", chart.attempt_starts);
                lineChart("smx-e-sub", chart.submissions);
                lineChart("smx-e-as", chart.autosave_failures);
                lineChart("smx-e-pin", chart.pin_failures);
            }
        }

        function renderSecurity(data) {
            var state = states["security-events"];
            var rows = rowsFrom(data, "events");
            var html = '<div class="smx-filter"><select id="smx-sec-type">' +
                '<option value="">Bütün hadisələr</option>' +
                '<option value="login_failed"' + selected("login_failed", state.type) + '>Uğursuz giriş</option>' +
                '<option value="login_brute_force"' + selected("login_brute_force", state.type) + '>Brute-force</option>' +
                '<option value="superadmin_login"' + selected("superadmin_login", state.type) + '>Superadmin girişi</option>' +
                '<option value="superadmin_login_failed"' + selected("superadmin_login_failed", state.type) +
                '>Superadmin uğursuz girişi</option>' +
                '<option value="unauthorized_monitoring"' + selected("unauthorized_monitoring", state.type) +
                '>İcazəsiz monitorinq</option></select></div>';
            if (!rows.length) {
                body.innerHTML = html + '<div class="smx-empty">Təhlükəsizlik hadisəsi yoxdur</div>';
                return;
            }
            html += '<div class="smx-table-wrap"><table class="smx-table"><thead><tr>' +
                "<th>Vaxt</th><th>Hadisə</th><th>Önəm</th><th>İstifadəçi</th><th>IP</th><th>Say</th><th>Mesaj</th>" +
                "</tr></thead><tbody>";
            rows.forEach(function (row) {
                html += "<tr><td>" + escapeHtml(new Date(row.last_seen).toLocaleString("az")) + "</td><td>" +
                    escapeHtml(row.event_type_display) + "</td><td>" + pill(row.severity, row.severity) + "</td><td>" +
                    escapeHtml(row.user || "—") + "</td><td>" + escapeHtml(row.ip || "—") + "</td><td>" + row.count +
                    '</td><td style="white-space:normal">' + escapeHtml(row.message) + "</td></tr>";
            });
            body.innerHTML = html + "</tbody></table></div>" + pager(data, rows.length);
        }

        function renderLogs(data) {
            var state = states.logs;
            var rows = rowsFrom(data, "lines");
            var containers = data.containers || [];
            var html = '<div class="smx-filter"><select id="smx-log-container">' +
                '<option value="">Bütün konteynerlər</option>' + containers.map(function (name) {
                    return '<option value="' + escapeHtml(name) + '"' + selected(name, state.container) + ">" +
                        escapeHtml(name) + "</option>";
                }).join("") + '</select><select id="smx-log-level"><option value="">Bütün səviyyələr</option>' +
                '<option value="error"' + selected("error", state.level) + '>error</option>' +
                '<option value="warning"' + selected("warning", state.level) + '>warning</option>' +
                '<option value="critical"' + selected("critical", state.level) + '>critical</option></select>' +
                '<input type="text" id="smx-log-q" placeholder="Mətn axtarışı…" maxlength="120" value="' +
                escapeHtml(state.q) + '"><button type="button" class="smx-btn" id="smx-log-go">' +
                '<i class="fas fa-search"></i> Axtar</button></div>';
            if (!rows.length) {
                body.innerHTML = html + '<div class="smx-empty">Log tapılmadı</div>';
                return;
            }
            html += '<div class="smx-table-wrap"><table class="smx-table"><tbody>';
            rows.forEach(function (row) {
                html += '<tr><td style="color:#8a97a8">' +
                    escapeHtml(new Date(row.ts).toLocaleTimeString("az")) + "</td><td><b>" +
                    escapeHtml(row.container) + '</b></td><td class="smx-log" style="white-space:normal">' +
                    escapeHtml(row.line) + "</td></tr>";
            });
            body.innerHTML = html + "</tbody></table></div>" + pager(data, rows.length);
        }

        function renderAlerts(data) {
            var rows = data.alerts || [];
            if (!rows.length) {
                body.innerHTML = '<div class="smx-empty">Aktiv alert yoxdur</div>';
                return;
            }
            var html = '<div class="smx-table-wrap"><table class="smx-table"><thead><tr>' +
                "<th>Alert</th><th>Önəm</th><th>Vəziyyət</th><th>Başlayıb</th><th>Xülasə</th>" +
                "</tr></thead><tbody>";
            rows.forEach(function (row) {
                html += "<tr><td><b>" + escapeHtml(row.name) + "</b></td><td>" +
                    pill(row.severity || "—", row.severity || "info") + "</td><td>" + escapeHtml(row.state) +
                    (row.silenced ? " " + pill("susdurulub", "silenced") : "") + "</td><td>" +
                    escapeHtml(row.starts_at ? new Date(row.starts_at).toLocaleString("az") : "—") +
                    '</td><td style="white-space:normal">' + escapeHtml(row.summary) + "</td></tr>";
            });
            body.innerHTML = html + "</tbody></table></div>";
        }

        function renderIncidents(data) {
            var state = states.incidents;
            var rows = rowsFrom(data, "incidents");
            var html = '<div class="smx-filter"><select id="smx-inc-status">' +
                '<option value="open"' + selected("open", state.status) + '>Açıq olanlar</option>' +
                '<option value=""' + selected("", state.status) + '>Hamısı</option>' +
                '<option value="resolved"' + selected("resolved", state.status) + '>Həll olunub</option>' +
                '<option value="silenced"' + selected("silenced", state.status) + '>Susdurulub</option></select></div>';
            if (!rows.length) {
                body.innerHTML = html + '<div class="smx-empty">İnsident yoxdur</div>';
                return;
            }
            html += '<div class="smx-table-wrap"><table class="smx-table"><thead><tr>' +
                "<th>Başlıq</th><th>Önəm</th><th>Status</th><th>Servis</th><th>Başlayıb</th><th>Müddət</th>" +
                "<th>Əməliyyat</th></tr></thead><tbody>";
            rows.forEach(function (row) {
                var actions = row.status === "resolved" ? "" : '<span class="smx-actions">' +
                    '<button data-inc="' + row.id + '" data-act="acknowledge">Qəbul et</button>' +
                    '<button data-inc="' + row.id + '" data-act="resolve">Həll olundu</button>' +
                    '<button data-inc="' + row.id + '" data-act="silence">Susdur</button></span>';
                html += '<tr><td style="white-space:normal"><b>' + escapeHtml(row.title) + "</b>" +
                    (row.resolution_note ? '<div style="color:#8a97a8;font-size:12px">' +
                        escapeHtml(row.resolution_note) + "</div>" : "") +
                    "</td><td>" + pill(row.severity, row.severity) + "</td><td>" +
                    pill(row.status, row.status) + "</td><td>" + escapeHtml(row.service || "—") + "</td><td>" +
                    escapeHtml(row.started_at ? new Date(row.started_at).toLocaleString("az") : "—") + "</td><td>" +
                    escapeHtml(formatDuration(row.duration_seconds)) + "</td><td>" + actions + "</td></tr>";
            });
            body.innerHTML = html + "</tbody></table></div>" + pager(data, rows.length);
        }

        return {
            overview: renderOverview,
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
