/* system_monitoring_summary.js — «Ümumi vəziyyət» tabı (sahib 2026-10-01).
 *
 * Texniki olmayan oxucu (RİM rəhbəri) üçün bir baxışda server: status banneri
 * (səbəb + «nə etməli»), əsas faktlar, trafik/xətalar, xidmətlər, resurslar,
 * imtahan fəaliyyəti, təhlükəsizlik, ehtiyat nüsxələr, son insidentlər.
 * Bütün insan mətnləri ya serverdən (pgettext), ya da `#smx-i18n` JSON adasından
 * gəlir; bütün dəyərlər `escapeHtml`-dən keçir. Inline `style` YOXDUR — faiz
 * zolaqlarının eni render-dən SONRA CSSOM ilə (`el.style.width`) qoyulur.
 * Yükləmə sırası fail-soft: əsas fayl `namespace.summary` yoxdursa sadə mesaj göstərir.
 */
(function () {
    "use strict";

    var namespace = window.EMSSystemMonitoring = window.EMSSystemMonitoring || {};

    var STATE_TONE = { ok: "ok", warning: "warning", problem: "problem", unknown: "unknown" };
    var SEVERITY_TONE = { critical: "danger", high: "danger", medium: "warning", warning: "warning", low: "info", info: "info" };
    var LEVEL_ICON = { ok: "fa-circle-check", warning: "fa-triangle-exclamation", problem: "fa-circle-exclamation" };

    function render(body, data, ctx) {
        var t = ctx.t;
        var fmt = ctx.fmt;
        var esc = ctx.escapeHtml;
        var dur = ctx.formatDuration;

        function num(value, digits) {
            if (value == null || isNaN(value)) return "—";
            var number = Number(value);
            return digits ? number.toFixed(digits) : Math.round(number).toLocaleString("az");
        }

        function ago(seconds) {
            return seconds == null ? t("state_unknown") : fmt(t("ago"), { age: dur(seconds) });
        }

        function stateBadge(state) {
            var tone = STATE_TONE[state] || "unknown";
            return '<span class="smx-state smx-state--' + tone + '"><span class="smx-state__dot" aria-hidden="true"></span>' +
                esc(t("state_" + tone)) + "</span>";
        }

        function gotoButton(tab) {
            if (!tab) return "";
            return '<button type="button" class="smx-link" data-smx-goto="' + esc(tab) + '">' + esc(t("details")) +
                ' <i class="fas fa-arrow-right" aria-hidden="true"></i></button>';
        }

        function box(title, icon, inner, options) {
            options = options || {};
            return '<section class="smx-box' + (options.wide ? " smx-box--wide" : "") + '">' +
                '<header class="smx-box__head"><h4 class="smx-box__title"><i class="fas ' + icon +
                '" aria-hidden="true"></i>' + esc(title) + "</h4>" + gotoButton(options.tab) + "</header>" +
                '<div class="smx-box__body">' + inner + "</div></section>";
        }

        function kpi(label, value, note, tone) {
            return '<div class="ems-kpi smx-kpi' + (tone ? " smx-kpi--" + tone : "") + '">' +
                '<div class="ems-kpi__label">' + esc(label) + "</div>" +
                '<div class="ems-kpi__value">' + value + "</div>" +
                (note ? '<div class="ems-kpi__note">' + esc(note) + "</div>" : "") + "</div>";
        }

        function empty() {
            return '<p class="smx-muted">' + esc(t("emptyData")) + "</p>";
        }

        // ── 1. Status banneri ────────────────────────────────────────────
        function hero() {
            var health = data.health || {};
            var level = health.level || "ok";
            var reasons = (health.reasons || []).map(function (item) {
                return '<li class="smx-reason smx-reason--' + esc(item.level) + '">' +
                    '<span class="smx-reason__badge">' + esc(t("level_" + item.level)) + "</span>" +
                    '<div class="smx-reason__text"><p>' + esc(item.text) + "</p>" +
                    (item.hint ? '<p class="smx-reason__hint"><b>' + esc(t("whatToDo")) + "</b> " + esc(item.hint) + "</p>" : "") +
                    "</div>" + gotoButton(item.tab) + "</li>";
            }).join("");
            var generated = data.generated_at ? new Date(data.generated_at).toLocaleTimeString("az") : "";
            // Canlı region YOX: 30 s-lik avto-yeniləmə ekran oxuyucuya bütün paneli təkrar oxutmasın.
            return '<section class="smx-hero smx-hero--' + esc(level) + '" aria-label="' + esc(t("overall")) + '">' +
                '<div class="smx-hero__icon" aria-hidden="true"><i class="fas ' + (LEVEL_ICON[level] || LEVEL_ICON.ok) + '"></i></div>' +
                '<div class="smx-hero__main">' +
                '<div class="smx-hero__eyebrow">' + esc(t("overall")) + (generated ? " · " + esc(fmt(t("updated"), { time: generated })) : "") + "</div>" +
                '<h3 class="smx-hero__title">' + esc(health.title || "") + "</h3>" +
                '<p class="smx-hero__summary">' + esc(health.summary || "") + "</p>" +
                (reasons ? '<ul class="smx-reasons">' + reasons + "</ul>" : "") +
                "</div>" +
                '<div class="smx-hero__actions" data-smx-ai-actions></div>' +
                "</section>" +
                '<div data-smx-ai-panel aria-live="polite"></div>';
        }

        // ── 2. Əsas faktlar ─────────────────────────────────────────────
        function facts() {
            var platform = data.platform || {};
            var users = data.users || {};
            var exams = data.exams || {};
            var built = platform.built_at ? new Date(platform.built_at) : null;
            var builtAgo = built && !isNaN(built) ? (Date.now() - built.getTime()) / 1000 : null;
            return '<div class="ems-kpis smx-kpis">' +
                kpi(t("kpiVersion"), '<span class="smx-mono">' + esc(platform.version || "—") + "</span>", platform.sha && platform.sha !== platform.version ? platform.sha : "") +
                kpi(t("kpiDeploy"), esc(builtAgo == null ? "—" : ago(builtAgo)), built && !isNaN(built) ? built.toLocaleString("az") : "") +
                kpi(t("kpiUptime"), esc(platform.server_uptime_seconds == null ? "—" : dur(platform.server_uptime_seconds)), "") +
                kpi(t("kpiSessions"), num(users.active_sessions_15m), t("kpiSessionsNote")) +
                kpi(t("kpiLogins"), num(users.logins_today), fmt(t("kpiLoginsNote"), { count: num(users.logins_1h) })) +
                kpi(t("kpiExam"), num(exams.open_attempts), fmt(t("kpiExamNote"), { count: num(exams.active_exams) }), exams.open_attempts ? "live" : "") +
                "</div>";
        }

        // ── 3. Trafik ──────────────────────────────────────────────────
        function traffic() {
            var info = data.traffic || {};
            var rows = (info.windows || []).map(function (row) {
                var tone = row.error_pct == null ? "" : row.error_pct >= 5 ? "is-problem" : row.error_pct >= 1 ? "is-warning" : "";
                return "<tr><th scope=\"row\">" + esc(row.label) + "</th><td>" + num(row.requests) + "</td><td>" +
                    num(row.errors) + '</td><td class="' + tone + '">' +
                    (row.error_pct == null ? "—" : esc(num(row.error_pct, 2)) + "%") + "</td></tr>";
            }).join("");
            var series = info.series || {};
            var hasSeries = (series.requests || []).length > 0 || (series.errors || []).length > 0;
            var inner = '<div class="smx-table-wrap"><table class="smx-mini-table"><thead><tr><th scope="col">' + esc(t("colWindow")) +
                '</th><th scope="col">' + esc(t("colRequests")) + '</th><th scope="col">' + esc(t("colErrors")) +
                '</th><th scope="col">' + esc(t("colErrorPct")) + "</th></tr></thead><tbody>" + rows + "</tbody></table></div>" +
                '<div class="smx-inline-stats"><span>' + esc(t("p95")) + ": <b>" +
                (info.p95_ms == null ? "—" : esc(num(info.p95_ms)) + " ms") + "</b></span><span>" + esc(t("rps")) + ": <b>" +
                (info.rps == null ? "—" : esc(num(info.rps, 2)) + " " + esc(t("rpsUnit"))) + "</b></span></div>" +
                (hasSeries ? '<p class="smx-box__caption">' + esc(t("chartTitle")) + "</p>" +
                    '<div class="smx-chart smx-chart--sm"><canvas id="smx-s-traffic"></canvas>' +
                    '<div class="smx-chart-empty" hidden>' + esc(t("emptyData")) + "</div></div>" : "");
            return box(t("trafficTitle"), "fa-chart-line", inner, { wide: true, tab: "application" });
        }

        // ── 4. Xidmətlər ───────────────────────────────────────────────
        function serviceDetail(row) {
            var extra = row.extra || {};
            var value = row.value;
            var parts = [];
            if (row.unit === "ms" && value != null) parts.push(num(value, value < 10 ? 1 : 0) + " ms");
            if (row.unit === "waiting" && value != null) parts.push(num(value) + " " + t("unit_waiting"));
            if (row.unit === "workers" && value != null) parts.push(num(value) + " " + t("unit_workers"));
            if (row.unit === "age" && value != null) parts.push(fmt(t("unit_age"), { age: dur(value) }));
            if (row.unit === "days" && value != null) parts.push(fmt(t("unit_days"), { count: num(value) }));
            if (row.unit === "down_jobs" && value) parts.push(fmt(t("unit_down_jobs"), { count: num(value) }));
            if (extra.queue != null) parts.push(fmt(t("queue"), { count: num(extra.queue) }));
            if (extra.connections != null && extra.max_connections != null) {
                parts.push(fmt(t("connections"), { used: num(extra.connections), max: num(extra.max_connections) }));
            }
            return parts.join(" · ");
        }

        function services() {
            var rows = (data.services || []).map(function (row) {
                return '<li class="smx-list__row"><div class="smx-list__main"><span class="smx-list__name">' + esc(row.label) +
                    '</span><span class="smx-list__detail">' + esc(serviceDetail(row)) + "</span></div>" +
                    stateBadge(row.state) + "</li>";
            }).join("");
            return box(t("servicesTitle"), "fa-server", rows ? '<ul class="smx-list">' + rows + "</ul>" : empty(), { tab: "database" });
        }

        // ── 5. Resurslar ───────────────────────────────────────────────
        function meter(label, value, warn, crit, note) {
            var tone = value == null ? "unknown" : value >= crit ? "problem" : value >= warn ? "warning" : "ok";
            return '<div class="smx-meter smx-meter--' + tone + '"><div class="smx-meter__head"><span>' + esc(label) +
                "</span><b>" + (value == null ? "—" : esc(num(value, 1)) + "%") + "</b></div>" +
                '<div class="smx-meter__track"><div class="smx-meter__fill" data-smx-pct="' +
                (value == null ? 0 : Math.max(0, Math.min(100, Number(value)))) + '"></div></div>' +
                (note ? '<div class="smx-meter__note">' + esc(note) + "</div>" : "") + "</div>";
        }

        function resources() {
            var res = data.resources || {};
            var diskNote = res.disk_free_bytes != null && res.disk_total_bytes != null ?
                fmt(t("diskFree"), { free: ctx.formatBytes(res.disk_free_bytes), total: ctx.formatBytes(res.disk_total_bytes) }) : "";
            var inner = meter(t("cpu"), res.cpu_pct, 85, 95) + meter(t("ram"), res.mem_pct, 90, 95) +
                meter(t("disk"), res.disk_pct, 85, 95, diskNote) +
                '<dl class="smx-facts">' +
                "<div><dt>" + esc(t("containersAlive")) + "</dt><dd>" + num(res.containers_alive) + "</dd></div>" +
                '<div class="' + ((res.restarts_24h || 0) > 5 ? "is-warning" : "") + '"><dt>' + esc(t("restarts")) + "</dt><dd>" + num(res.restarts_24h) + "</dd></div>" +
                '<div class="' + ((res.oom_24h || 0) > 0 ? "is-warning" : "") + '"><dt>' + esc(t("oom")) + "</dt><dd>" + num(res.oom_24h) + "</dd></div>" +
                "</dl>";
            return box(t("resourcesTitle"), "fa-microchip", inner, { tab: "server" });
        }

        // ── 6. İmtahan fəaliyyəti ───────────────────────────────────────
        function exams() {
            var ex = data.exams || {};
            var busy = ex.open_attempts > 0 || ex.live_running > 0;
            var inner = (busy ? '<p class="smx-callout"><i class="fas fa-circle-info" aria-hidden="true"></i> ' + esc(t("examsBusy")) + "</p>" : "") +
                '<dl class="smx-facts smx-facts--grid">' +
                "<div><dt>" + esc(t("openAttempts")) + "</dt><dd>" + num(ex.open_attempts) + "<small>" + esc(fmt(t("openRecent"), { count: num(ex.open_recent) })) + "</small></dd></div>" +
                "<div><dt>" + esc(t("activeExams")) + "</dt><dd>" + num(ex.active_exams) + "</dd></div>" +
                "<div><dt>" + esc(t("started15")) + "</dt><dd>" + num(ex.started_15m) + "</dd></div>" +
                "<div><dt>" + esc(t("finished15")) + "</dt><dd>" + num(ex.finished_15m) + "</dd></div>" +
                "<div><dt>" + esc(t("liveActive")) + "</dt><dd>" + num(ex.live_active) + "<small>" + esc(fmt(t("liveRunning"), { count: num(ex.live_running) })) + "</small></dd></div>" +
                '<div class="' + ((ex.autosave_errors_1h || 0) > 0 ? "is-warning" : "") + '"><dt>' + esc(t("autosaveErrors")) + "</dt><dd>" + num(ex.autosave_errors_1h) + "</dd></div>" +
                "<div><dt>" + esc(t("pinFailures")) + "</dt><dd>" + num(ex.pin_failures_1h) + "</dd></div>" +
                "</dl>";
            return box(t("examsTitle"), "fa-file-signature", inner, { tab: "exams" });
        }

        // ── 7. Təhlükəsizlik ───────────────────────────────────────────
        function security() {
            var rows = ((data.security || {}).rows || []).map(function (row) {
                return '<tr class="' + (row.state === "warning" ? "is-warning" : "") + '"><th scope="row">' + esc(row.label) +
                    "</th><td>" + num(row.h24) + "</td><td>" + num(row.d7) + "</td></tr>";
            }).join("");
            var inner = '<div class="smx-table-wrap"><table class="smx-mini-table smx-mini-table--labels"><thead><tr><th scope="col">' +
                esc(t("colEvent")) + '</th><th scope="col">' + esc(t("col24h")) + '</th><th scope="col">' + esc(t("col7d")) +
                "</th></tr></thead><tbody>" + rows + "</tbody></table></div>";
            return box(t("securityTitle"), "fa-shield-halved", inner, { tab: "security-events" });
        }

        // ── 8. Ehtiyat nüsxələr ────────────────────────────────────────
        function backups() {
            var rows = (data.backups || []).map(function (row) {
                return '<li class="smx-list__row"><div class="smx-list__main"><span class="smx-list__name">' + esc(row.label) +
                    '</span><span class="smx-list__detail">' + esc(row.age_seconds == null ? t("state_unknown") : ago(row.age_seconds)) +
                    "</span></div>" + stateBadge(row.state) + "</li>";
            }).join("");
            return box(t("backupsTitle"), "fa-box-archive", '<ul class="smx-list">' + rows + "</ul>", { tab: "database" });
        }

        // ── 9. Son insidentlər ─────────────────────────────────────────
        function incidents() {
            var info = data.incidents || {};
            var groups = info.groups || [];
            if (!groups.length) {
                return box(t("incidentsTitle"), "fa-clock-rotate-left", '<p class="smx-muted smx-ok-line"><i class="fas fa-circle-check" aria-hidden="true"></i> ' +
                    esc(t("incidentsEmpty")) + "</p>", { tab: "incidents" });
            }
            var items = groups.map(function (group) {
                var started = group.last_started_at ? new Date(group.last_started_at) : null;
                var when = started && !isNaN(started) ? ago((Date.now() - started.getTime()) / 1000) : "";
                var tone = group.open ? (SEVERITY_TONE[group.severity] || "warning") : "muted";
                var meta = [fmt(t("times"), { count: group.count }), group.open ? t("stillOpen") : t("resolved")];
                if (group.last_duration_seconds != null) meta.push(fmt(t("lasted"), { duration: dur(group.last_duration_seconds) }));
                return '<li class="ems-tl__item' + (group.open ? " ems-tl__item--current" : "") + '">' +
                    '<div class="ems-tl__gutter" aria-hidden="true"><span class="ems-tl__dot ems-tl__dot--' + tone +
                    '"></span><span class="ems-tl__line"></span></div><div class="ems-tl__main"><div class="ems-tl__head">' +
                    '<span class="ems-tl__who">' + esc(group.title) + '</span><span class="ems-tl__when">' + esc(when) +
                    '</span></div><div class="ems-tl__what">' + esc(meta.join(" · ")) + "</div></div></li>";
            }).join("");
            var head = info.open ? '<p class="smx-box__caption">' + esc(fmt(t("openCount"), { count: info.open })) + "</p>" : "";
            return box(t("incidentsTitle"), "fa-clock-rotate-left", head + '<ol class="ems-tl smx-tl">' + items + "</ol>", { tab: "incidents" });
        }

        // ── 10. Səhifələr ──────────────────────────────────────────────
        function endpointTable(rows, unit) {
            if (!rows || !rows.length) return empty();
            return '<ol class="smx-endpoints">' + rows.map(function (row) {
                return '<li><code class="smx-endpoints__path">' + esc(row.path) + "</code><b>" + esc(num(row.value)) + " " + esc(unit) + "</b></li>";
            }).join("") + "</ol>";
        }

        function endpoints() {
            var info = data.endpoints || {};
            return box(t("slowTitle"), "fa-hourglass-half", endpointTable(info.slow, "ms"), { tab: "application" }) +
                box(t("errorsTitle"), "fa-bug", endpointTable(info.errors, t("errorsUnit")), { tab: "logs" });
        }

        // Metrik stek dayananda ayrıca banner YOX — səbəb artıq status bannerindədir
        // («metrics_down»); boş kartlar isə «—» / «Məlumat yoxdur» göstərir.
        var scope = data.scope || {};
        body.innerHTML = '<div class="smx-sum">' + hero() + facts() +
            '<div class="smx-grid">' + traffic() + services() + resources() + exams() + security() + backups() +
            incidents() + endpoints() + "</div>" +
            '<p class="smx-foot"><i class="fas fa-user-shield" aria-hidden="true"></i> ' + esc(t("note")) +
            (scope.platform ? "" : " " + esc(t("scopeOrg"))) + "</p></div>";

        body.querySelectorAll("[data-smx-pct]").forEach(function (fill) {
            fill.style.width = Number(fill.getAttribute("data-smx-pct") || 0) + "%";
        });
        var series = (data.traffic || {}).series || {};
        ctx.lineChart("smx-s-traffic", [
            { label: t("chartRequests"), points: series.requests || [] },
            { label: t("chartErrors"), points: series.errors || [] },
        ]);
        if (namespace.ai && typeof namespace.ai.mount === "function") {
            namespace.ai.mount(body, data.ai || {}, ctx);
        }
    }

    namespace.summary = { render: render };

    if (typeof namespace.bootPending === "function") {
        namespace.bootPending();
    }
})();
