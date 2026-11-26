/*
 * «Bölgü sehrbazı» — addım 2–3: Seminar, Laboratoriya + başlanğıc vəziyyət (`window.EMSWorkloadWizard`, 2026-11-26).
 *
 * Vəziyyət (`W.S`): `selected` {qrup: true}; `rows` {sətir: {joint, fix}}; `groups` {qrup: {seminar, lab, editable,
 * reason}} — seminar `{numbers[], names[], units[], place{qeydiyyat: №}}`, lab `{mode: none|nested|flat, per,
 * numbers[], names[], place{}}`. Bölmələr jurnalın REAL nömrələri ilə saxlanılır (2026-11-26 review: «Lab-1
 * silinib, {2,3} qalıb» halında yenidən nömrələmə Lab-2-nin dərslərini başqa tələbələrə keçirirdi) — yeni bölmə ən
 * kiçik boş nömrəni alır. İç-içə rejimdə i-ci seminar alt qrupunun lab qrupları lab nömrələrinin [i·per, i·per+per)
 * dilimidir — bir lab qrupu iki seminar alt qrupunu qarışdırmır. Dərsi olan bölmənin tərkibi dəyişdirilmir.
 * Tələbə siyahısı yalnız jurnal varsa, səlahiyyət varsa və jurnal bağlı deyilsə dəyişdirilir.
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

    function range(n) { var out = []; for (var i = 1; i <= Math.min(n, MAX); i += 1) out.push(i); return out; }
    function size(part) { return part.numbers.length; }

    /** Bölmələrin real nömrələri: jurnalda ≥ 2 bölmə varsa onlar (boşluqlu da — {2,3}), yoxdursa yükdəki say. */
    function startNumbers(sections, fallback) {
        if (sections.length >= 2) return sections.map(function (s) { return s.number; }).slice(0, MAX);
        return fallback >= 2 ? range(fallback) : [];
    }

    function byNumber(sections) {
        var map = {};
        sections.forEach(function (x) { map[x.number] = x; });
        return map;
    }

    function initGroup(group) {
        var row = W.row(group.row_id);
        var journal = group.journal;
        var semSections = journal ? journal.seminar : [];
        var labSections = journal ? journal.lab : [];
        var single = row.groups.length === 1;
        var semFallback = 0;
        if (W.active(row, "seminar")) {
            var top = maxSub(row, group.id, "seminar");
            semFallback = top >= 2 ? top : single && row.subgroup_count >= 2 ? row.subgroup_count : 0;
        }
        var semMap = byNumber(semSections);
        var seminar = { numbers: startNumbers(semSections, semFallback), names: [], units: [], place: {} };
        seminar.numbers.forEach(function (n) {
            seminar.names.push(semMap[n] ? semMap[n].name : clip(group.name + n));
            seminar.units.push(semMap[n] ? semMap[n].unit_id : "");
        });
        var labFallback = 0;
        if (W.active(row, "lab")) {
            var labTop = maxSub(row, group.id, "lab");
            var rowLab = row.lab_group_count || row.subgroup_count;
            labFallback = labTop >= 2 ? labTop : single && rowLab >= 2 ? rowLab : 0;
        }
        var labMap = byNumber(labSections);
        var lab = { mode: "none", per: 2, numbers: startNumbers(labSections, labFallback), names: [], place: {} };
        (journal ? journal.students : []).forEach(function (st) {
            if (st.seminar && seminar.numbers.indexOf(st.seminar) >= 0) seminar.place[st.id] = st.seminar;
            if (st.lab && lab.numbers.indexOf(st.lab) >= 0) lab.place[st.id] = st.lab;
        });
        var semCount = size(seminar), labCount = size(lab);
        if (labCount) {
            var nested = semCount >= 2 && labCount % semCount === 0;
            var per = nested ? labCount / semCount : 2;
            if (nested && journal) {
                journal.students.forEach(function (st) {
                    var li = lab.numbers.indexOf(lab.place[st.id]);
                    var si = seminar.numbers.indexOf(seminar.place[st.id]);
                    if (li >= 0 && si >= 0 && Math.floor(li / per) !== si) nested = false;
                });
            }
            lab.mode = nested ? "nested" : "flat";
            lab.per = nested ? per : 2;
        }
        lab.numbers.forEach(function (n, i) { lab.names.push(labMap[n] ? labMap[n].name : defaultLabName(group, seminar, lab, i)); });
        var editable = !!(journal && journal.can_manage && !journal.block_reason);
        var reason = !journal
            ? ""
            : journal.block_reason || (!journal.can_manage ? gettext("Bu jurnalın bölmələrini dəyişməyə icazəniz yoxdur.") : "");
        return { seminar: seminar, lab: lab, editable: editable, reason: reason };
    }

    /** Lab qrupunun defolt adı (`i` — sıradakı indeks): iç-içə — «234 K1 · Lab-1», müstəqil — «234 K · Lab-№». */
    function defaultLabName(group, seminar, lab, i) {
        if (lab.mode === "nested" && size(seminar) >= 2) {
            var si = Math.floor(i / lab.per);
            var base = seminar.names[si] || group.name + seminar.numbers[si];
            return clip(base + " · Lab-" + ((i % lab.per) + 1));
        }
        return clip(group.name + " · Lab-" + lab.numbers[i]);
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

    /** `{№: say, 0: yerləşməyən}`. */
    function counts(place, numbers, list) {
        var out = { 0: 0 };
        numbers.forEach(function (n) { out[n] = 0; });
        list.forEach(function (st) {
            var v = place[st.id];
            if (v && out[v] != null) out[v] += 1;
            else out[0] += 1;
        });
        return out;
    }

    /** Əlifba ilə bərabər bölmə (siyahı soyad sırası ilə gəlir) — dəyərlər `numbers`-dəki real nömrələrdir. */
    function splitEven(list, numbers) {
        var place = {};
        var n = numbers.length;
        if (!n) return place;  // bərabər: ölçülər ən çox 1 fərqlənir (10 / 3 → 4 · 3 · 3)
        var base = Math.floor(list.length / n), extra = list.length % n, k = 0;
        numbers.forEach(function (num, j) {
            var take = base + (j < extra ? 1 : 0);
            for (var t = 0; t < take; t += 1, k += 1) place[list[k].id] = num;
        });
        return place;
    }

    /** Sayı dəyiş: mövcud nömrələr saxlanır (artıqlar sondan düşür), yenilər ən kiçik boş nömrəni alır. */
    function resize(part, count, defaults) {
        if (count < 2) {
            part.numbers = [];
            part.names = [];
            if (part.units) part.units = [];
            part.place = {};
            return;
        }
        var keep = part.numbers.slice(0, count);
        var names = part.names.slice(0, count);
        var units = part.units ? part.units.slice(0, count) : null;
        for (var n = 1; n <= MAX && keep.length < count; n += 1) {
            if (keep.indexOf(n) >= 0) continue;
            keep.push(n);
            names.push(defaults(n));
            if (units) units.push("");
        }
        var order = keep.map(function (number, i) { return i; }).sort(function (a, b) { return keep[a] - keep[b]; });
        part.numbers = order.map(function (i) { return keep[i]; });
        part.names = order.map(function (i) { return names[i]; });
        if (units) part.units = order.map(function (i) { return units[i]; });
        Object.keys(part.place).forEach(function (id) { if (part.numbers.indexOf(part.place[id]) < 0) delete part.place[id]; });
    }

    function setSeminarCount(groupId, count) {
        var group = W.group(groupId);
        var cfg = W.S.groups[groupId];
        var pattern = (cfg.seminar.names || []).filter(function (x) { return /\d+$/.test(x || ""); })[0], prefix = pattern ? pattern.replace(/\d+$/, "") : group.name;
        resize(cfg.seminar, count, function (n) { return clip(prefix + n); });
        if (size(cfg.seminar) < 2) {
            if (cfg.lab.mode === "nested") setLabMode(groupId, "flat");
        } else if (cfg.lab.mode === "nested") {
            setLabMode(groupId, "nested");
        }
    }

    function setLabMode(groupId, mode, count) {
        var group = W.group(groupId);
        var cfg = W.S.groups[groupId];
        var lab = cfg.lab;
        var semCount = size(cfg.seminar);
        if (mode === "nested" && semCount < 2) mode = "flat";
        // QA 2026-11-26: rejim dəyişəndə köhnə yerləşdirmə (başqa quruluşdan qalan) yeni təkliflə əvəzlənir.
        var changed = lab.mode !== mode; if (changed) lab.place = {};
        lab.mode = mode;
        var target = 0;
        if (mode === "nested") {
            lab.per = Math.max(2, Math.min(lab.per || 2, Math.floor(MAX / semCount)));
            target = semCount * lab.per;
        } else if (mode === "flat") {
            target = Math.max(2, count || (changed ? 2 : size(lab)) || 2);
        }
        resize(lab, target, function (n) { return clip(group.name + " · Lab-" + n); });
        lab.names = lab.numbers.map(function (n, i) { return defaultLabName(group, cfg.seminar, lab, i); });
        if (mode === "nested") lab.place = nestedFill(group, cfg, lab.place);
        // Heç kim yerləşməyibsə ilkin təklif əlifba ilədir (sonra əl ilə dəyişmək olar) — «kim haradadır» dərhal görünür.
        if (mode !== "none" && !Object.keys(lab.place).length) {
            lab.place = mode === "nested" ? nestedAlphabet(group, cfg) : splitEven(students(group), lab.numbers);
        }
    }

    /** Seminar alt qrupunun (№) lab qrupları (iç-içə rejim) — real lab nömrələri. */
    function labsOf(cfg, seminarNumber) {
        var si = cfg.seminar.numbers.indexOf(seminarNumber);
        return si < 0 ? [] : cfg.lab.numbers.slice(si * cfg.lab.per, si * cfg.lab.per + cfg.lab.per);
    }

    /** İç-içə rejim: tələbə öz seminar alt qrupunun lab qruplarındadır; uyğun olmayan/boş olan ən az dolu qrupa düşür. */
    function nestedFill(group, cfg, current) {
        if (!Object.keys(current || {}).length) return nestedAlphabet(group, cfg);
        var place = {};
        var sizes = {};
        var list = students(group);
        list.forEach(function (st) {
            var l = current[st.id];
            if (l && labsOf(cfg, cfg.seminar.place[st.id]).indexOf(l) >= 0) {
                place[st.id] = l;
                sizes[l] = (sizes[l] || 0) + 1;
            }
        });
        list.forEach(function (st) {
            if (place[st.id]) return;
            var options = labsOf(cfg, cfg.seminar.place[st.id]);
            if (!options.length) return;
            var best = options.reduce(function (a, b) { return (sizes[b] || 0) < (sizes[a] || 0) ? b : a; });
            place[st.id] = best;
            sizes[best] = (sizes[best] || 0) + 1;
        });
        return place;
    }

    function nestedAlphabet(group, cfg) {
        var place = {};
        cfg.seminar.numbers.forEach(function (s) {
            var members = students(group).filter(function (st) { return cfg.seminar.place[st.id] === s; });
            var labs = labsOf(cfg, s);
            if (!labs.length) return;
            var part = splitEven(members, labs);
            Object.keys(part).forEach(function (id) { place[id] = part[id]; });
        });
        return place;
    }

    /** Seminar alt qrupları reyestrdən: say, ad, mənbə alt qrup və tələbənin reyestr qrupu ilə yerləşdirmə. */
    function fromRegistry(group) {
        var regs = group.registry_subgroups || [];
        setSeminarCount(group.id, Math.min(regs.length, MAX));
        var sem = W.S.groups[group.id].seminar;
        sem.names = regs.slice(0, size(sem)).map(function (u) { return clip(u.name); });
        sem.units = regs.slice(0, size(sem)).map(function (u) { return u.id; });
        sem.place = {};
        students(group).forEach(function (st) {
            var index = sem.units.indexOf(st.unit_id);
            if (index >= 0) sem.place[st.id] = sem.numbers[index];
        });
        if (W.S.groups[group.id].lab.mode === "nested") setLabMode(group.id, "nested");
    }

    function registryName(group, unitId) {
        var found = (group.registry_subgroups || []).filter(function (u) { return u.id === unitId; })[0];
        return found ? found.name : "";
    }

    // ── 2. Seminar ──────────────────────────────────────────────────────────
    // Ortaq UI parçaları `workload_split_wizard_groups.js`-dədir (`W.ui`) — modul ölçüsü büdcəsi.
    function notice(kind, text, extra) { return W.ui.notice(kind, text, extra); }
    function journalNotice(group) { return W.ui.journalNotice(group); }
    function segment(attr, groupId, options, current, disabled) { return W.ui.segment(attr, groupId, options, current, disabled); }

    function sectionChips(kind, group, part) {
        var list = students(group);
        var c = counts(part.place, part.numbers, list);
        var cfg = W.S.groups[group.id];
        var html = '<div class="wl-wiz-secs">';
        part.numbers.forEach(function (n, i) {
            html += '<label class="wl-wiz-sec wl-wiz-c' + (i + 1) + '"><span class="wl-wiz-sec__no">' + n + "</span>" +
                '<input type="text" maxlength="40" value="' + esc(part.names[i]) + '" placeholder="' + esc(group.name + n) + '" data-wl-wiz-' + kind + '-name="' + n +
                '" data-group-id="' + esc(group.id) + '"' + (cfg.editable || !group.journal ? "" : " disabled") + ' aria-label="' + esc(fmt(gettext("%(n)s-ci bölmənin adı"), { n: n })) + '">' +
                (group.journal ? '<span class="wl-wiz-sec__count">' + esc(fmt(gettext("%(n)s tələbə"), { n: c[n] })) + "</span>" : "") + "</label>";
        });
        html += "</div>";
        if (group.journal && c[0]) html += notice("warn", fmt(gettext("Heç bir bölməyə yerləşdirilməyib: %(n)s tələbə."), { n: c[0] }));
        return html;
    }

    function studentRows(kind, group, allowed) {
        var cfg = W.S.groups[group.id];
        var part = cfg[kind];
        var list = students(group);
        if (!list.length) return group.journal ? notice("info", gettext("Jurnalda aktiv tələbə yoxdur.")) : "";
        return '<div class="wl-wiz-students">' + list.map(function (st) {
            var current = part.place[st.id] || 0;
            var reg = registryName(group, st.unit_id);
            var buttons = "";
            part.numbers.forEach(function (n, i) {
                if (allowed && !allowed(st, n)) return;
                buttons += '<button type="button" class="wl-wiz-place wl-wiz-c' + (i + 1) + (current === n ? " is-on" : "") + '" data-wl-wiz-place="' + kind +
                    '" data-number="' + n + '" data-group-id="' + esc(group.id) + '" data-enrollment="' + esc(st.id) + '" aria-pressed="' +
                    (current === n ? "true" : "false") + '" title="' + esc(part.names[i] || "") + '"' + (cfg.editable ? "" : " disabled") + ">" + n + "</button>";
            });
            return '<div class="wl-wiz-st' + (current ? "" : " is-unplaced") + '" data-wl-wiz-student="' + esc(st.id) + '">' +
                '<span class="wl-wiz-st__name">' + esc(st.name) + "</span>" +
                (reg ? '<span class="wl-wiz-st__reg">' + esc(reg) + "</span>" : "") +
                '<span class="wl-wiz-st__btns">' + buttons + "</span></div>";
        }).join("") + "</div>";
    }

    /** Dərsi olan bölmə: silinə bilməz və tərkibi (tələbələri) dəyişməməlidir — server də eyni qaydanı yoxlayır. */
    function lessonIssues(group, kind) {
        var part = W.S.groups[group.id][kind];
        var issues = [];
        (group.journal ? group.journal[kind] : []).forEach(function (s) {
            if (!s.lessons) return;
            if (part.numbers.indexOf(s.number) < 0) {
                issues.push({ section: s, removed: true });
                return;
            }
            var changed = students(group).some(function (st) { return (st[kind] === s.number) !== (part.place[st.id] === s.number); });
            issues.push({ section: s, removed: false, changed: changed });
        });
        return issues;
    }

    function lessonWarnings(group, kind) {
        return lessonIssues(group, kind).map(function (issue) {
            var s = issue.section;
            if (issue.removed) {
                return notice("warn", fmt(gettext("«%(name)s» bölməsinə %(n)s dərs bağlıdır — bu bölmə silinə bilməz. Əvvəlcə jurnalda həmin dərslərin bölməsini dəyişin."), { name: s.label, n: s.lessons }));
            }
            return notice(issue.changed ? "warn" : "info", fmt(gettext("«%(name)s» bölməsinə %(n)s dərs bağlıdır — onun tələbələri burada dəyişdirilmir (tələbəni jurnalın öz ekranında köçürün)."), { name: s.label, n: s.lessons }));
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
        if (size(sem) > 4) options.push({ value: size(sem), label: fmt(gettext("%(n)s alt qrup"), { n: size(sem) }) });
        var locked = !!group.journal && !cfg.editable;
        var html = '<article class="wl-wiz-gp" data-wl-wiz-gpanel="' + esc(group.id) + '"><header class="wl-wiz-gp__head"><h4>' + esc(group.name) + "</h4>" +
            '<span class="wl-wiz-gp__meta">' + esc(fmt(gettext("%(n)s tələbə · seminar planı %(h)s (bir alt qrup üçün)"), { n: group.journal ? group.student_count : row.student_count, h: W.hours(row.plans.seminar) })) + "</span></header>" +
            journalNotice(group) + segment("data-wl-wiz-seminar-count", group.id, options, size(sem), locked);
        if (size(sem) >= 2) {
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
            html += (helpers ? '<div class="wl-wiz-helpers">' + helpers + "</div>" : "") + sectionChips("seminar", group, sem);
            html += studentRows("seminar", group, null);
        } else if (group.journal) {
            html += notice("info", gettext("Seminar bütün qrupla keçir — bir bölmə, bir müəllim."));
        }
        html += lessonWarnings(group, "seminar");
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
                if (size(part) >= 2) {
                    var c = counts(part.place, part.numbers, students(group));
                    if (c[0]) problems.push(fmt(gettext("%(group)s: %(n)s tələbə yerləşdirilməyib."), { group: group.name, n: c[0] }));
                    // QA 2026-11-26: boş bölmə (məs. 2 → 3 alt qrup, köhnə yerləşdirmə saxlanıb) — müəllim saatı boş bölməyə yazılmasın.
                    if (students(group).length) {
                        part.numbers.forEach(function (n, i) {
                            if (!c[n]) problems.push(fmt(gettext("%(group)s: «%(name)s» bölməsində tələbə yoxdur — tələbə yerləşdirin və ya bölmə sayını azaldın."), { group: group.name, name: part.names[i] || String(n) }));
                        });
                    }
                    var seen = {};
                    part.names.forEach(function (name) {
                        var key = String(name || "").toLowerCase().replace(/[\s-]+/g, "");
                        if (key && seen[key]) problems.push(fmt(gettext("%(group)s: iki bölmənin adı eynidir."), { group: group.name }));
                        seen[key] = true;
                    });
                }
                lessonIssues(group, kind).forEach(function (issue) {
                    if (issue.removed || issue.changed) problems.push(fmt(gettext("%(group)s: «%(name)s» bölməsinə dərs bağlıdır."), { group: group.name, name: issue.section.label }));
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
        var canNest = size(cfg.seminar) >= 2;
        var html = '<article class="wl-wiz-gp" data-wl-wiz-gpanel="' + esc(group.id) + '"><header class="wl-wiz-gp__head"><h4>' + esc(group.name) + "</h4>" +
            '<span class="wl-wiz-gp__meta">' + esc(fmt(gettext("lab planı %(h)s (bir lab qrupu üçün)"), { h: W.hours(row.plans.lab) })) + "</span></header>" +
            journalNotice(group) +
            segment("data-wl-wiz-lab-mode", group.id, [
                { value: "none", label: gettext("Bölünmür") },
                { value: "nested", label: fmt(gettext("Hər seminar alt qrupunu böl (%(n)s alt qrup)"), { n: size(cfg.seminar) }), disabled: !canNest, title: canNest ? "" : gettext("Əvvəlcə seminarı alt qruplara bölün.") },
                { value: "flat", label: gettext("Seminardan asılı olmadan") },
            ], lab.mode, locked);
        if (lab.mode === "nested") {
            html += '<div class="wl-wiz-row"><span class="wl-wiz-row__label">' + esc(gettext("Hər seminar alt qrupunda neçə lab qrupu:")) + "</span>" +
                segment("data-wl-wiz-lab-per", group.id, [2, 3, 4].filter(function (n) { return n * size(cfg.seminar) <= MAX; }).map(function (n) { return { value: n, label: String(n) }; }), lab.per, locked) + "</div>";
        } else if (lab.mode === "flat") {
            html += '<div class="wl-wiz-row"><span class="wl-wiz-row__label">' + esc(gettext("Lab qrupu sayı:")) + "</span>" +
                segment("data-wl-wiz-lab-count", group.id, [2, 3, 4, 5, 6].map(function (n) { return { value: n, label: String(n) }; }), size(lab), locked) + "</div>";
        }
        if (lab.mode !== "none") {
            if (group.journal) {
                html += '<div class="wl-wiz-helpers"><button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-wiz-lab-fill data-group-id="' + esc(group.id) + '"' + (cfg.editable ? "" : " disabled") + '>' +
                    '<i class="fas fa-arrow-down-a-z" aria-hidden="true"></i> ' + esc(lab.mode === "nested" ? gettext("Seminar alt qrupundan doldur (əlifba ilə)") : gettext("Əlifba ilə bərabər böl")) + "</button></div>";
            }
            html += sectionChips("lab", group, lab);
            html += studentRows("lab", group, lab.mode === "nested"
                ? function (st, n) { var s = cfg.seminar.place[st.id]; return !s || labsOf(cfg, s).indexOf(n) >= 0; }
                : null);
        } else if (group.journal) {
            html += notice("info", gettext("Laboratoriya bütün qrupla keçir — bir bölmə, bir müəllim."));
        }
        html += lessonWarnings(group, "lab");
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
                    if (s && l && labsOf(cfg, s).indexOf(l) < 0) mixed = fmt(gettext("%(name)s başqa seminar alt qrupunun lab qrupundadır."), { name: st.name });
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
                if (count >= 2 && !Object.keys(sem.place).length) sem.place = splitEven(students(group), sem.numbers);
            }
            rerender();
        });
        D.on("click", "[data-wl-wiz-seminar-alpha]", function (event, btn) {
            var cfg = W.S.groups[btn.dataset.groupId];
            cfg.seminar.place = splitEven(students(W.group(btn.dataset.groupId)), cfg.seminar.numbers);
            if (cfg.lab.mode === "nested") cfg.lab.place = nestedFill(W.group(btn.dataset.groupId), cfg, cfg.lab.place);
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
            var i = sem.numbers.indexOf(Number(field.dataset.wlWizSeminarName));
            if (i >= 0) sem.names[i] = clip(field.value);
        });
        D.on("input", "[data-wl-wiz-lab-name]", function (event, field) {
            var lab = W.S.groups[field.dataset.groupId].lab;
            var i = lab.numbers.indexOf(Number(field.dataset.wlWizLabName));
            if (i >= 0) lab.names[i] = clip(field.value);
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
            setLabMode(btn.dataset.groupId, "flat", Number(btn.dataset.wlWizLabCount) || 2);
            rerender();
        });
        D.on("click", "[data-wl-wiz-lab-fill]", function (event, btn) {
            var group = W.group(btn.dataset.groupId);
            var cfg = W.S.groups[group.id];
            cfg.lab.place = cfg.lab.mode === "nested" ? nestedAlphabet(group, cfg) : splitEven(students(group), cfg.lab.numbers);
            rerender();
        });
    };

    // Əsas fayl artıq bağlayıbsa (bu modul sonra yükləndi) — dinləyiciləri indi bağla.
    if (W.bindModules && window.__emsWorkloadWizardBound) W.bindModules();
})(window);
