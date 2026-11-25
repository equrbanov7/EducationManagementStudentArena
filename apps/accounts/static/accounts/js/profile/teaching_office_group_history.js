/*
 * Qrup çekmecəsi «Tarixçə» (sahib 2026-11-25) — tələbənin BÜTÜN jurnal statistikası, dondurulmuş qeydiyyatlar daxil.
 *
 * Düymə `teaching_office_groups.js`-də render olunur (`data-tof-history-url`, yalnız `student.records_view`
 * daşıyana). Bu fayl JSON-u (`organizations:group_student_history`) oxuyub `tofStudentHistoryDialog` dialoquna
 * yazır. Mətnlər dialoqun `[data-tof-history]` kökündəki data-atributlardandır. AJAX-safe: EMSReady + EMSDelegate.
 */
(function (window, document) {
    "use strict";

    var DIALOG_ID = "tofStudentHistoryDialog";
    var seq = 0;

    function dialog() { return document.getElementById(DIALOG_ID); }
    function root() { var d = dialog(); return d ? d.querySelector("[data-tof-history]") : null; }
    function t(key) { var r = root(); return r ? (r.getAttribute("data-t-" + key) || "") : ""; }
    function esc(value) {
        return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
        });
    }
    function num(value) { return value == null ? "—" : String(value).replace(".", ","); }

    function kpi(label, value) {
        return '<div class="tof-history__kpi"><span class="tof-history__kpi-value">' + esc(value) + '</span><span class="tof-history__kpi-label">' + esc(label) + "</span></div>";
    }

    function summary(payload) {
        var totals = payload.totals || {};
        var tiles = [kpi(t("subjects"), totals.subjects || 0), kpi(t("marks"), totals.marks || 0)];
        if (payload.freeze) { tiles.push(kpi(t("before-freeze"), totals.marks_before_freeze || 0)); }
        tiles.push(kpi(t("average"), num(totals.average)));
        tiles.push(kpi(t("present"), totals.present || 0));
        tiles.push(kpi(t("absent"), totals.absent || 0));
        return '<div class="tof-history__kpis">' + tiles.join("") + "</div>";
    }

    function freezeNote(payload) {
        var freeze = payload.freeze;
        if (!freeze) { return ""; }
        var text = t("freeze") + ": " + (freeze.order_number ? t("order") + " " + freeze.order_number + " · " : "") + (freeze.date || "");
        if (freeze.until) { text += " (" + t("until") + ": " + freeze.until + ")"; }
        return '<p class="tof-history__freeze" role="note"><i class="fas fa-snowflake" aria-hidden="true"></i> ' + esc(text) + "</p>";
    }

    function periodTable(period, withFreeze) {
        var head = [t("subjects"), t("group"), t("status"), t("marks")];
        if (withFreeze) { head.push(t("before-freeze")); }
        head = head.concat([t("average"), t("present"), t("absent"), t("excused"), t("absence-hours"), t("last-date")]);
        var rows = (period.rows || []).map(function (row) {
            var cells = [
                esc(row.subject) + (row.subject_code ? ' <span class="tof-history__code">' + esc(row.subject_code) + "</span>" : ""),
                esc(row.group || "—"),
                '<span class="ems-badge tof-history__status tof-history__status--' + esc(row.status) + '">' + esc(row.status_label) + "</span>",
                esc(row.marks)
            ];
            if (withFreeze) { cells.push(esc(row.marks_before_freeze)); }
            cells = cells.concat([esc(num(row.average)), esc(row.present), esc(row.absent), esc(row.excused), esc(row.absence_hours), esc(row.last_date || "—")]);
            return "<tr>" + cells.map(function (cell) { return "<td>" + cell + "</td>"; }).join("") + "</tr>";
        });
        return (
            '<section class="tof-history__period"><h3 class="tof-history__period-title">' + esc(period.label) + "</h3>" +
            '<div class="ems-tablescroll"><table class="ems-table ems-table--zebra tof-history__table"><thead><tr>' +
            head.map(function (label) { return '<th scope="col">' + esc(label) + "</th>"; }).join("") +
            "</tr></thead><tbody>" + rows.join("") + "</tbody></table></div></section>"
        );
    }

    function movements(payload) {
        var items = payload.movements || [];
        var body = items.length
            ? "<ul class=\"tof-history__moves\">" + items.map(function (move) {
                var parts = [move.kind_label];
                if (move.order_number) { parts.push(t("order") + " " + move.order_number); }
                if (move.order_date) { parts.push(move.order_date); }
                if (move.from_group || move.to_group) { parts.push((move.from_group || "—") + " → " + (move.to_group || "—")); }
                if (move.until) { parts.push(t("until") + ": " + move.until); }
                return "<li>" + esc(parts.join(" · ")) + "</li>";
            }).join("") + "</ul>"
            : '<p class="tof-history__muted">' + esc(t("no-movements")) + "</p>";
        return '<section class="tof-history__period"><h3 class="tof-history__period-title">' + esc(t("movements")) + "</h3>" + body + "</section>";
    }

    function render(payload) {
        var r = root();
        if (!r) { return; }
        var who = r.querySelector("[data-tof-history-who]");
        if (who) {
            var record = payload.record || {};
            who.textContent = [payload.student && payload.student.name, record.group, record.status_label].filter(Boolean).join(" · ");
        }
        var periods = payload.periods || [];
        var html = summary(payload) + freezeNote(payload);
        html += periods.length
            ? periods.map(function (period) { return periodTable(period, !!payload.freeze); }).join("")
            : '<p class="tof-history__muted">' + esc(t("empty")) + "</p>";
        if (payload.truncated) { html += '<p class="tof-history__muted">' + esc(t("truncated")) + "</p>"; }
        html += movements(payload);
        var body = r.querySelector("[data-tof-history-body]");
        body.innerHTML = html;
        body.setAttribute("aria-busy", "false");
    }

    function open(button) {
        var d = dialog();
        var r = root();
        if (!d || !r || !window.EMSOverlay) { return; }
        var body = r.querySelector("[data-tof-history-body]");
        var error = r.querySelector("[data-tof-history-error]");
        var who = r.querySelector("[data-tof-history-who]");
        if (who) { who.textContent = button.getAttribute("data-tof-history-name") || ""; }
        if (error) { error.hidden = true; error.textContent = ""; }
        body.innerHTML = '<p class="tof-history__muted">' + esc(t("loading")) + "</p>";
        body.setAttribute("aria-busy", "true");
        window.EMSOverlay.open(d, button);
        var mine = ++seq;
        window.EMSCore.fetchJSON(button.getAttribute("data-tof-history-url"))
            .then(function (payload) {
                if (mine !== seq) { return; }
                if (!payload || payload.ok === false) { throw new Error("history"); }
                render(payload);
            })
            .catch(function () {
                if (mine !== seq) { return; }
                body.innerHTML = "";
                body.setAttribute("aria-busy", "false");
                if (error) { error.textContent = t("error"); error.hidden = false; }
            });
    }

    window.EMSReady(function () {
        if (window.__emsTofHistoryBound) { return; }
        window.__emsTofHistoryBound = true;
        window.EMSDelegate.on("click", "[data-tof-history-url]", function (event, button) {
            event.preventDefault();
            open(button);
        });
    });
})(window, document);
