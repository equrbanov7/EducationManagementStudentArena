/* system_monitoring_format.js — Sistem monitorinqi: saf format/markup
 * köməkçiləri (escapeHtml, formatBytes, formatDuration, card, pill, chartPanel,
 * chartGrid, rowsFrom …). 2026-09-21 bölgüsü (modul ölçü büdcəsi ≤ 550 sətir):
 * `system_monitoring.js` (əsas nəzarətçi) onları `namespace.format`-dan oxuyur və
 * renderers-ə eyni adlarla ötürür. Vəziyyətdən asılı deyil (scope/DOM yoxdur).
 * Yükləmə sırası fail-soft-dur: əsas fayl `namespace.format` olmadan boot
 * etmir; bu fayl sonra gəlsə `bootPending()`-i özü çağırır (renderers kimi).
 */
(function () {
    "use strict";

    var namespace = window.EMSSystemMonitoring = window.EMSSystemMonitoring || {};

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
            return interpolate(gettext("%(days)s gün %(hours)s saat"), { days: days, hours: hours }, true);
        }
        if (hours > 0) {
            return interpolate(gettext("%(hours)s saat %(minutes)s dəq"), { hours: hours, minutes: minutes }, true);
        }
        return interpolate(gettext("%(minutes)s dəq %(seconds)s san"), { minutes: minutes, seconds: seconds % 60 }, true);
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
            '<span class="skeleton skeleton-line skeleton-line--lg smx-skel-gap"></span></div>';
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

    /** Layihənin stilli select komponenti (native görünüş YOX — sahib qaydası 2026-09-09).
     * `options` = [[value, label], …]; render-dən sonra `EMSBootstrapSelect.init(body)` gücləndirir. */
    function selectMarkup(attrs, options, current, label) {
        return '<div class="bootstrap-single-select bootstrap-single-select--ems smx-select-wrap">' +
            '<select class="ems-select bootstrap-single-select__native" data-bootstrap-select ' + attrs +
            ' aria-label="' + escapeHtml(label) + '">' + options.map(function (option) {
                return '<option value="' + escapeHtml(option[0]) + '"' + selected(option[0], current) + ">" +
                    escapeHtml(option[1]) + "</option>";
            }).join("") + "</select></div>";
    }

    /** Səhifələmə: API-nin `pagination` müqaviləsi (source.total_pages / has_next …) → markup. */
    function pagerMarkup(data, count, state) {
        var source = data.pagination || data;
        var pageSize = Number(source.page_size || state.page_size || 20);
        var total = Number(source.total == null ? count : source.total);
        var page = Math.max(1, Number(source.page || state.page || 1));
        var pages = Math.max(1, Number(source.total_pages || Math.ceil(total / pageSize)));
        var hasPrevious = source.has_previous == null ? page > 1 : source.has_previous;
        var hasNext = source.has_next == null ? page < pages : source.has_next;
        if (!total) return "";
        var start = (page - 1) * pageSize + 1;
        var end = Math.min(total, start + count - 1);
        return '<div class="smx-pagination"><span class="smx-page-summary">' + start + "–" + end + " / " + total +
            "</span>" + selectMarkup("data-smx-page-size", [["10", "10"], ["20", "20"], ["50", "50"]], pageSize, gettext("Sətir")) +
            '<button type="button" class="smx-btn" data-smx-page="' + (page - 1) + '"' + (hasPrevious ? "" : " disabled") +
            ' aria-label="' + escapeHtml(gettext("Əvvəlki səhifə")) + '">‹</button>' +
            "<span>" + page + " / " + pages + "</span>" +
            '<button type="button" class="smx-btn" data-smx-page="' + (page + 1) + '"' + (hasNext ? "" : " disabled") +
            ' aria-label="' + escapeHtml(gettext("Növbəti səhifə")) + '">›</button></div>';
    }

    function rowsFrom(data, legacyKey) {
        if (Array.isArray(data.items)) return data.items;
        return Array.isArray(data[legacyKey]) ? data[legacyKey] : [];
    }

    namespace.format = {
        escapeHtml: escapeHtml,
        selected: selected,
        formatBytes: formatBytes,
        formatDuration: formatDuration,
        percent: percent,
        number: number,
        statusClass: statusClass,
        card: card,
        skeletonCards: skeletonCards,
        dot: dot,
        pill: pill,
        chartPanel: chartPanel,
        chartGrid: chartGrid,
        rowsFrom: rowsFrom,
        selectMarkup: selectMarkup,
        pagerMarkup: pagerMarkup,
    };

    if (typeof namespace.bootPending === "function") {
        namespace.bootPending();
    }
})();
