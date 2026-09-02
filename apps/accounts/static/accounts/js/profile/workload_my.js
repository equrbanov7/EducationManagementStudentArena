/*
 * «Dərs yüküm» bölməsi — yalnız-oxu cədvəl (AJAX-safe).
 *
 * Server ilk render-də sətirləri onsuz da verir; bu modul yalnız il/fəsil
 * dəyişəndə JSON ilə yeniləyir. Endpoint URL-ləri `[data-wlm-root]`
 * data-atributlarından oxunur (xarici JS template engine-dən keçmir).
 */
(function (window, document) {
    "use strict";

    function panel() {
        return document.querySelector('[data-profile-section-panel="my-workload"]');
    }

    function q(selector) {
        var host = panel();
        return host ? host.querySelector(selector) : null;
    }

    function root() {
        return q("[data-wlm-root]");
    }

    function esc(value) {
        var node = document.createElement("span");
        node.textContent = value == null ? "" : String(value);
        return node.innerHTML;
    }

    function activeSeason() {
        var tab = q(".wlm-tab.is-active");
        return tab ? tab.dataset.wlmSeason || "" : "";
    }

    function renderSummary(summary) {
        if (!summary) return;
        var host = panel();
        if (!host) return;
        Object.keys(summary).forEach(function (key) {
            var node = host.querySelector('[data-wlm-kpi="' + key + '"]');
            if (node) node.textContent = summary[key];
        });
        var total = q("[data-wlm-total]");
        if (total) total.textContent = summary.total_hours || 0;
    }

    function renderRows(rows) {
        var body = q("[data-wlm-rows]");
        if (!body) return;
        var base = (root() && root().dataset.journalBaseUrl) || "";
        body.innerHTML = (rows || [])
            .map(function (row) {
                var journal = row.offering_id
                    ? '<a href="' + esc(base + row.offering_id) + '/">Aç</a>'
                    : "";
                return (
                    "<tr>" +
                    "<td>" + esc(row.subject) + "</td>" +
                    "<td>" + esc(row.groups) + "</td>" +
                    "<td>" + esc(row.activity_label) + "</td>" +
                    '<td class="wlm-table__num">' + esc(row.hours) + "</td>" +
                    "<td>" + esc(row.education_form) + "</td>" +
                    "<td>" + esc(row.degree_level) + "</td>" +
                    "<td>" + journal + "</td>" +
                    "</tr>"
                );
            })
            .join("");
        var empty = q("[data-wlm-empty]");
        var wrap = q("[data-wlm-table-wrap]");
        if (empty) empty.hidden = (rows || []).length > 0;
        if (wrap) wrap.hidden = (rows || []).length === 0;
    }

    function load() {
        var host = root();
        if (!host) return;
        var year = (q("[data-wlm-year]") || {}).value || "";
        var skeleton = q("[data-wlm-skeleton]");
        if (skeleton) skeleton.hidden = false;
        window.EMSCore.fetchJSON(
            host.dataset.rowsUrl +
                "?year=" +
                encodeURIComponent(year) +
                "&season=" +
                encodeURIComponent(activeSeason())
        )
            .then(function (payload) {
                renderRows(payload.rows || []);
                renderSummary(payload.summary);
                var exportLink = q("[data-wlm-export]");
                if (exportLink) {
                    exportLink.href = host.dataset.exportUrl + "?year=" + encodeURIComponent(year);
                }
            })
            .catch(function () {
                /* səssiz — server-render sətirlər ekranda qalır */
            })
            .then(function () {
                if (skeleton) skeleton.hidden = true;
            });
    }

    function bind() {
        var EMSDelegate = window.EMSDelegate;
        if (!EMSDelegate) return;
        EMSDelegate.on("change", "[data-wlm-year]", load);
        EMSDelegate.on("click", "[data-wlm-season]", function (event, btn) {
            var host = panel();
            if (!host) return;
            host.querySelectorAll(".wlm-tab").forEach(function (tab) {
                var isActive = tab === btn;
                tab.classList.toggle("is-active", isActive);
                tab.setAttribute("aria-selected", isActive ? "true" : "false");
                tab.tabIndex = isActive ? 0 : -1;
            });
            load();
        });
    }

    if (window.EMSReady) {
        window.EMSReady.once("my-workload-bind", bind);
    }
})(window, document);
