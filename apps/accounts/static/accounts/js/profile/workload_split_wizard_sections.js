/*
 * «Bölgü sehrbazı» — addım 2–3: Seminar, Laboratoriya + başlanğıc vəziyyət (`window.EMSWorkloadWizard`, 2026-11-26).
 *
 * Vəziyyət (`W.S`): `selected` {qrup: true}; `rows` {sətir: {joint, fix}}; `groups` {qrup: {seminar, lab, editable,
 * reason}} — seminar `{count, names[], units[], place{qeydiyyat: indeks}}`, lab `{mode: none|nested|flat, per,
 * count, names[], place{}}`. Bölmə indeksi 1..count; server də 1..count nömrələyir (jurnal `SeminarGroup` /
 * `LabGroup`). İç-içə rejimdə lab № = (seminar indeksi − 1) × per + k — bir lab qrupu iki seminar alt qrupunu
 * qarışdırmır. Tələbə siyahısı yalnız jurnal varsa, səlahiyyət varsa və jurnal bağlı deyilsə dəyişdirilir.
 */
(function (window) {
    "use strict";

    var W = (window.EMSWorkloadWizard = window.EMSWorkloadWizard || {});
    W.render = W.render || {};
    W.validate = W.validate || {};
    var MAX = 9;
    var NAME_MAX = 40;

    var gettext = window.gettext || function (value) { return value; };
    function esc(v) { return W.esc(v); }
    function fmt(a, b) { return W.fmt(a, b); }
    function clip(text) { return String(text || "").slice(0, NAME_MAX); }

    // ── başlanğıc vəziyyət ──────────────────────────────────────────────────
    function maxSub(row, groupId, activity) {
        var single = row.groups.length === 1;
        var top = 0;
        row.assignments.forEach(function (a) {
            if (a.activity !== activity || !a.sub_number) return;
            if (a.group_id === groupId || (single && !a.group_id)) top = Math.max(top, a.sub_number);
        });
        return top;
    }

    function indexMap(sections) {
        var map = {};
        sections.forEach(function (s, i) { map[s.number] = i + 1; });
        return map;
    }

    function initGroup(group) {
        var row = W.row(group.row_id);
        var journal = group.journal;
        var semSections = journal ? journal.seminar : [];
        var labSections = journal ? journal.lab : [];
        var single = row.groups.length === 1;
        var semCount = semSections.length >= 2 ? semSections.length : 0;
        if (!semCount && W.active(row, "seminar")) {
            var top = maxSub(row, group.id, "seminar");
            semCount = top >= 2 ? top : single && row.subgroup_count >= 2 ? row.subgroup_count : 0;
        }
        semCount = Math.min(semCount, MAX);
        var semIndex = indexMap(semSections);
        var seminar = { count: semCount, names: [], units: [], place: {} };
        for (var i = 0; i < semCount; i += 1) {
            var section = semSections[i];
            seminar.names.push(section ? section.name : clip(group.name + (i + 1)));
            seminar.units.push(section ? section.unit_id : "");
        }
        (journal ? journal.students : []).forEach(function (st) {
            var idx = st.seminar ? semIndex[st.seminar] : 0;
            if (idx && idx <= semCount) seminar.place[st.id] = idx;
        });
        var labCount = labSections.length >= 2 ? labSections.length : 0;
        if (!labCount && W.active(row, "lab")) {
            var labTop = maxSub(row, group.id, "lab");
            var rowLab = row.lab_group_count || row.subgroup_count;
            labCount = labTop >= 2 ? labTop : single && rowLab >= 2 ? rowLab : 0;
        }
        labCount = Math.min(labCount, MAX);
        var labIndex = indexMap(labSections);
        var lab = { mode: "none", per: 2, count: labCount, names: [], place: {} };
        (journal ? journal.students : []).forEach(function (st) {
            var idx = st.lab ? labIndex[st.lab] : 0;
            if (idx && idx <= labCount) lab.place[st.id] = idx;
        });
        if (labCount) {
            var nested = semCount >= 2 && labCount % semCount === 0;
            if (nested && journal) {
                var owner = {};
                journal.students.forEach(function (st) {
                    var l = lab.place[st.id];
                    var s = seminar.place[st.id];
                    if (!l || !s) return;
                    if (owner[l] && owner[l] !== s) nested = false;
                    owner[l] = s;
                    if (Math.ceil(l / (labCount / semCount)) !== s) nested = false;
                });
            }
            lab.mode = nested ? "nested" : "flat";
            lab.per = nested ? labCount / semCount : 2;
        }
        for (var k = 0; k < labCount; k += 1) {
            lab.names.push(labSections[k] ? labSections[k].name : defaultLabName(group, seminar, lab, k + 1));
        }
        var editable = !!(journal && journal.can_manage && !journal.block_reason);
        var reason = !journal
            ? ""
            : journal.block_reason || (!journal.can_manage ? gettext("Bu jurnalın bölmələrini dəyişməyə icazəniz yoxdur.") : "");
        return { seminar: seminar, lab: lab, editable: editable, reason: reason };
    }

    function defaultLabName(group, seminar, lab, number) {
        if (lab.mode === "nested" && seminar.count >= 2) {
            var s = Math.ceil(number / lab.per);
            var k = number - (s - 1) * lab.per;
            var base = seminar.names[s - 1] || group.name + s;
            return clip(base + " · Lab-" + k);
        }
        return clip(group.name + " · Lab-" + number);
    }

    W.init = function (data) {
        var S = W.S;
        S.rows = {};
        S.groups = {};
        S.units = {};
        S.lecture = {};
        (data.rows || []).forEach(function (row) { S.rows[row.id] = { joint: !!row.joint, fix: false }; });
        (data.groups || []).forEach(function (group) { S.groups[group.id] = initGroup(group); });
        var keep = S.selected;
        S.selected = {};
        Object.keys(keep || {}).forEach(function (id) { if (S.groups[id]) S.selected[id] = true; });
        if (!Object.keys(S.selected).length && (data.rows || []).length === 1) {
            data.rows[0].groups.forEach(function (id) { S.selected[id] = true; });
        }
    };

    // ── köməkçilər ──────────────────────────────────────────────────────────
    function students(group) { return group.journal ? group.journal.students : []; }

    function counts(place, n, list) {
        var out = [];
        for (var i = 0; i <= n; i += 1) out.push(0);
        list.forEach(function (st) { var v = place[st.id]; out[v && v <= n ? v : 0] += 1; });
        return out;
    }

    /** Əlifba ilə bərabər bölmə (siyahı server tərəfindən soyad sırası ilə gəlir). */
    function splitEven(list, n, offset) {
        var place = {};
        var size = Math.ceil(list.length / n) || 1;
        list.forEach(function (st, i) { place[st.id] = Math.min(Math.floor(i / size), n - 1) + 1 + (offset || 0); });
        return place;
    }

    function setSeminarCount(groupId, count) {
        var group = W.group(groupId);
        var cfg = W.S.groups[groupId];
        var sem = cfg.seminar;
        var old = sem.count;
        sem.count = count;
        var names = [], units = [];
        for (var i = 0; i < count; i += 1) {
            names.push(i < old ? sem.names[i] : clip(group.name + (i + 1)));
            units.push(i < old ? sem.units[i] : "");
        }
        sem.names = names;
        sem.units = units;
        Object.keys(sem.place).forEach(function (id) { if (sem.place[id] > count) delete sem.place[id]; });
        if (count < 2) {
            sem.place = {};
            if (cfg.lab.mode === "nested") setLabMode(groupId, "flat");
        } else if (cfg.lab.mode === "nested") {
            setLabMode(groupId, "nested");
        }
    }

    function setLabMode(groupId, mode) {
        var group = W.group(groupId);
        var cfg = W.S.groups[groupId];
        var lab = cfg.lab;
        if (mode === "nested" && cfg.seminar.count < 2) mode = "flat";
        lab.mode = mode;
        if (mode === "none") {
            lab.count = 0;
        } else if (mode === "nested") {
            lab.per = Math.max(2, lab.per || 2);
            lab.count = Math.min(cfg.seminar.count * lab.per, MAX);
            lab.per = Math.floor(lab.count / cfg.seminar.count);
            lab.count = cfg.seminar.count * lab.per;
        } else if (lab.count < 2) {
            lab.count = 2;
        }
        lab.names = [];
        for (var n = 1; n <= lab.count; n += 1) lab.names.push(defaultLabName(group, cfg.seminar, lab, n));
        if (mode === "nested") lab.place = nestedFill(group, cfg, lab.place);
        else Object.keys(lab.place).forEach(function (id) { if (lab.place[id] > lab.count) delete lab.place[id]; });
        if (mode === "none") lab.place = {};
        // Heç kim yerləşməyibsə ilkin təklif əlifba ilədir (sonra əl ilə dəyişmək olar) — «kim haradadır» dərhal görünür.
        if (mode !== "none" && !Object.keys(lab.place).length) {
            lab.place = mode === "nested" ? nestedAlphabet(group, cfg) : splitEven(students(group), lab.count, 0);
        }
    }

    /** İç-içə rejim: tələbə öz seminar alt qrupunun lab qruplarındadır; uyğun olmayan/boş olan ən az dolu qrupa düşür. */
    function nestedFill(group, cfg, current) {
        if (!Object.keys(current || {}).length) return nestedAlphabet(group, cfg);
        var lab = cfg.lab;
        var per = lab.per;
        var place = {};
        var sizes = {};
        var list = students(group);
        list.forEach(function (st) {
            var s = cfg.seminar.place[st.id];
            var l = current[st.id];
            if (s && l && Math.ceil(l / per) === s) { place[st.id] = l; sizes[l] = (sizes[l] || 0) + 1; }
        });
        list.forEach(function (st) {
            if (place[st.id]) return;
            var s = cfg.seminar.place[st.id];
            if (!s) return;
            var best = 0;
            for (var k = 1; k <= per; k += 1) {
                var n = (s - 1) * per + k;
                if (!best || (sizes[n] || 0) < (sizes[best] || 0)) best = n;
            }
            place[st.id] = best;
            sizes[best] = (sizes[best] || 0) + 1;
        });
        return place;
    }

    function nestedAlphabet(group, cfg) {
        var place = {};
        for (var s = 1; s <= cfg.seminar.count; s += 1) {
            var members = students(group).filter(function (st) { return cfg.seminar.place[st.id] === s; });
            var part = splitEven(members, cfg.lab.per, (s - 1) * cfg.lab.per);
            Object.keys(part).forEach(function (id) { place[id] = part[id]; });
        }
        return place;
    }

    /** Seminar alt qrupları reyestrdən: say, ad, mənbə alt qrup və tələbənin reyestr qrupu ilə yerləşdirmə. */
    function fromRegistry(group) {
        var regs = group.registry_subgroups || [];
        setSeminarCount(group.id, Math.min(regs.length, MAX));
        var sem = W.S.groups[group.id].seminar;
        sem.names = regs.slice(0, MAX).map(function (u) { return clip(u.name); });
        sem.units = regs.slice(0, MAX).map(function (u) { return u.id; });
        sem.place = {};
        students(group).forEach(function (st) {
            var index = sem.units.indexOf(st.unit_id);
            if (index >= 0) sem.place[st.id] = index + 1;
        });
        if (W.S.groups[group.id].lab.mode === "nested") setLabMode(group.id, "nested");
    }

    function registryName(group, unitId) {
        var found = (group.registry_subgroups || []).filter(function (u) { return u.id === unitId; })[0];
        return found ? found.name : "";
    }

    // ── 2. Seminar ──────────────────────────────────────────────────────────
    function notice(kind, text, extra) {
        return '<p class="wl-wiz-note wl-wiz-note--' + kind + '"><i class="fas fa-' + (kind === "warn" ? "triangle-exclamation" : "circle-info") +
            '" aria-hidden="true"></i> <span>' + esc(text) + "</span>" + (extra || "") + "</p>";
    }

    function journalNotice(group) {
        var cfg = W.S.groups[group.id];
        if (!group.journal) {
            var can = W.S.data.task.plan_reached;
            return notice(
                "warn",
                can
                    ? gettext("Bu qrupun jurnalı hələ yaradılmayıb. Tələbələri bölmək üçün əvvəlcə jurnalı yaradın — bölgü saatını isə indi də seçə bilərsiniz.")
                    : gettext("Bu qrupun jurnalı hələ yoxdur — tapşırıq dekanlıqda təsdiqlənəndən sonra yaranacaq. İndi yalnız say seçilir, tələbələr sonra bölünür."),
                can ? ' <button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-wiz-journal-create><i class="fas fa-book-medical" aria-hidden="true"></i> ' + esc(gettext("Jurnalı indi yarat")) + "</button>" : ""
            );
        }
        return cfg.reason ? notice("warn", cfg.reason) : "";
    }

    function segment(attr, groupId, options, current, disabled) {
        return '<div class="wl-wiz-seg" role="group">' + options.map(function (opt) {
            var on = String(opt.value) === String(current);
            return '<button type="button" class="wl-wiz-seg__btn' + (on ? " is-on" : "") + '" ' + attr + '="' + esc(opt.value) +
                '" data-group-id="' + esc(groupId) + '" aria-pressed="' + (on ? "true" : "false") + '"' +
                (disabled || opt.disabled ? " disabled" : "") + (opt.title ? ' title="' + esc(opt.title) + '"' : "") + ">" + esc(opt.label) + "</button>";
        }).join("") + "</div>";
    }

    function sectionChips(kind, group, names, place, n) {
        var list = students(group);
        var c = counts(place, n, list);
        var cfg = W.S.groups[group.id];
        var html = '<div class="wl-wiz-secs">';
        for (var i = 1; i <= n; i += 1) {
            html += '<label class="wl-wiz-sec wl-wiz-c' + i + '"><span class="wl-wiz-sec__no">' + i + "</span>" +
                '<input type="text" maxlength="40" value="' + esc(names[i - 1]) + '" placeholder="' + esc(group.name + i) + '" data-wl-wiz-' + kind + '-name="' + i +
                '" data-group-id="' + esc(group.id) + '"' + (cfg.editable || !group.journal ? "" : " disabled") + ' aria-label="' + esc(fmt(gettext("%(n)s-ci bölmənin adı"), { n: i })) + '">' +
                (group.journal ? '<span class="wl-wiz-sec__count">' + esc(fmt(gettext("%(n)s tələbə"), { n: c[i] })) + "</span>" : "") + "</label>";
        }
        html += "</div>";
        if (group.journal && c[0]) html += notice("warn", fmt(gettext("Heç bir bölməyə yerləşdirilməyib: %(n)s tələbə."), { n: c[0] }));
        return html;
    }

    function studentRows(kind, group, n, allowed) {
        var cfg = W.S.groups[group.id];
        var place = cfg[kind].place;
        var list = students(group);
        if (!list.length) return group.journal ? notice("info", gettext("Jurnalda aktiv tələbə yoxdur.")) : "";
        return '<div class="wl-wiz-students">' + list.map(function (st) {
            var current = place[st.id] || 0;
            var reg = registryName(group, st.unit_id);
            var buttons = "";
            for (var i = 1; i <= n; i += 1) {
                if (allowed && !allowed(st, i)) continue;
                buttons += '<button type="button" class="wl-wiz-place wl-wiz-c' + i + (current === i ? " is-on" : "") + '" data-wl-wiz-place="' + kind +
                    '" data-number="' + i + '" data-group-id="' + esc(group.id) + '" data-enrollment="' + esc(st.id) + '" aria-pressed="' +
                    (current === i ? "true" : "false") + '" title="' + esc(cfg[kind].names[i - 1] || "") + '"' + (cfg.editable ? "" : " disabled") + ">" + i + "</button>";
            }
            return '<div class="wl-wiz-st' + (current ? "" : " is-unplaced") + '" data-wl-wiz-student="' + esc(st.id) + '">' +
                '<span class="wl-wiz-st__name">' + esc(st.name) + "</span>" +
                (reg ? '<span class="wl-wiz-st__reg">' + esc(reg) + "</span>" : "") +
                '<span class="wl-wiz-st__btns">' + buttons + "</span></div>";
        }).join("") + "</div>";
    }

    function lessonWarnings(group, kind, n) {
        var sections = group.journal ? group.journal[kind] : [];
        return sections.filter(function (s, i) { return s.lessons > 0 && i + 1 > n; }).map(function (s) {
            return notice("warn", fmt(gettext("«%(name)s» bölməsinə %(n)s dərs bağlıdır — bu bölmə silinə bilməz. Əvvəlcə jurnalda həmin dərslərin bölməsini dəyişin."), { name: s.label, n: s.lessons }));
        }).join("");
    }

    function jointToggle(row) {
        if (row.groups.length < 2) return "";
        var joint = W.S.rows[row.id].joint;
        return '<div class="wl-wiz-joint"><span class="wl-wiz-joint__label">' + esc(fmt(gettext("%(groups)s — seminar və laboratoriya:"), { groups: row.label })) + "</span>" +
            '<div class="wl-wiz-seg" role="group">' +
            '<button type="button" class="wl-wiz-seg__btn' + (joint ? " is-on" : "") + '" data-wl-wiz-joint="' + esc(row.id) + '" data-value="1" aria-pressed="' + joint + '">' + esc(gettext("Qruplar birlikdə keçir")) + "</button>" +
            '<button type="button" class="wl-wiz-seg__btn' + (!joint ? " is-on" : "") + '" data-wl-wiz-joint="' + esc(row.id) + '" data-value="0" aria-pressed="' + !joint + '">' + esc(gettext("Hər qrup ayrıca")) + "</button>" +
            "</div></div>";
    }

    function seminarPanel(group) {
        var row = W.row(group.row_id);
        var cfg = W.S.groups[group.id];
        var sem = cfg.seminar;
        var options = [{ value: 0, label: gettext("Bölünmür") }, { value: 2, label: gettext("2 alt qrup") }, { value: 3, label: gettext("3 alt qrup") }, { value: 4, label: gettext("4 alt qrup") }];
        if (sem.count > 4) options.push({ value: sem.count, label: fmt(gettext("%(n)s alt qrup"), { n: sem.count }) });
        var locked = !!group.journal && !cfg.editable;
        var html = '<article class="wl-wiz-gp" data-wl-wiz-gpanel="' + esc(group.id) + '"><header class="wl-wiz-gp__head"><h4>' + esc(group.name) + "</h4>" +
            '<span class="wl-wiz-gp__meta">' + esc(fmt(gettext("%(n)s tələbə · seminar planı %(h)s (bir alt qrup üçün)"), { n: group.journal ? group.student_count : row.student_count, h: W.hours(row.plans.seminar) })) + "</span></header>" +
            journalNotice(group) + segment("data-wl-wiz-seminar-count", group.id, options, sem.count, locked);
        if (sem.count >= 2) {
            var regs = group.registry_subgroups || [];
            var helpers = "";
            if (regs.length >= 2 && group.journal) {
                helpers += '<button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-wiz-seminar-registry data-group-id="' + esc(group.id) + '"' + (cfg.editable ? "" : " disabled") + '>' +
                    '<i class="fas fa-sitemap" aria-hidden="true"></i> ' + esc(fmt(gettext("%(list)s kimi böl"), { list: regs.map(function (u) { return u.name; }).join(gettext(" və ")) })) + "</button>";
            }
            if (group.journal) {
                helpers += '<button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-wiz-seminar-alpha data-group-id="' + esc(group.id) + '"' + (cfg.editable ? "" : " disabled") + '>' +
                    '<i class="fas fa-arrow-down-a-z" aria-hidden="true"></i> ' + esc(gettext("Əlifba ilə bərabər böl")) + "</button>";
            }
            html += (helpers ? '<div class="wl-wiz-helpers">' + helpers + "</div>" : "") + sectionChips("seminar", group, sem.names, sem.place, sem.count);
            html += studentRows("seminar", group, sem.count, null);
        } else if (group.journal) {
            html += notice("info", gettext("Seminar bütün qrupla keçir — bir bölmə, bir müəllim."));
        }
        html += lessonWarnings(group, "seminar", sem.count);
        return html + "</article>";
    }

    W.render.seminar = function (panel) {
        if (!panel) return;
        var html = "";
        W.selectedRows().forEach(function (row) {
            if (!W.active(row, "seminar")) return;
            html += jointToggle(row);
            if (W.S.rows[row.id].joint) {
                html += notice("info", fmt(gettext("%(groups)s seminarı birlikdə keçir — bir bölmə, bir müəllim."), { groups: row.label }));
                return;
            }
            row.groups.forEach(function (id) { html += seminarPanel(W.group(id)); });
        });
        panel.innerHTML = html || notice("info", gettext("Seçilmiş qruplarda seminar saatı yoxdur — bu addımı keçin."));
    };

    function sectionProblems(kind) {
        var problems = [];
        W.selectedRows().forEach(function (row) {
            if (!W.active(row, kind) || W.S.rows[row.id].joint) return;
            row.groups.forEach(function (id) {
                var group = W.group(id);
                var cfg = W.S.groups[id];
                var part = cfg[kind];
                if (!group.journal || !cfg.editable) return;
                if (part.count >= 2) {
                    var c = counts(part.place, part.count, students(group));
                    if (c[0]) problems.push(fmt(gettext("%(group)s: %(n)s tələbə yerləşdirilməyib."), { group: group.name, n: c[0] }));
                    var seen = {};
                    part.names.forEach(function (name) {
                        var key = String(name || "").toLowerCase().replace(/[\s-]+/g, "");
                        if (key && seen[key]) problems.push(fmt(gettext("%(group)s: iki bölmənin adı eynidir."), { group: group.name }));
                        seen[key] = true;
                    });
                }
                group.journal[kind].forEach(function (s, i) {
                    if (s.lessons > 0 && i + 1 > part.count) problems.push(fmt(gettext("%(group)s: «%(name)s» bölməsinə dərs bağlıdır."), { group: group.name, name: s.label }));
                });
            });
        });
        return problems.length ? problems[0] + (problems.length > 1 ? " " + fmt(gettext("(+%(n)s başqa)"), { n: problems.length - 1 }) : "") : "";
    }

    W.validate.seminar = function () { return sectionProblems("seminar"); };

    // ── 3. Laboratoriya ─────────────────────────────────────────────────────
    function labPanel(group) {
        var row = W.row(group.row_id);
        var cfg = W.S.groups[group.id];
        var lab = cfg.lab;
        var locked = !!group.journal && !cfg.editable;
        var canNest = cfg.seminar.count >= 2;
        var html = '<article class="wl-wiz-gp" data-wl-wiz-gpanel="' + esc(group.id) + '"><header class="wl-wiz-gp__head"><h4>' + esc(group.name) + "</h4>" +
            '<span class="wl-wiz-gp__meta">' + esc(fmt(gettext("lab planı %(h)s (bir lab qrupu üçün)"), { h: W.hours(row.plans.lab) })) + "</span></header>" +
            journalNotice(group) +
            segment("data-wl-wiz-lab-mode", group.id, [
                { value: "none", label: gettext("Bölünmür") },
                { value: "nested", label: fmt(gettext("Hər seminar alt qrupunu böl (%(n)s alt qrup)"), { n: cfg.seminar.count || 0 }), disabled: !canNest, title: canNest ? "" : gettext("Əvvəlcə seminarı alt qruplara bölün.") },
                { value: "flat", label: gettext("Seminardan asılı olmadan") },
            ], lab.mode, locked);
        if (lab.mode === "nested") {
            html += '<div class="wl-wiz-row"><span class="wl-wiz-row__label">' + esc(gettext("Hər seminar alt qrupunda neçə lab qrupu:")) + "</span>" +
                segment("data-wl-wiz-lab-per", group.id, [2, 3, 4].filter(function (n) { return n * cfg.seminar.count <= MAX; }).map(function (n) { return { value: n, label: String(n) }; }), lab.per, locked) + "</div>";
        } else if (lab.mode === "flat") {
            html += '<div class="wl-wiz-row"><span class="wl-wiz-row__label">' + esc(gettext("Lab qrupu sayı:")) + "</span>" +
                segment("data-wl-wiz-lab-count", group.id, [2, 3, 4, 5, 6].map(function (n) { return { value: n, label: String(n) }; }), lab.count, locked) + "</div>";
        }
        if (lab.mode !== "none") {
            if (group.journal) {
                html += '<div class="wl-wiz-helpers"><button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-wiz-lab-fill data-group-id="' + esc(group.id) + '"' + (cfg.editable ? "" : " disabled") + '>' +
                    '<i class="fas fa-arrow-down-a-z" aria-hidden="true"></i> ' + esc(lab.mode === "nested" ? gettext("Seminar alt qrupundan doldur (əlifba ilə)") : gettext("Əlifba ilə bərabər böl")) + "</button></div>";
            }
            html += sectionChips("lab", group, lab.names, lab.place, lab.count);
            var per = lab.per;
            html += studentRows("lab", group, lab.count, lab.mode === "nested"
                ? function (st, n) { var s = cfg.seminar.place[st.id]; return !s || Math.ceil(n / per) === s; }
                : null);
        } else if (group.journal) {
            html += notice("info", gettext("Laboratoriya bütün qrupla keçir — bir bölmə, bir müəllim."));
        }
        html += lessonWarnings(group, "lab", lab.count);
        return html + "</article>";
    }

    W.render.lab = function (panel) {
        if (!panel) return;
        var html = "";
        W.selectedRows().forEach(function (row) {
            if (!W.active(row, "lab")) return;
            if (W.S.rows[row.id].joint) {
                html += notice("info", fmt(gettext("%(groups)s laboratoriyanı birlikdə keçir — bir bölmə, bir müəllim."), { groups: row.label }));
                return;
            }
            row.groups.forEach(function (id) {
                var group = W.group(id);
                var cfg = W.S.groups[id];
                if (cfg.lab.mode === "nested" && cfg.editable) cfg.lab.place = nestedFill(group, cfg, cfg.lab.place);
                html += labPanel(group);
            });
        });
        panel.innerHTML = html || notice("info", gettext("Seçilmiş qruplarda laboratoriya saatı yoxdur — bu addımı keçin."));
    };

    W.validate.lab = function () {
        var problem = sectionProblems("lab");
        if (problem) return problem;
        var mixed = "";
        W.selectedRows().forEach(function (row) {
            row.groups.forEach(function (id) {
                var cfg = W.S.groups[id];
                if (mixed || cfg.lab.mode !== "nested" || !cfg.editable) return;
                students(W.group(id)).forEach(function (st) {
                    var s = cfg.seminar.place[st.id];
                    var l = cfg.lab.place[st.id];
                    if (s && l && Math.ceil(l / cfg.lab.per) !== s) mixed = fmt(gettext("%(name)s başqa seminar alt qrupunun lab qrupundadır."), { name: st.name });
                });
            });
        });
        return mixed;
    };

    function rerender() { var name = W.STEPS[W.S.step]; W.render[name](W.q('[data-wl-wiz-panel="' + name + '"]')); }

    W.bindSections = function (D) {
        D.on("click", "[data-wl-wiz-group]", function (event, btn) {
            var group = W.group(btn.dataset.wlWizGroup);
            if (!group) return;
            var row = W.row(group.row_id);
            var on = !row.groups.some(function (id) { return W.S.selected[id]; });
            row.groups.forEach(function (id) { if (on) W.S.selected[id] = true; else delete W.S.selected[id]; });
            rerender();
        });
        D.on("click", "[data-wl-wiz-groups-all]", function () {
            var all = W.S.data.groups.every(function (g) { return W.S.selected[g.id]; });
            W.S.data.groups.forEach(function (g) { if (all) delete W.S.selected[g.id]; else W.S.selected[g.id] = true; });
            rerender();
        });
        D.on("click", "[data-wl-wiz-joint]", function (event, btn) {
            W.S.rows[btn.dataset.wlWizJoint].joint = btn.dataset.value === "1";
            rerender();
        });
        D.on("click", "[data-wl-wiz-seminar-count]", function (event, btn) {
            var group = W.group(btn.dataset.groupId);
            var count = Number(btn.dataset.wlWizSeminarCount) || 0;
            var regs = group.registry_subgroups || [];
            if (count >= 2 && regs.length === count && group.journal && !Object.keys(W.S.groups[group.id].seminar.place).length) {
                fromRegistry(group);  // reyestrdə məhz bu qədər alt qrup var — ilkin təklif onlardır
            } else {
                setSeminarCount(group.id, count);
                var sem = W.S.groups[group.id].seminar;
                if (count >= 2 && !Object.keys(sem.place).length) sem.place = splitEven(students(group), count, 0);
            }
            rerender();
        });
        D.on("click", "[data-wl-wiz-seminar-alpha]", function (event, btn) {
            var cfg = W.S.groups[btn.dataset.groupId];
            cfg.seminar.place = splitEven(students(W.group(btn.dataset.groupId)), cfg.seminar.count, 0);
            rerender();
        });
        D.on("click", "[data-wl-wiz-seminar-registry]", function (event, btn) {
            fromRegistry(W.group(btn.dataset.groupId));
            rerender();
        });
        D.on("click", "[data-wl-wiz-place]", function (event, btn) {
            var cfg = W.S.groups[btn.dataset.groupId];
            var part = cfg && cfg[btn.dataset.wlWizPlace];
            if (!part || !cfg.editable) return;
            part.place[btn.dataset.enrollment] = Number(btn.dataset.number);
            if (btn.dataset.wlWizPlace === "seminar" && cfg.lab.mode === "nested") cfg.lab.place = nestedFill(W.group(btn.dataset.groupId), cfg, cfg.lab.place);
            rerender();
        });
        D.on("input", "[data-wl-wiz-seminar-name]", function (event, field) {
            var sem = W.S.groups[field.dataset.groupId].seminar;
            sem.names[Number(field.dataset.wlWizSeminarName) - 1] = clip(field.value);
        });
        D.on("input", "[data-wl-wiz-lab-name]", function (event, field) {
            W.S.groups[field.dataset.groupId].lab.names[Number(field.dataset.wlWizLabName) - 1] = clip(field.value);
        });
        D.on("click", "[data-wl-wiz-lab-mode]", function (event, btn) {
            setLabMode(btn.dataset.groupId, btn.dataset.wlWizLabMode);
            rerender();
        });
        D.on("click", "[data-wl-wiz-lab-per]", function (event, btn) {
            W.S.groups[btn.dataset.groupId].lab.per = Number(btn.dataset.wlWizLabPer) || 2;
            setLabMode(btn.dataset.groupId, "nested");
            rerender();
        });
        D.on("click", "[data-wl-wiz-lab-count]", function (event, btn) {
            var cfg = W.S.groups[btn.dataset.groupId];
            cfg.lab.count = Number(btn.dataset.wlWizLabCount) || 2;
            setLabMode(btn.dataset.groupId, "flat");
            rerender();
        });
        D.on("click", "[data-wl-wiz-lab-fill]", function (event, btn) {
            var group = W.group(btn.dataset.groupId);
            var cfg = W.S.groups[group.id];
            cfg.lab.place = cfg.lab.mode === "nested" ? nestedAlphabet(group, cfg) : splitEven(students(group), cfg.lab.count, 0);
            rerender();
        });
    };

})(window);
