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
    W.ui = W.ui || {};

    W.ui.notice = function (kind, text, extra) {
        return '<p class="wl-wiz-note wl-wiz-note--' + kind + '"><i class="fas fa-' + (kind === "warn" ? "triangle-exclamation" : "circle-info") +
            '" aria-hidden="true"></i> <span>' + esc(text) + "</span>" + (extra || "") + "</p>";
    };

    W.ui.journalNotice = function (group) {
        var cfg = W.S.groups[group.id];
        if (!group.journal) {
            var can = W.S.data.task.plan_reached;
            return W.ui.notice(
                "warn",
                can
                    ? gettext("Bu qrupun jurnalı hələ yaradılmayıb. Tələbələri bölmək üçün əvvəlcə jurnalı yaradın — bölgü saatını isə indi də seçə bilərsiniz.")
                    : gettext("Bu qrupun jurnalı hələ yoxdur — tapşırıq dekanlıqda təsdiqlənəndən sonra yaranacaq. İndi yalnız say seçilir, tələbələr sonra bölünür."),
                can ? ' <button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-wiz-journal-create><i class="fas fa-book-medical" aria-hidden="true"></i> ' + esc(gettext("Jurnalı indi yarat")) + "</button>" : ""
            );
        }
        return cfg.reason ? W.ui.notice("warn", cfg.reason) : "";
    };

    W.ui.segment = function (attr, groupId, options, current, disabled) {
        return '<div class="wl-wiz-seg" role="group">' + options.map(function (opt) {
            var on = String(opt.value) === String(current);
            return '<button type="button" class="wl-wiz-seg__btn' + (on ? " is-on" : "") + '" ' + attr + '="' + esc(opt.value) +
                '" data-group-id="' + esc(groupId) + '" aria-pressed="' + (on ? "true" : "false") + '"' +
                (disabled || opt.disabled ? " disabled" : "") + (opt.title ? ' title="' + esc(opt.title) + '"' : "") + ">" + esc(opt.label) + "</button>";
        }).join("") + "</div>";
    };


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
            if (cfg.seminar.numbers.length) badges.push('<span class="wl-badge">' + esc(fmt(gettext("Seminar: %(n)s alt qrup"), { n: cfg.seminar.numbers.length })) + "</span>");
            if (cfg.lab.numbers.length) badges.push('<span class="wl-badge">' + esc(fmt(gettext("Lab: %(n)s qrup"), { n: cfg.lab.numbers.length })) + "</span>");
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

    W.rowModes = function (row) {
        var perKind = row.joint_by_activity || {};
        return { fix: false, joint_by_activity: {
            seminar: perKind.seminar == null ? !!row.joint : perKind.seminar,
            lab: perKind.lab == null ? !!row.joint : perKind.lab,
        } };
    };

    W.isJoint = function (row, kind) { return W.S.rows[row.id].joint_by_activity[kind]; };

    W.separateLab = function (row) { return W.active(row, "lab") && !W.isJoint(row, "lab"); };

    W.alignLabMode = function (row, cfg) {
        if (!W.separateLab(row) || cfg.lab.mode !== "nested") return;
        if (W.isJoint(row, "seminar") || cfg.lab.numbers.length !== cfg.seminar.numbers.length * cfg.lab.per) {
            cfg.lab.mode = "flat";
        }
    };

    W.jointToggle = function (row, kind) {
        if (row.groups.length < 2) return "";
        var joint = W.isJoint(row, kind);
        var label = esc(row.label + " · " + (kind === "seminar" ? gettext("Seminar") : gettext("Laboratoriya")));
        return '<div class="wl-wiz-joint"><span class="wl-wiz-joint__label">' + label + "</span>" +
            '<div class="wl-wiz-seg" role="group" aria-label="' + label + '">' +
            '<button type="button" class="wl-wiz-seg__btn' + (joint ? " is-on" : "") + '" data-wl-wiz-joint="' + esc(row.id) + '" data-activity="' + kind + '" data-value="1" aria-pressed="' + joint + '">' + esc(gettext("Qruplar birlikdə keçir")) + "</button>" +
            '<button type="button" class="wl-wiz-seg__btn' + (!joint ? " is-on" : "") + '" data-wl-wiz-joint="' + esc(row.id) + '" data-activity="' + kind + '" data-value="0" aria-pressed="' + !joint + '">' + esc(gettext("Hər qrup ayrıca")) + "</button>" +
            "</div></div>";
    };

    /** Payload üçün: qrupun jurnal konfiqurasiyası (yalnız dəyişdirilə bilən jurnalda göndərilir). */
    W.groupPayload = function (row, groupId) {
        var cfg = W.S.groups[groupId];
        var group = W.group(groupId);
        var applySem = W.active(row, "seminar") && !W.isJoint(row, "seminar");
        var applyLab = W.active(row, "lab") && !W.isJoint(row, "lab");
        var sem = cfg.seminar, lab = cfg.lab;
        var semNumbers = applySem ? sem.numbers : [];
        var labNumbers = applyLab ? lab.numbers : [];
        var apply = !!(group.journal && cfg.editable && (applySem || applyLab));
        var seminarPlace = {}, labPlace = {};
        if (apply) {
            students(group).forEach(function (st) {
                if (semNumbers.length >= 2 && sem.place[st.id]) seminarPlace[st.id] = sem.place[st.id];
                if (labNumbers.length >= 2 && lab.place[st.id]) labPlace[st.id] = lab.place[st.id];
            });
        }
        return {
            row_id: row.id,
            group_id: groupId,
            apply_journal: apply,
            // Real bölmə nömrələri (`numbers`) — server onları yenidən nömrələmir (boşluqlu {2,3} də qalır).
            seminar: {
                count: semNumbers.length, numbers: semNumbers.slice(), names: sem.names.slice(0, semNumbers.length),
                units: sem.units.slice(0, semNumbers.length), placement: seminarPlace,
            },
            lab: {
                count: labNumbers.length, numbers: labNumbers.slice(), nested: !W.isJoint(row, "seminar") && lab.mode === "nested",
                names: lab.names.slice(0, labNumbers.length), placement: labPlace,
            },
        };
    };

    W.sectionLabel = function (row, groupId, activity, number) {
        var cfg = W.S.groups[groupId];
        var group = W.group(groupId);
        var part = cfg[activity];
        var name = part.names[part.numbers.indexOf(number)];
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
