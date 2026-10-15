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

    // 2026-09-13 frontend auditi F7: AZ literallar `gettext()`-ə keçirildi
    // (JavaScriptCatalog `base.html`-dədir; fallback msgid-in özüdür).
    var gettext = window.gettext || function (value) { return value; };

    function esc(value) {
        var node = document.createElement("span");
        node.textContent = value == null ? "" : String(value);
        return node.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function activeSeason() {
        var tab = q(".wlm-tab.is-active");
        return tab ? tab.dataset.wlmSeason || "" : "";
    }

    function rowsTotal(rows) {
        return (rows || []).reduce(function (sum, row) {
            return sum + (Number(row.hours) || 0);
        }, 0);
    }

    /* 2026-10-08 (müəllim rəyi W1): «CƏMİ» xanası İLLİK cəmi (`total_hours`)
       göstərirdi — «Payız» tabında sətirlər 300, cəm 630 idi. İndi GÖRÜNƏN
       sətirlərin cəmidir (server `rows_total_hours`; köhnə cavabda sətirlərdən
       hesablanır) və etiket semestri adlandırır. «İllik cəmi» KPI-ı illikdir. */
    function renderTotal(summary, rows) {
        var total = q("[data-wlm-total]");
        if (total) {
            var value = summary && summary.rows_total_hours !== undefined ?
                summary.rows_total_hours : rowsTotal(rows);
            total.textContent = value || 0;
        }
        var label = q("[data-wlm-total-label]");
        if (!label) return;
        var tab = q(".wlm-tab.is-active");
        var season = activeSeason();
        if (season && tab) {
            label.textContent = (label.dataset.labelSeason || "{season}")
                .replace("{season}", (tab.textContent || "").trim());
        } else if (label.dataset.labelAll) {
            label.textContent = label.dataset.labelAll;
        }
    }

    function renderSummary(summary) {
        if (!summary) return;
        var host = panel();
        if (!host) return;
        Object.keys(summary).forEach(function (key) {
            var node = host.querySelector('[data-wlm-kpi="' + key + '"]');
            if (node) node.textContent = summary[key];
        });
    }

    /* 2026-10-15 (sahib: «631/5K-nı birləşdir»): cədvəl `lines`-ı göstərir — bir fənn + qrup = bir xətt
       («Mühazirə 30 · Seminar 15», saat = cəm). Köhnə cavabda (`lines` yoxdur) bölgü sətirləri olduğu kimi.
       «Redaktə et» yalnız server `edit_url` veribsə (kafedra müdiri / RİM əhatəsi). */
    function renderRows(rows, lines) {
        var body = q("[data-wlm-rows]");
        if (!body) return;
        var host = root();
        var base = (host && host.dataset.journalBaseUrl) || "";
        var canEdit = !!host && host.dataset.canEdit === "1";
        body.innerHTML = (lines || rows || [])
            .map(function (row) {
                var journal = row.offering_id
                    ? '<a href="' + esc(base + row.offering_id) + '/">' + esc(gettext("Aç")) + "</a>"
                    : "";
                var edit = row.edit_url
                    ? '<a class="wl-btn wl-btn--ghost wlm-edit" href="' + esc(row.edit_url) + '">' +
                      esc(gettext("Redaktə et")) + "</a>"
                    : "";
                return (
                    "<tr>" +
                    "<td>" + esc(row.subject) + "</td>" +
                    "<td>" + esc(row.groups) + "</td>" +
                    "<td>" + esc(row.activity_label) + "</td>" +
                    '<td class="wlm-table__num">' + esc(row.hours) + "</td>" +
                    "<td>" + esc(row.education_form_label || row.education_form) + "</td>" +
                    "<td>" + esc(row.degree_level_label || row.degree_level) + "</td>" +
                    "<td>" + journal + "</td>" +
                    (canEdit ? "<td>" + edit + "</td>" : "") +
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
                renderRows(payload.rows || [], payload.lines);
                renderSummary(payload.summary);
                renderTotal(payload.summary, payload.rows || []);
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
