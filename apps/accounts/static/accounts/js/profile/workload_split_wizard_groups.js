/*
 * «Bölgü sehrbazı» — addım 1 (Qruplar) + qrupun server gövdəsi (`window.EMSWorkloadWizard`, sahib 2026-11-26).
 *
 * Qrup plitələri: ad, tələbə sayı, saatlar, nişanlar (jurnal yoxdur / bağlıdır, reyestr alt qrupları, cari seminar
 * və lab bölgüsü, «bir sətir» qardaşları). Bir tapşırıq sətrinin qrupları birlikdə seçilir. `W.groupPayload` —
 * qrupun jurnal konfiqurasiyası (`split_wizard_apply` gövdəsinin `groups[]` elementi); `W.sectionLabel` /
 * `W.sectionSize` — müəllimlər və yoxlama addımları üçün bölmə adı / tələbə sayı.
 */
(function (window) {
    "use strict";

    var W = (window.EMSWorkloadWizard = window.EMSWorkloadWizard || {});
    W.render = W.render || {};
    W.validate = W.validate || {};

    var gettext = window.gettext || function (value) { return value; };
    function esc(v) { return W.esc(v); }
    function fmt(a, b) { return W.fmt(a, b); }
    function students(group) { return group.journal ? group.journal.students : []; }
    // ── 1. Qruplar ──────────────────────────────────────────────────────────
    function rowHours(row) {
        var parts = [];
        if (W.active(row, "lecture")) parts.push(fmt(gettext("Mühazirə %(h)s"), { h: W.hours(row.totals.lecture) }));
        if (W.active(row, "seminar")) parts.push(fmt(gettext("Seminar %(h)s"), { h: W.hours(row.plans.seminar) }));
        if (W.active(row, "lab")) parts.push(fmt(gettext("Lab %(h)s"), { h: W.hours(row.plans.lab) }));
        return parts.join(" · ");
    }

    W.render.groups = function (panel) {
        if (!panel) return;
        var data = W.S.data;
        var selected = W.selectedGroups().length;
        var html = '<div class="wl-wiz-toolbar"><button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-wiz-groups-all>' +
            '<i class="fas fa-check-double" aria-hidden="true"></i> ' + esc(gettext("Hamısını seç")) + "</button>" +
            '<span class="wl-wiz-toolbar__note" data-wl-wiz-groups-count>' + esc(fmt(gettext("Seçilib: %(n)s qrup"), { n: selected })) + "</span></div>";
        html += '<div class="wl-wiz-tiles">';
        data.groups.forEach(function (group) {
            var row = W.row(group.row_id);
            var on = !!W.S.selected[group.id] || row.groups.some(function (id) { return W.S.selected[id]; });
            var journal = group.journal;
            var badges = [];
            if (!journal) badges.push('<span class="wl-badge wl-badge--warn">' + esc(gettext("Jurnal hələ yoxdur")) + "</span>");
            else if (journal.block_reason) badges.push('<span class="wl-badge">' + esc(gettext("Jurnal bağlıdır")) + "</span>");
            if ((group.registry_subgroups || []).length) {
                badges.push('<span class="wl-badge wl-badge--info">' + esc(fmt(gettext("Reyestrdə alt qruplar: %(list)s"), {
                    list: group.registry_subgroups.map(function (u) { return u.name; }).join(", "),
                })) + "</span>");
            }
            var cfg = W.S.groups[group.id];
            if (cfg.seminar.count) badges.push('<span class="wl-badge">' + esc(fmt(gettext("Seminar: %(n)s alt qrup"), { n: cfg.seminar.count })) + "</span>");
            if (cfg.lab.count) badges.push('<span class="wl-badge">' + esc(fmt(gettext("Lab: %(n)s qrup"), { n: cfg.lab.count })) + "</span>");
            if (row.groups.length > 1) {
                var mates = row.groups.filter(function (id) { return id !== group.id; }).map(function (id) { return (W.group(id) || {}).name; });
                badges.push('<span class="wl-badge" title="' + esc(gettext("Bir tapşırıq sətrinin qrupları birlikdə seçilir.")) + '">' +
                    esc(fmt(gettext("%(list)s ilə bir sətir"), { list: mates.join(", ") })) + "</span>");
            }
            html += '<button type="button" class="wl-wiz-tile' + (on ? " is-selected" : "") + '" data-wl-wiz-group="' + esc(group.id) +
                '" aria-pressed="' + (on ? "true" : "false") + '">' +
                '<span class="wl-wiz-tile__check" aria-hidden="true"><i class="fas fa-check"></i></span>' +
                '<span class="wl-wiz-tile__name">' + esc(group.name) + "</span>" +
                '<span class="wl-wiz-tile__meta">' + esc(journal ? fmt(gettext("%(n)s tələbə"), { n: group.student_count }) : fmt(gettext("%(n)s tələbə (plan)"), { n: row.student_count })) +
                " · " + esc(rowHours(row)) + "</span>" +
                '<span class="wl-wiz-tile__badges">' + badges.join("") + "</span></button>";
        });
        html += "</div>";
        panel.innerHTML = html;
    };

    W.validate.groups = function () {
        return W.selectedRows().length ? "" : gettext("Ən azı bir qrup seçin.");
    };


    /** Payload üçün: qrupun jurnal konfiqurasiyası (yalnız dəyişdirilə bilən jurnalda göndərilir). */
    W.groupPayload = function (row, groupId) {
        var cfg = W.S.groups[groupId];
        var group = W.group(groupId);
        var joint = W.S.rows[row.id].joint;
        var sem = cfg.seminar, lab = cfg.lab;
        var semCount = W.active(row, "seminar") && !joint ? sem.count : 0;
        var labCount = W.active(row, "lab") && !joint ? lab.count : 0;
        var apply = !!(group.journal && cfg.editable && !joint);
        var seminarPlace = {}, labPlace = {};
        if (apply) {
            students(group).forEach(function (st) {
                if (semCount >= 2 && sem.place[st.id]) seminarPlace[st.id] = sem.place[st.id];
                if (labCount >= 2 && lab.place[st.id]) labPlace[st.id] = lab.place[st.id];
            });
        }
        return {
            row_id: row.id,
            group_id: groupId,
            apply_journal: apply,
            seminar: { count: semCount, names: sem.names.slice(0, semCount), units: sem.units.slice(0, semCount), placement: seminarPlace },
            lab: { count: labCount, nested: lab.mode === "nested", names: lab.names.slice(0, labCount), placement: labPlace },
        };
    };

    W.sectionLabel = function (row, groupId, activity, number) {
        var cfg = W.S.groups[groupId];
        var group = W.group(groupId);
        var part = cfg[activity];
        var name = part.names[number - 1];
        if (name) return name;
        return activity === "lab" ? group.name + " · Lab-" + number : group.name + number;
    };
    W.sectionSize = function (groupId, activity, number) {
        var group = W.group(groupId);
        if (!group || !group.journal) return null;
        var place = W.S.groups[groupId][activity].place;
        if (!number) return group.journal.students.length;
        return group.journal.students.filter(function (st) { return place[st.id] === number; }).length;
    };
})(window);
