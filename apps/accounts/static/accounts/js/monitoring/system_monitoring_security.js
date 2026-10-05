/* system_monitoring_security.js — «Təhlükəsizlik» tabı: hadisələr + IP filtri (sahib 2026-10-05).
 *
 * Sahib bir IP yazıb (i) həmin IP-dən gələn təhlükəsizlik hadisələrini, (ii) həmin IP-dən KİMİN
 * uğurla daxil olduğunu görmək istəyir. Filtr zolağı: hadisə tipi (layihənin stilli select-i) +
 * IP sahəsi («Axtar» / Enter, «×» təmizləyir; şəbəkə də olar: 5.191.0.0/16). IP aktivdirsə API
 * `data.logins` qaytarır → «Bu IP-dən uğurlu girişlər» bloku (IP + hesab + cihaz qrupları, ən son
 * 50). Cədvəldəki IP xanaları düymədir — basanda həmin IP filtr olur. Yanlış IP → API 400 →
 * controller `data.invalid` ötürür → xəta sahənin altında göstərilir, zolaq itmir.
 *
 * Təhlükəsizlik: istifadəçi adı / user-agent / IP TAM escape olunur (`& < > " '` — atributlar da:
 * user-agent `title`-dadır və onu hücumçu idarə edir). Inline `style` YOXDUR.
 * AJAX-safe: hadisələr `body` üzərində delegasiyadır, hər `body` üçün BİR dəfə bağlanır; handler-lər
 * son render kontekstini `WeakMap`-dən oxuyur. Avto-yeniləmə (60 s) sahəyə yazılan, hələ tətbiq
 * olunmamış mətni və fokusu silmir. Renderer `system_monitoring_renderers.js`-dən çağırılır.
 */
(function () {
    "use strict";

    var namespace = window.EMSSystemMonitoring = window.EMSSystemMonitoring || {};
    var TAB = "security-events";
    var MAX_LENGTH = 64;
    var REFOCUS_WINDOW_MS = 15000;
    var contexts = new WeakMap();
    var refocusAt = new WeakMap();
    var bound = new WeakSet();

    // /jsi18n/ kataloqu base.html-də bu fayldan SONRA yüklənir — hər çağırışda oxu (renderers.js kimi).
    function gettext(text) {
        return window.gettext ? window.gettext(text) : text;
    }

    function esc(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    /** `#smx-i18n` mətni (`t()`), `{ad}` yer tutucuları doldurulmuş (`fmt()`); escape ÇAĞIRANDADIR. */
    function text(ctx, key, values) {
        var value = ctx.t(key);
        return values && typeof ctx.fmt === "function" ? ctx.fmt(value, values) : value;
    }

    function when(iso) {
        return iso ? new Date(iso).toLocaleString("az") : "—";
    }

    function ipCell(ip, ctx, activeIp) {
        if (!ip) return "—";
        if (ip === activeIp) return '<span class="smx-iplink is-active">' + esc(ip) + "</span>";
        var label = text(ctx, "ipFilterBy", { ip: ip });
        return '<button type="button" class="smx-iplink" data-smx-ip="' + esc(ip) + '" title="' + esc(label) +
            '" aria-label="' + esc(label) + '">' + esc(ip) + "</button>";
    }

    function filterBar(state, invalid, ctx) {
        var value = state.ip || "";
        return '<div class="smx-filter">' + namespace.format.selectMarkup('id="smx-sec-type"', [
            ["", gettext("Bütün hadisələr")],
            ["login_failed", gettext("Uğursuz giriş")],
            ["login_brute_force", "Brute-force"],
            ["superadmin_login", gettext("Superadmin girişi")],
            ["superadmin_login_failed", gettext("Superadmin uğursuz girişi")],
            ["unauthorized_monitoring", gettext("İcazəsiz monitorinq")],
        ], state.type, ctx.t("allEvents")) +
            '<div class="smx-ipfilter" role="group" aria-label="' + esc(ctx.t("ipLabel")) + '">' +
            '<span class="smx-ipfilter__field"><input type="text" class="ems-input smx-ipfilter__input" id="smx-sec-ip"' +
            ' maxlength="' + MAX_LENGTH + '" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="' +
            esc(ctx.t("ipLabel")) + '" placeholder="' + esc(ctx.t("ipPlaceholder")) + '" value="' + esc(value) + '"' +
            (invalid ? ' aria-invalid="true" aria-describedby="smx-sec-ip-error"' : "") + ">" +
            '<button type="button" class="smx-ipfilter__clear" id="smx-sec-ip-clear" title="' + esc(ctx.t("ipClear")) +
            '" aria-label="' + esc(ctx.t("ipClear")) + '"' + (value ? "" : " hidden") + ">" +
            '<i class="fas fa-xmark" aria-hidden="true"></i></button></span>' +
            '<button type="button" class="smx-btn" id="smx-sec-ip-go"><i class="fas fa-search" aria-hidden="true"></i> ' +
            esc(gettext("Axtar")) + "</button></div></div>" +
            (invalid ? '<p class="smx-ipfilter__error" id="smx-sec-ip-error" role="alert">' +
                '<i class="fas fa-circle-exclamation" aria-hidden="true"></i> ' + esc(invalid) + "</p>" : "");
    }

    function loginsBlock(logins, filter, ctx) {
        var network = Boolean(filter && filter.kind === "network");
        var items = Array.isArray(logins.items) ? logins.items : [];
        var html = '<section class="smx-panel smx-logins" aria-labelledby="smx-logins-title">' +
            '<header class="smx-logins__head"><h4 class="smx-logins__title" id="smx-logins-title">' +
            '<i class="fas fa-right-to-bracket" aria-hidden="true"></i> ' +
            esc(ctx.t(network ? "loginsTitleNet" : "loginsTitle")) +
            (filter && filter.normalized ? ' <code class="smx-logins__query">' + esc(filter.normalized) + "</code>" : "") +
            "</h4>" + (items.length ? '<span class="smx-logins__meta">' +
                esc(text(ctx, "loginsMeta", { logins: logins.total, accounts: logins.accounts })) + "</span>" : "") +
            "</header>";
        if (!items.length) {
            html += '<div class="smx-empty smx-empty--compact">' +
                esc(ctx.t(network ? "loginsEmptyNet" : "loginsEmpty")) + "</div>";
        } else {
            html += '<div class="smx-table-wrap"><table class="smx-table"><thead><tr><th>' + esc(ctx.t("colLastLogin")) +
                "</th><th>" + esc(gettext("İstifadəçi")) + "</th>" + (network ? "<th>IP</th>" : "") +
                "<th>" + esc(ctx.t("colDevice")) + "</th><th>" + esc(gettext("Say")) + "</th></tr></thead><tbody>";
            items.forEach(function (row) {
                var first = row.count > 1 && row.first_seen && row.first_seen !== row.last_seen ?
                    '<span class="smx-logins__sub">' + esc(text(ctx, "firstSeen", { time: when(row.first_seen) })) +
                    "</span>" : "";
                html += "<tr><td>" + esc(when(row.last_seen)) + first + "</td><td>" +
                    (row.user ? "<b>" + esc(row.user) + "</b>" : "—") +
                    (row.full_name ? '<span class="smx-logins__sub">' + esc(row.full_name) + "</span>" : "") + "</td>" +
                    (network ? "<td>" + ipCell(row.ip, ctx, "") + "</td>" : "") +
                    '<td><span class="smx-logins__device" title="' + esc(row.user_agent) + '">' + esc(row.device || "—") +
                    '</span></td><td class="smx-num">' + esc(row.count) + "</td></tr>";
            });
            html += "</tbody></table></div>";
        }
        if (logins.truncated) {
            html += '<p class="smx-foot">' + esc(text(ctx, "loginsTruncated", { limit: logins.limit })) + "</p>";
        }
        if (logins.org_scoped) html += '<p class="smx-foot">' + esc(ctx.t("loginsOrgNote")) + "</p>";
        return html + "</section>";
    }

    function eventsTable(rows, data, ctx, activeIp) {
        var html = '<div class="smx-table-wrap"><table class="smx-table"><thead><tr>' +
            "<th>" + esc(gettext("Vaxt")) + "</th><th>" + esc(gettext("Hadisə")) + "</th><th>" + esc(gettext("Önəm")) +
            "</th><th>" + esc(gettext("İstifadəçi")) + "</th><th>IP</th><th>" + esc(gettext("Say")) + "</th><th>" +
            esc(gettext("Mesaj")) + "</th></tr></thead><tbody>";
        rows.forEach(function (row) {
            html += "<tr><td>" + esc(when(row.last_seen)) + "</td><td>" + esc(row.event_type_display) + "</td><td>" +
                ctx.pill(row.severity, row.severity) + "</td><td>" + esc(row.user || "—") + "</td><td>" +
                ipCell(row.ip, ctx, activeIp) + "</td><td>" + esc(row.count) + '</td><td class="smx-wrap">' +
                esc(row.message) + "</td></tr>";
        });
        return html + "</tbody></table></div>" + ctx.pager(data, rows.length);
    }

    function syncClear(body, input) {
        var clear = body.querySelector("#smx-sec-ip-clear");
        var ctx = contexts.get(body);
        if (clear) clear.hidden = !input.value && !(ctx && ctx.states[TAB].ip);
    }

    function apply(body, value) {
        var ctx = contexts.get(body);
        if (!ctx || typeof ctx.reload !== "function") return;
        ctx.states[TAB].ip = String(value == null ? "" : value).trim().slice(0, MAX_LENGTH);
        refocusAt.set(body, Date.now());
        ctx.reload(TAB);
    }

    /** Tətbiqdən sonra fokus IP sahəsinə qayıdır; avto-yeniləmədə isə yazılan mətn + kursor saxlanır. */
    function restoreFocus(body, typing) {
        var input = body.querySelector("#smx-sec-ip");
        var requested = refocusAt.get(body);
        refocusAt.delete(body);
        if (!input || (!typing && !(requested && Date.now() - requested < REFOCUS_WINDOW_MS))) return;
        if (typing) {
            input.value = typing.value;
            syncClear(body, input);
        }
        input.focus({ preventScroll: true });
        var end = input.value.length;
        try {
            input.setSelectionRange(typing ? typing.start : end, typing ? typing.end : end);
        } catch (error) { /* kursor yeri vacib deyil */ }
    }

    function bind(body) {
        if (bound.has(body)) return;
        bound.add(body);
        body.addEventListener("click", function (event) {
            var target = event.target.closest && event.target.closest("#smx-sec-ip-go, #smx-sec-ip-clear, [data-smx-ip]");
            if (!target || !body.contains(target)) return;
            if (target.id === "smx-sec-ip-clear") {
                apply(body, "");
            } else if (target.id === "smx-sec-ip-go") {
                var input = body.querySelector("#smx-sec-ip");
                apply(body, input ? input.value : "");
            } else {
                apply(body, target.getAttribute("data-smx-ip"));
            }
        });
        body.addEventListener("keydown", function (event) {
            if (event.key !== "Enter" || event.isComposing || event.target.id !== "smx-sec-ip") return;
            event.preventDefault();
            apply(body, event.target.value);
        });
        body.addEventListener("input", function (event) {
            if (event.target.id === "smx-sec-ip") syncClear(body, event.target);
        });
        body.addEventListener("change", function (event) {
            var ctx = contexts.get(body);
            if (event.target.id !== "smx-sec-type" || !ctx || typeof ctx.reload !== "function") return;
            ctx.states[TAB].type = event.target.value;
            ctx.reload(TAB);
        });
    }

    function render(body, data, ctx) {
        data = data || {};
        bind(body);
        contexts.set(body, ctx);
        var state = ctx.states[TAB];
        var previous = body.querySelector("#smx-sec-ip");
        var typing = previous && previous === document.activeElement ?
            { value: previous.value, start: previous.selectionStart, end: previous.selectionEnd } : null;
        var filter = data.ip_filter || null;
        var html = filterBar(state, data.invalid ? String(data.invalid) : "", ctx);
        if (!data.invalid) {
            var rows = ctx.rowsFrom(data, "events");
            if (data.logins) {
                html += loginsBlock(data.logins, filter, ctx) +
                    '<h4 class="smx-subhead">' + esc(ctx.t("securityTitle")) + "</h4>";
            }
            html += rows.length ?
                eventsTable(rows, data, ctx, filter && filter.kind === "address" ? filter.normalized : "") :
                '<div class="smx-empty">' +
                    esc(state.ip ? ctx.t("eventsEmptyIp") : gettext("Təhlükəsizlik hadisəsi yoxdur")) + "</div>";
        }
        body.innerHTML = html;
        restoreFocus(body, typing);
    }

    namespace.security = { render: render };

    if (typeof namespace.bootPending === "function") {
        namespace.bootPending();
    }
})();
