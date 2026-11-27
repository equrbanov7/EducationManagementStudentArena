/*
 * «Bölgü sehrbazı» — addım 4–5: Müəllimlər, Yoxla + server gövdəsi (`window.EMSWorkloadWizard`, sahib 2026-11-26).
 *
 * Vahid (bölmə) = sətir × fəaliyyət × qrup × alt qrup №. Vahidlər seminar/lab konfiqurasiyasından törədilir —
 * qayda serverdəki `split_wizard_apply.expected_units` ilə EYNİDİR (server fərq görsə heç nə yazmır):
 *   birlikdə keçən sətir → bir vahid (qrupsuz); qrup bölünməyib → (qrup, —); N alt qrup → (qrup, 1..N).
 * Vahid vəziyyəti (`W.S.units[açar]`) ilk göstərişdə mövcud bölgüdən doldurulur: bir bölgü → onun müəllimi/saatı;
 * bir neçə bölgü → «saxla» (toxunulmur, müəllim seçilənə qədər); heç biri → boş, saat = qrup planı.
 * «Yoxla»: cəm təklifi (seminar/lab cəmi, alt qrup və lab qrupu sayı — `split_wizard_apply._totals_data` güzgüsü),
 * aşma xətası, silinəcək köhnə bölgülər, xülasə cədvəli.
 */
(function (window) {
    "use strict";

    var W = (window.EMSWorkloadWizard = window.EMSWorkloadWizard || {});
    W.render = W.render || {};
    W.validate = W.validate || {};
    var KINDS = ["seminar", "lab"];

    var gettext = window.gettext || function (value) { return value; };
    function esc(v) { return W.esc(v); }
    function fmt(a, b) { return W.fmt(a, b); }
    function kindLabel(activity) {
        return activity === "lecture" ? gettext("Mühazirə") : activity === "seminar" ? gettext("Seminar") : gettext("Laboratoriya");
    }

    // ── vahidlər ────────────────────────────────────────────────────────────
    W.unitKeys = function (row) {
        var out = { seminar: [], lab: [] };
        KINDS.forEach(function (activity) {
            if (!W.active(row, activity)) return;
            if (W.isJoint(row, activity)) { out[activity].push({ group: "", sub: null }); return; }
            row.groups.forEach(function (groupId) {
                var numbers = W.S.groups[groupId][activity].numbers;
                if (numbers.length >= 2) numbers.forEach(function (n) { out[activity].push({ group: groupId, sub: n }); });
                else out[activity].push({ group: groupId, sub: null });
            });
        });
        return out;
    };

    function key(row, activity, unit) { return [activity, row.id, unit.group, unit.sub || ""].join("|"); }

    function assignmentKey(row, a) {
        var group = a.group_id || (row.groups.length === 1 ? row.groups[0] : "");
        return [a.activity, row.id, group, a.sub_number || ""].join("|");
    }

    function existing(row, unitKey) {
        return row.assignments.filter(function (a) { return KINDS.indexOf(a.activity) >= 0 && assignmentKey(row, a) === unitKey; });
    }

    W.unitState = function (row, activity, unit) {
        var k = key(row, activity, unit);
        if (!W.S.units[k]) {
            var found = existing(row, k);
            var st = { teacher: "", hours: row.plans[activity] || 0, hourly: false, keep: false, found: found };
            if (found.length === 1) {
                st.teacher = found[0].is_vacant ? W.VACANT : String(found[0].teacher_id);
                st.hours = found[0].hours;
                st.hourly = !!found[0].is_hourly_paid;
            } else if (found.length > 1) {
                st.keep = true;
                st.hours = found.reduce(function (sum, a) { return sum + a.hours; }, 0);
            } else if (unit.sub) {
                // Bütün qrupa yazılmış müəllim yeni alt qruplara ilkin təklif kimi keçir (sonra dəyişmək olar).
                var whole = existing(row, key(row, activity, { group: unit.group, sub: null }));
                if (whole.length === 1 && !whole[0].is_vacant) st.teacher = String(whole[0].teacher_id);
            }
            W.S.units[k] = st;
        }
        return W.S.units[k];
    };

    function unitLabel(row, activity, unit) {
        if (!unit.group) return fmt(gettext("%(kind)s — %(groups)s (birlikdə)"), { kind: kindLabel(activity), groups: row.label });
        var group = W.group(unit.group);
        if (!unit.sub) return fmt(gettext("%(kind)s — %(group)s (bütün qrup)"), { kind: kindLabel(activity), group: group.name });
        return kindLabel(activity) + " — " + W.sectionLabel(row, unit.group, activity, unit.sub);
    }

    function unitSize(unit, activity) {
        if (!unit.group) return null;
        return W.sectionSize(unit.group, activity, unit.sub);
    }

    function lectureState(row) {
        if (!W.S.lecture[row.id]) {
            var lectures = row.assignments.filter(function (a) { return a.activity === "lecture"; });
            var initial = lectures.length === 1 ? (lectures[0].is_vacant ? W.VACANT : String(lectures[0].teacher_id)) : "";
            W.S.lecture[row.id] = { teacher: initial, initial: initial };
        }
        return W.S.lecture[row.id];
    }

    /** Fəaliyyət üzrə paylanan saat (saxlanan bölgülər daxil). */
    function assigned(row, activity) {
        var sum = 0;
        W.unitKeys(row)[activity].forEach(function (unit) {
            var st = W.unitState(row, activity, unit);
            if (st.keep) sum += st.hours;
            else if (st.teacher) sum += Number(st.hours) || 0;
        });
        return sum;
    }

    /** `split_wizard_apply._totals_data` güzgüsü — sətrin düzəlişi (boş = lazım deyil). */
    W.fixData = function (row) {
        var keys = W.unitKeys(row);
        var data = {}, counts = {};
        KINDS.forEach(function (activity) {
            if (!W.active(row, activity)) return;
            counts[activity] = keys[activity].length;
            var want = (row.plans[activity] || 0) * counts[activity];
            if (want !== row.totals[activity]) data[activity + "_total"] = want;
        });
        var sub = counts.seminar || row.subgroup_count;
        if (sub !== row.subgroup_count) data.subgroup_count = sub;
        var followsChangedSeminar = row.lab_group_count && sub !== row.subgroup_count && counts.lab === sub;
        if (counts.lab && (counts.lab !== (row.lab_group_count || sub) || followsChangedSeminar)) {
            data.lab_group_count = counts.lab === sub ? 0 : counts.lab;
        }
        return data;
    };

    function totalFor(row, activity) {
        var data = W.fixData(row);
        var fix = W.S.rows[row.id].fix && W.S.data.task.can_fix_totals;
        return fix && data[activity + "_total"] != null ? data[activity + "_total"] : row.totals[activity];
    }

    // ── 4. Müəllimlər ───────────────────────────────────────────────────────
    function counter(row, activity) {
        var total = totalFor(row, activity);
        var used = assigned(row, activity);
        var cls = used > total ? " is-over" : used === total ? " is-ok" : "";
        return '<span class="wl-wiz-counter' + cls + '" data-wl-wiz-counter="' + esc(row.id + "|" + activity) + '">' +
            esc(fmt(gettext("paylanıb %(used)s / cəmi %(total)s"), { used: W.hours(used), total: W.hours(total) })) + "</span>";
    }

    function lectureBlock(row) {
        if (!W.active(row, "lecture") && !row.partner) return "";
        var html = '<div class="wl-wiz-act wl-wiz-act--lecture"><div class="wl-wiz-act__head"><span class="wl-wiz-act__title">' + esc(gettext("Mühazirə")) + "</span></div>";
        if (row.partner) {
            html += '<p class="wl-wiz-act__info">' + esc(fmt(gettext("Axında keçir: aparıcı «%(groups)s», mühazirəçi — %(teacher)s. Dəyişmək üçün kartda «Axınları dəyiş»."), {
                groups: row.partner.lead_groups || "—", teacher: row.partner.teacher_name || gettext("Vakant"),
            })) + "</p>";
        } else if (row.lecture_editable) {
            var st = lectureState(row);
            var extra = row.assignments.filter(function (a) { return a.activity === "lecture" && a.teacher_id; }).map(function (a) { return { id: a.teacher_id, name: a.teacher_name }; });
            html += '<div class="wl-wiz-unit" data-wl-wiz-unit="' + esc("lecture|" + row.id) + '"><span class="wl-wiz-unit__label">' +
                esc(fmt(gettext("Mühazirə — %(groups)s (bütün qrup)"), { groups: row.label })) + "</span>" +
                '<span class="wl-wiz-unit__size"></span><span class="wl-wiz-unit__teacher">' +
                W.select('data-wl-wiz-lecture="' + esc(row.id) + '" aria-label="' + esc(gettext("Mühazirəçi")) + '"', W.teacherOptions(st.teacher, extra), true) + "</span>" +
                '<span class="wl-wiz-unit__hours">' + esc(W.hours(row.totals.lecture)) + "</span></div>";
        } else {
            var names = row.assignments.filter(function (a) { return a.activity === "lecture"; }).map(function (a) { return a.teacher_name + " (" + W.hours(a.hours) + ")"; });
            html += '<p class="wl-wiz-act__info">' + esc(fmt(gettext("Mühazirə bir neçə müəllim arasında bölünüb: %(list)s. Dəyişmək üçün «Ətraflı cədvəl»."), { list: names.join(", ") || "—" })) + "</p>";
        }
        return html + "</div>";
    }

    function activityBlock(row, activity) {
        var units = W.unitKeys(row)[activity];
        if (!units.length) return "";
        var html = '<div class="wl-wiz-act"><div class="wl-wiz-act__head"><span class="wl-wiz-act__title">' + esc(kindLabel(activity)) + "</span>" +
            counter(row, activity) +
            (units.length > 1
                ? '<label class="wl-wiz-act__all"><span>' + esc(gettext("Hamısına:")) + "</span>" +
                  W.select('data-wl-wiz-teacher-all="' + esc(row.id + "|" + activity) + '" aria-label="' + esc(gettext("Bütün bölmələrə eyni müəllim")) + '"', W.teacherOptions(""), true) + "</label>"
                : "") +
            "</div>";
        units.forEach(function (unit) {
            var k = key(row, activity, unit);
            var st = W.unitState(row, activity, unit);
            var size = unitSize(unit, activity);
            var extra = st.found.filter(function (a) { return a.teacher_id; }).map(function (a) { return { id: a.teacher_id, name: a.teacher_name }; });
            html += '<div class="wl-wiz-unit' + (st.teacher || st.keep ? "" : " is-empty") + '" data-wl-wiz-unit="' + esc(k) + '">' +
                '<span class="wl-wiz-unit__label">' + esc(unitLabel(row, activity, unit)) + "</span>" +
                '<span class="wl-wiz-unit__size">' + (size != null ? esc(fmt(gettext("%(n)s tələbə"), { n: size })) : "") + "</span>" +
                '<span class="wl-wiz-unit__teacher">' +
                (st.keep
                    ? '<span class="wl-wiz-unit__keep">' + esc(fmt(gettext("Saxlanır: %(list)s"), { list: st.found.map(function (a) { return a.teacher_name + " " + W.hours(a.hours); }).join(", ") })) + "</span>"
                    : "") +
                W.select('data-wl-wiz-teacher="' + esc(k) + '" aria-label="' + esc(gettext("Müəllim")) + '"', W.teacherOptions(st.keep ? "" : st.teacher, extra), true) + "</span>" +
                '<span class="wl-wiz-unit__hours"><input type="number" min="1" value="' + esc(st.hours) + '" data-wl-wiz-hours="' + esc(k) + '" aria-label="' + esc(gettext("Saat")) + '"' + (st.keep ? " disabled" : "") + "></span>" +
                '<label class="wl-wiz-unit__hourly"><input type="checkbox" data-wl-wiz-hourly="' + esc(k) + '"' + (st.hourly ? " checked" : "") + (st.keep ? " disabled" : "") + "> " + esc(gettext("saathesabı")) + "</label>" +
                "</div>";
        });
        var need = (row.plans[activity] || 0) * units.length;
        if (need !== row.totals[activity]) {
            html += '<p class="wl-wiz-note wl-wiz-note--info"><i class="fas fa-circle-info" aria-hidden="true"></i> <span>' +
                esc(fmt(gettext("Sətrin %(kind)s cəmi %(total)s, bölmələrə görə isə %(need)s lazımdır — «Yoxla» addımında sətri bir kliklə düzəldə bilərsiniz."), {
                    kind: kindLabel(activity).toLowerCase(), total: W.hours(row.totals[activity]), need: W.hours(need),
                })) + "</span></p>";
        }
        return html + "</div>";
    }

    W.render.teachers = function (panel) {
        if (!panel) return;
        var html = "";
        W.selectedRows().forEach(function (row) {
            html += '<section class="wl-wiz-trow"><h4 class="wl-wiz-trow__title">' + esc(row.label) + "</h4>" +
                lectureBlock(row) + activityBlock(row, "seminar") + activityBlock(row, "lab") + "</section>";
        });
        panel.innerHTML = html;
        W.initSelects(panel);
    };

    W.validate.teachers = function () {
        var bad = "";
        W.selectedRows().forEach(function (row) {
            KINDS.forEach(function (activity) {
                W.unitKeys(row)[activity].forEach(function (unit) {
                    var st = W.unitState(row, activity, unit);
                    if (!bad && !st.keep && st.teacher && !(Number(st.hours) > 0)) bad = fmt(gettext("%(unit)s: saat sıfırdan böyük olmalıdır."), { unit: unitLabel(row, activity, unit) });
                });
            });
        });
        return bad;
    };

    // ── 5. Yoxla ────────────────────────────────────────────────────────────
    /** Silinəcək köhnə bölgülər (server `_plan_writes` güzgüsü). */
    function removals(row) {
        var used = {};
        var out = [];
        KINDS.forEach(function (activity) {
            W.unitKeys(row)[activity].forEach(function (unit) {
                var k = key(row, activity, unit);
                var st = W.unitState(row, activity, unit);
                var found = existing(row, k);
                found.forEach(function (a, i) {
                    used[a.id] = true;
                    if (st.keep) return;
                    if (!st.teacher || i > 0) out.push(a);
                });
            });
        });
        row.assignments.forEach(function (a) { if (KINDS.indexOf(a.activity) >= 0 && !used[a.id]) out.push(a); });
        return out;
    }

    function overProblems() {
        var problems = [];
        W.selectedRows().forEach(function (row) {
            KINDS.forEach(function (activity) {
                if (!W.unitKeys(row)[activity].length) return;
                var used = assigned(row, activity), total = totalFor(row, activity);
                if (used > total) {
                    problems.push(fmt(gettext("%(groups)s: %(kind)s üçün %(used)s paylanıb, sətrin cəmi %(total)s. «Sətri düzəlt» seçin və ya saatı azaldın."), {
                        groups: row.label, kind: kindLabel(activity).toLowerCase(), used: W.hours(used), total: W.hours(total),
                    }));
                }
            });
        });
        return problems;
    }

    function fixCard(row) {
        var data = W.fixData(row);
        if (!Object.keys(data).length) return "";
        var lines = [];
        KINDS.forEach(function (activity) {
            if (data[activity + "_total"] != null) {
                lines.push(fmt(gettext("%(kind)s cəmi: %(old)s → %(new)s"), { kind: kindLabel(activity), old: W.hours(row.totals[activity]), new: W.hours(data[activity + "_total"]) }));
            }
        });
        if (data.subgroup_count != null) lines.push(fmt(gettext("Qrup/yarımqrup sayı: %(old)s → %(new)s"), { old: row.subgroup_count, new: data.subgroup_count }));
        if (data.lab_group_count != null) lines.push(fmt(gettext("Lab qrupu sayı: %(old)s → %(new)s"), { old: row.lab_group_count || "—", new: data.lab_group_count || "—" }));
        var on = W.S.rows[row.id].fix;
        var can = W.S.data.task.can_fix_totals;
        return '<div class="wl-wiz-fix' + (on ? " is-on" : "") + '"><div class="wl-wiz-fix__text"><strong>' + esc(fmt(gettext("%(groups)s — sətrin saatı bölmələrə uyğun deyil"), { groups: row.label })) + "</strong>" +
            "<ul>" + lines.map(function (line) { return "<li>" + esc(line) + "</li>"; }).join("") + "</ul></div>" +
            (can
                ? '<button type="button" class="wl-btn ' + (on ? "wl-btn--primary" : "wl-btn--ghost") + ' wl-btn--sm" data-wl-wiz-fix-totals="' + esc(row.id) + '" aria-pressed="' + on + '">' +
                  '<i class="fas ' + (on ? "fa-check" : "fa-wand-magic-sparkles") + '" aria-hidden="true"></i> ' + esc(on ? gettext("Düzəldiləcək") : gettext("Sətri düzəlt")) + "</button>"
                : '<span class="wl-wiz-fix__no">' + esc(gettext("Bu mərhələdə sətrin cəmi dəyişdirilmir — tədris şöbəsinə müraciət edin.")) + "</span>") +
            "</div>";
    }

    function summaryRows(row) {
        var html = "";
        if (row.lecture_editable && W.active(row, "lecture")) {
            var st = lectureState(row);
            html += "<tr><td>" + esc(fmt(gettext("Mühazirə — %(groups)s"), { groups: row.label })) + "</td><td>—</td><td>" + esc(W.teacherName(st.teacher)) +
                (st.teacher !== st.initial ? ' <span class="wl-badge wl-badge--info">' + esc(gettext("dəyişir")) + "</span>" : "") + "</td><td>" + esc(W.hours(row.totals.lecture)) + "</td></tr>";
        }
        KINDS.forEach(function (activity) {
            W.unitKeys(row)[activity].forEach(function (unit) {
                var u = W.unitState(row, activity, unit);
                var size = unitSize(unit, activity);
                var who = u.keep ? u.found.map(function (a) { return a.teacher_name; }).join(", ") : W.teacherName(u.teacher);
                html += '<tr class="' + (u.teacher || u.keep ? "" : "is-empty") + '"><td>' + esc(unitLabel(row, activity, unit)) + "</td><td>" + (size != null ? esc(size) : "—") + "</td><td>" + esc(who) + "</td><td>" +
                    esc(u.teacher || u.keep ? W.hours(u.hours) : "—") + "</td></tr>";
            });
        });
        return html;
    }

    W.render.review = function (panel) {
        if (!panel) return;
        var rows = W.selectedRows();
        var html = "";
        rows.forEach(function (row) { html += fixCard(row); });
        overProblems().forEach(function (text) {
            html += '<p class="wl-wiz-note wl-wiz-note--error"><i class="fas fa-circle-xmark" aria-hidden="true"></i> <span>' + esc(text) + "</span></p>";
        });
        var empty = 0;
        var gone = [];
        rows.forEach(function (row) {
            KINDS.forEach(function (activity) {
                W.unitKeys(row)[activity].forEach(function (unit) { var st = W.unitState(row, activity, unit); if (!st.teacher && !st.keep) empty += 1; });
            });
            gone = gone.concat(removals(row));
        });
        if (empty) html += '<p class="wl-wiz-note wl-wiz-note--warn"><i class="fas fa-user-slash" aria-hidden="true"></i> <span>' + esc(fmt(gettext("%(n)s bölməyə müəllim seçilməyib — onların saatı «bölünməyib» qalacaq."), { n: empty })) + "</span></p>";
        if (gone.length) {
            html += '<div class="wl-wiz-note wl-wiz-note--warn"><i class="fas fa-trash-can" aria-hidden="true"></i> <span>' + esc(gettext("Bu köhnə bölgülər silinəcək:")) + "<ul>" +
                gone.map(function (a) { return "<li>" + esc(kindLabel(a.activity) + " · " + a.teacher_name + " · " + W.hours(a.hours)) + "</li>"; }).join("") + "</ul></span></div>";
        }
        if (W.S.data.task.needs_amendment) html += amendBlock();
        html += '<div class="wl-wiz-table-wrap"><table class="wl-wiz-table" data-wl-wiz-summary><thead><tr><th scope="col">' + esc(gettext("Bölmə")) + '</th><th scope="col">' + esc(gettext("Tələbə")) +
            '</th><th scope="col">' + esc(gettext("Müəllim")) + '</th><th scope="col">' + esc(gettext("Saat")) + "</th></tr></thead><tbody>";
        rows.forEach(function (row) { html += summaryRows(row); });
        html += "</tbody></table></div>";
        panel.innerHTML = html;
        W.initSelects(panel);
    };

    // QA 2026-11-26: təsdiqlənmiş bölgüdə səbəb + qeyd ELƏ BU addımda soruşulur — ayrıca dialoqda «Bağla»
    // basanda sehrbazın bütün seçimləri itirdi. Səbəblər səhifənin düzəliş formasındakı kataloqdan götürülür.
    function amendState() {
        W.S.amend = W.S.amend || { reason: "", note: "" };
        return W.S.amend;
    }

    function amendBlock() {
        var st = amendState();
        var source = document.querySelector("[data-wl-amend-form] select[name=reason]");
        var options = '<option value="">' + esc(gettext("— Səbəb seçin —")) + "</option>";
        if (source) {
            Array.prototype.forEach.call(source.options, function (opt) {
                if (!opt.value) return;
                options += '<option value="' + esc(opt.value) + '"' + (opt.value === st.reason ? " selected" : "") + ">" + esc(opt.textContent) + "</option>";
            });
        }
        return '<div class="wl-wiz-amend" data-wl-wiz-amend><p class="wl-wiz-amend__lead"><i class="fas fa-file-signature" aria-hidden="true"></i> ' +
            esc(gettext("Bölgü artıq təsdiqlənib — dəyişiklik audit jurnalına yazılır. Səbəbi seçin və qısa qeyd yazın.")) + "</p>" +
            '<label class="wl-wiz-amend__field"><span>' + esc(gettext("Səbəb")) + "</span>" +
            W.select('data-wl-wiz-amend-reason aria-label="' + esc(gettext("Səbəb")) + '"', options, false) + "</label>" +
            '<label class="wl-wiz-amend__field"><span>' + esc(gettext("Qeyd")) + "</span>" +
            '<textarea rows="2" maxlength="500" data-wl-wiz-amend-note placeholder="' + esc(gettext("Məsələn: seminar 2 alt qrupa bölündü")) + '">' + esc(st.note) + "</textarea></label></div>";
    }

    W.validate.review = function () {
        var problem = W.validate.teachers() || overProblems()[0] || "";
        if (problem || !W.S.data.task.needs_amendment) return problem;
        var st = amendState();
        return st.reason && st.note.trim() ? "" : gettext("Düzəliş səbəbi və qeydi məcburidir.");
    };

    // ── gövdə ───────────────────────────────────────────────────────────────
    W.payload = function () {
        var D = W.dist();
        var rows = W.selectedRows();
        var units = [], groups = [], lecture = [];
        rows.forEach(function (row) {
            row.groups.forEach(function (groupId) { groups.push(W.groupPayload(row, groupId)); });
            KINDS.forEach(function (activity) {
                W.unitKeys(row)[activity].forEach(function (unit) {
                    var st = W.unitState(row, activity, unit);
                    units.push({
                        row_id: row.id, activity: activity, group_id: unit.group, sub_number: unit.sub,
                        teacher_id: st.keep ? "" : st.teacher, hours: Number(st.hours) || 0, is_hourly_paid: !!st.hourly, keep: !!st.keep,
                    });
                });
            });
            if (row.lecture_editable) {
                var lec = lectureState(row);
                if (lec.teacher !== lec.initial) lecture.push({ row_id: row.id, teacher_id: lec.teacher || W.VACANT });
            }
        });
        var body = {
            task_id: D.state.task.id,
            row_ids: rows.map(function (row) { return row.id; }),
            rows: rows.map(function (row) {
                return { row_id: row.id, joint: W.isJoint(row, "seminar"), joint_by_activity: W.S.rows[row.id].joint_by_activity, fix_totals: !!(W.S.rows[row.id].fix && Object.keys(W.fixData(row)).length) };
            }),
            groups: groups,
            units: units,
            lecture: lecture,
        };
        if (W.S.data.task.needs_amendment) {
            var amend = amendState();
            body.amend_reason = amend.reason;
            body.amend_note = amend.note.trim();
        }
        return body;
    };

    function refreshCounters(row) {
        KINDS.forEach(function (activity) {
            var node = W.q('[data-wl-wiz-counter="' + (row.id + "|" + activity).replace(/"/g, "") + '"]');
            if (node) node.outerHTML = counter(row, activity);
        });
    }

    function unitFromKey(k) {
        var parts = String(k).split("|");
        var row = W.row(parts[1]);
        return row ? { row: row, activity: parts[0], unit: { group: parts[2], sub: parts[3] ? Number(parts[3]) : null } } : null;
    }

    W.bindUnits = function (D) {
        D.on("change", "[data-wl-wiz-teacher]", function (event, field) {
            var ref = unitFromKey(field.dataset.wlWizTeacher);
            if (!ref) return;
            var st = W.unitState(ref.row, ref.activity, ref.unit);
            if (st.keep) { st.keep = false; st.hours = ref.row.plans[ref.activity] || st.hours; }
            st.teacher = field.value;
            W.render.teachers(W.q('[data-wl-wiz-panel="teachers"]'));
        });
        D.on("change", "[data-wl-wiz-teacher-all]", function (event, field) {
            var parts = field.dataset.wlWizTeacherAll.split("|");
            var row = W.row(parts[0]);
            if (!row || !field.value) return;
            W.unitKeys(row)[parts[1]].forEach(function (unit) {
                var st = W.unitState(row, parts[1], unit);
                if (st.keep) { st.keep = false; st.hours = row.plans[parts[1]] || st.hours; }
                st.teacher = field.value;
            });
            W.render.teachers(W.q('[data-wl-wiz-panel="teachers"]'));
        });
        D.on("input", "[data-wl-wiz-hours]", function (event, field) {
            var ref = unitFromKey(field.dataset.wlWizHours);
            if (!ref) return;
            W.unitState(ref.row, ref.activity, ref.unit).hours = Number(field.value) || 0;
            refreshCounters(ref.row);
        });
        D.on("change", "[data-wl-wiz-hourly]", function (event, field) {
            var ref = unitFromKey(field.dataset.wlWizHourly);
            if (ref) W.unitState(ref.row, ref.activity, ref.unit).hourly = field.checked;
        });
        D.on("change", "[data-wl-wiz-lecture]", function (event, field) {
            var row = W.row(field.dataset.wlWizLecture);
            if (row) lectureState(row).teacher = field.value;
        });
        D.on("change", "[data-wl-wiz-amend-reason]", function (event, field) { amendState().reason = field.value; });
        D.on("input", "[data-wl-wiz-amend-note]", function (event, field) { amendState().note = field.value; });
        D.on("click", "[data-wl-wiz-fix-totals]", function (event, btn) {
            var state = W.S.rows[btn.dataset.wlWizFixTotals];
            if (!state) return;
            state.fix = !state.fix;
            W.render.review(W.q('[data-wl-wiz-panel="review"]'));
        });
    };
    // Əsas fayl artıq bağlayıbsa (bu modul sonra yükləndi) — dinləyiciləri indi bağla.
    if (W.bindModules && window.__emsWorkloadWizardBound) W.bindModules();
})(window);
