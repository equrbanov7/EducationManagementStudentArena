/*
 * «Yük bölgüsü» — fənn kartının SEÇİCİLƏRİ (`window.EMSWorkloadPickers`, sahib 2026-11-09).
 *
 *   1. «Axınları dəyiş» — mühazirə axınları (patok): hər tapşırıq sətri (qrup və ya qrup dəsti) bir axına salınır,
 *      hər axına mühazirəçi seçilir; qayda modalın özündə yazılıb. Yazı: POST `patok/axinlar/` (bir sorğu).
 *   2. «Bölüşdür» (seminar / laboratoriya) — cədvəl: qrup | müəllim | alt qrup (Lab-1 …) | saat; sətirlər əlavə /
 *      silinir; yazı mövcud `bolgu/` və `bolgu/sil/` endpoint-ləri ilə ARDICIL (düzəliş səbəbi bir dəfə soruşulur,
 *      sonrakı sorğulara köçürülür).
 *
 * Vəziyyət `EMSWorkloadDist`-dən (kartlar `state.cards`); yazı `EMSWorkloadAmend.write` ilə (409 → düzəliş dialoqu).
 * Dinləyicilər `EMSDelegate` ilə BİR dəfə; stilli seçicilər (`data-bootstrap-select`) əlavə olunan kimi
 * `bootstrap_select.js` tərəfindən avtomatik qoşulur. Xarici JS template-dən keçmir — mətnlər `gettext`, URL-lər
 * `[data-wl-root]` data-atributlarından.
 */
(function (window, document) {
    "use strict";

    var gettext = window.gettext || function (value) { return value; };
    var VACANT = "vacant";
    var pool = { key: "", items: [], promise: null };
    var S = { card: null, units: [], lecturers: {}, touched: {}, originals: {} }; // axın modalı
    var K = { card: null, kind: "", lines: [] }; // növ modalı

    function dist() { return window.EMSWorkloadDist || null; }
    function cards() { return window.EMSWorkloadCards || null; }
    function q(selector) { var D = dist(); return D ? D.q(selector) : null; }
    function esc(value) { return cards() ? cards().esc(value) : String(value == null ? "" : value); }
    function fmt(template, params) { return cards() ? cards().fmt(template, params) : template; }
    function hours(value) { return cards() ? cards().hours(value) : value + " s"; }

    function cardById(id) {
        var D = dist();
        var list = D && D.state.cards ? D.state.cards : [];
        for (var i = 0; i < list.length; i += 1) if (list[i].id === id) return list[i];
        return null;
    }

    function modal(selector) { var D = dist(); return D ? D.modal(selector) : null; }
    function showError(selector, message) { var D = dist(); if (D) D.showError(q(selector), message); }

    /** Kafedranın müəllim hovuzu (kənar daxil) — bölgü modalı ilə eyni endpoint; kafedra/il üzrə bir dəfə. */
    function loadPool() {
        var D = dist();
        var host = D ? D.root() : null;
        if (!host) return Promise.resolve([]);
        var params = D.filters();
        var key = params.chair + "|" + params.year;
        if (pool.key === key && pool.promise) return pool.promise;
        pool.key = key;
        pool.promise = window.EMSCore.fetchJSON(
            host.dataset.teachersUrl + "?chair=" + encodeURIComponent(params.chair) + "&year=" +
                encodeURIComponent(params.year) + "&outside=1"
        )
            .then(function (payload) { pool.items = (payload && payload.results) || []; return pool.items; })
            .catch(function () { pool.items = []; return pool.items; });
        return pool.promise;
    }

    function teacherOptions(selected, extra) {
        var html = '<option value=""' + (!selected ? " selected" : "") + ">" + esc(gettext("Vakant (müəllim təyin edilməyib)")) + "</option>";
        var seen = {};
        pool.items.forEach(function (item) {
            seen[String(item.id)] = true;
            var mark = item.is_outside ? " — " + fmt(gettext("kənar, ştat: %(chair)s"), { chair: item.home_chair || "—" }) : "";
            var suffix = item.current_hours != null ? " · " + item.current_hours + "s" : "";
            html += '<option value="' + esc(item.id) + '"' + (String(item.id) === String(selected) ? " selected" : "") + ">" +
                esc(item.full_name) + esc(suffix + mark) + "</option>";
        });
        // Hovuzda olmayan (deaktiv / başqa kafedra) mövcud müəllim itməsin.
        (extra || []).forEach(function (item) {
            if (!item.id || seen[String(item.id)]) return;
            seen[String(item.id)] = true;
            html += '<option value="' + esc(item.id) + '"' + (String(item.id) === String(selected) ? " selected" : "") + ">" +
                esc(item.name) + "</option>";
        });
        return html;
    }

    function select(attrs, options, search) {
        return (
            '<div class="bootstrap-single-select"><select class="form-select bootstrap-single-select__native js-bootstrap-single-select" data-bootstrap-select' +
            (search ? ' data-live-search="true" data-live-search-placeholder="' + esc(gettext("Müəllim axtar…")) + '"' : "") +
            " " + attrs + ">" + options + "</select></div>"
        );
    }

    // ══ Axınlar ═══════════════════════════════════════════════════════════
    function openStreams(cardId) {
        var card = cardById(cardId);
        if (!card) return;
        var index = {};
        var originals = {};
        (card.lecture.streams || []).forEach(function (stream, i) {
            stream.row_ids.forEach(function (id) { index[id] = i; });
            originals[i] = { rows: stream.row_ids.slice().sort().join(","), lead: stream.lead_row_id, entries: stream.entries };
        });
        var next = (card.lecture.streams || []).length;
        var units = [];
        (card.rows || []).forEach(function (row) {
            var h = row.hours || {};
            if (row.row_kind !== "teaching" || !((h.lecture_plan || 0) > 0 || (h.lecture_total || 0) > 0)) return;
            if (index[row.id] == null) index[row.id] = next++;
            units.push({
                row_id: row.id,
                label: (row.groups || []).map(function (g) { return g.name; }).join(" · ") || row.groups_text || "—",
                multi: (row.groups || []).length > 1,
                plan: h.lecture_plan || h.lecture_total || 0,
                stream: index[row.id],
            });
        });
        S = { card: card, units: units, lecturers: {}, touched: {}, originals: originals };
        Object.keys(originals).forEach(function (i) {
            var entries = originals[i].entries || [];
            if (entries.length === 1 && !entries[0].is_vacant) S.lecturers[i] = String(entries[0].teacher_id);
        });
        var title = q("[data-wl-streams-subject]");
        if (title) title.textContent = card.subject + " · " + card.season_label;
        showError("[data-wl-streams-error]", "");
        renderUnits();
        renderPreview();
        loadPool().then(renderPreview);
        var instance = modal("[data-wl-streams-modal]");
        if (instance) instance.show();
    }

    function renderUnits() {
        var host = q("[data-wl-streams-units]");
        if (!host) return;
        var count = S.units.length;
        host.innerHTML = S.units
            .map(function (unit) {
                var options = "";
                for (var i = 0; i < count; i += 1) {
                    options += '<option value="' + i + '"' + (unit.stream === i ? " selected" : "") + ">" +
                        esc(fmt(gettext("Axın %(n)s"), { n: i + 1 })) + "</option>";
                }
                return (
                    '<div class="wl-su" data-row-id="' + esc(unit.row_id) + '">' +
                    '<span class="wl-su__groups">' + esc(unit.label) +
                    (unit.multi ? ' <span class="wl-badge" title="' + esc(gettext("Bir sətrin qrupları birlikdə hərəkət edir — ayırmaq üçün sətri «Redaktə» ilə bölün.")) + '">' +
                        esc(gettext("bir sətir")) + "</span>" : "") +
                    "</span>" +
                    '<span class="wl-su__plan">' + esc(hours(unit.plan)) + "</span>" +
                    select('data-wl-stream-select data-row-id="' + esc(unit.row_id) + '"', options, false) +
                    "</div>"
                );
            })
            .join("");
        if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.init(host);
    }

    function collectStreams() {
        var groups = {};
        S.units.forEach(function (unit) {
            (groups[unit.stream] = groups[unit.stream] || []).push(unit);
        });
        return Object.keys(groups)
            .map(Number)
            .sort(function (a, b) { return a - b; })
            .map(function (i) { return { index: i, units: groups[i] }; });
    }

    function renderPreview() {
        var host = q("[data-wl-streams-preview]");
        if (!host) return;
        var streams = collectStreams();
        host.innerHTML = streams
            .map(function (stream, n) {
                var current = S.lecturers[stream.index] || "";
                var extra = ((S.originals[stream.index] || {}).entries || []).map(function (e) { return { id: e.teacher_id, name: e.teacher_name }; });
                // Nəticədə axınlar ardıcıl nömrələnir (seçicidəki «Axın N» boşluq buraxa bilər — birləşəndə).
                return (
                    '<div class="wl-sp" data-stream="' + stream.index + '">' +
                    '<div class="wl-sp__head"><span class="wl-sp__title">' + esc(fmt(gettext("Axın %(n)s"), { n: n + 1 })) + "</span>" +
                    '<span class="wl-sp__groups">' + stream.units.map(function (u) { return esc(u.label); }).join(" · ") + "</span>" +
                    '<span class="wl-sp__hours">' + esc(fmt(gettext("mühazirə %(hours)s · yükə bir dəfə"), { hours: hours(stream.units[0].plan) })) + "</span></div>" +
                    '<label class="wl-sp__teacher"><span>' + esc(gettext("Mühazirəçi")) + "</span>" +
                    select('data-wl-stream-teacher data-stream="' + stream.index + '"', teacherOptions(current, extra), true) +
                    "</label>" +
                    "</div>"
                );
            })
            .join("");
        if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.init(host);
    }

    function saveStreams() {
        var D = dist();
        var host = D ? D.root() : null;
        if (!host || !D.state.task || !S.card) return;
        var streams = collectStreams().map(function (stream) {
            var payload = { row_ids: stream.units.map(function (u) { return u.row_id; }) };
            var original = S.originals[stream.index];
            var changed = !original || original.rows !== payload.row_ids.slice().sort().join(",");
            if (S.touched[stream.index]) payload.teacher_id = S.lecturers[stream.index] || VACANT;
            else if (changed && S.lecturers[stream.index]) payload.teacher_id = S.lecturers[stream.index];
            return payload;
        });
        var done = function () {
            var instance = modal("[data-wl-streams-modal]");
            if (instance) instance.hide();
            D.loadRows();
        };
        window.EMSWorkloadAmend.write({
            url: host.dataset.streamsUrl,
            data: { task_id: D.state.task.id, streams: streams },
            modal: "[data-wl-streams-modal]",
            error: "[data-wl-streams-error]",
            done: done,
        });
    }

    // ══ Seminar / laboratoriya cədvəli ════════════════════════════════════
    function openKind(cardId, kind) {
        var card = cardById(cardId);
        if (!card || !card[kind]) return;
        K = {
            card: card,
            kind: kind,
            lines: (card[kind].lines || []).map(function (line) {
                return {
                    line: line,
                    items: (line.entries || []).map(function (entry) {
                        return {
                            id: entry.id,
                            teacher_id: entry.is_vacant ? "" : String(entry.teacher_id || ""),
                            teacher_name: entry.teacher_name,
                            hours: entry.hours,
                            sub_number: entry.sub_number ? String(entry.sub_number) : "",
                            hourly: !!entry.is_hourly_paid,
                            removed: false,
                            original: [entry.is_vacant ? "" : String(entry.teacher_id || ""), entry.hours, entry.sub_number ? String(entry.sub_number) : ""].join("|"),
                        };
                    }),
                };
            }),
        };
        var title = q("[data-wl-kind-title]");
        if (title) {
            title.textContent = fmt(gettext("%(kind)s bölgüsü — %(subject)s"), { kind: card[kind].label || kind, subject: card.subject });
        }
        showError("[data-wl-kind-error]", "");
        renderKind();
        loadPool().then(renderKind);
        var instance = modal("[data-wl-kind-modal]");
        if (instance) instance.show();
    }

    function rowRemaining(lineIndex) {
        var row = K.lines[lineIndex].line.row_id;
        var used = 0;
        K.lines.forEach(function (entry) {
            if (entry.line.row_id !== row) return;
            entry.items.forEach(function (item) { if (!item.removed) used += Number(item.hours) || 0; });
        });
        return K.lines[lineIndex].line.total - used;
    }

    function sectionOptions(line, selected) {
        var html = '<option value=""' + (!selected ? " selected" : "") + ">" + esc(gettext("Bütün qrup")) + "</option>";
        (line.sections || []).forEach(function (item) {
            html += '<option value="' + item.number + '"' + (String(item.number) === String(selected) ? " selected" : "") + ">" + esc(item.label) + "</option>";
        });
        return html;
    }

    function renderKind() {
        var host = q("[data-wl-kind-lines]");
        if (!host) return;
        var html = "";
        K.lines.forEach(function (entry, li) {
            var line = entry.line;
            var remaining = rowRemaining(li);
            var badges = line.joint ? '<span class="wl-badge wl-badge--info">' + esc(gettext("Bütün qruplar birlikdə")) + "</span>" : "";
            if (line.joint_elsewhere) badges += '<span class="wl-badge wl-badge--info">' + esc(gettext("Birgə — saat başqa sətirdədir")) + "</span>";
            html +=
                '<tr class="wl-kt__group"><th scope="rowgroup" colspan="5">' +
                '<span class="wl-kt__name">' + esc(line.label) + "</span> " + badges +
                '<span class="wl-kt__plan">' + esc(fmt(gettext("qrup planı %(hours)s"), { hours: hours(line.plan) })) + "</span>" +
                '<span class="wl-kt__remaining' + (remaining < 0 ? " is-over" : remaining > 0 ? " is-open" : "") + '">' +
                esc(fmt(gettext("sətir qalığı %(hours)s"), { hours: hours(remaining) })) + "</span>" +
                "</th></tr>";
            entry.items.forEach(function (item, ii) {
                if (item.removed) return;
                var extra = item.teacher_id ? [{ id: item.teacher_id, name: item.teacher_name }] : [];
                html +=
                    '<tr class="wl-kt__item" data-line="' + li + '" data-item="' + ii + '">' +
                    "<td>" + select('data-wl-kind-field="teacher_id" data-line="' + li + '" data-item="' + ii + '"', teacherOptions(item.teacher_id, extra), true) + "</td>" +
                    "<td>" + (line.sections && line.sections.length
                        ? select('data-wl-kind-field="sub_number" data-line="' + li + '" data-item="' + ii + '"', sectionOptions(line, item.sub_number), false)
                        : '<span class="wl-kt__muted">—</span>') + "</td>" +
                    '<td><input type="number" class="wl-kt__hours" min="1" value="' + esc(item.hours) + '" data-wl-kind-field="hours" data-line="' + li + '" data-item="' + ii + '" aria-label="' + esc(gettext("Saat")) + '"></td>' +
                    '<td><label class="wl-kt__hourly"><input type="checkbox" data-wl-kind-field="hourly" data-line="' + li + '" data-item="' + ii + '"' + (item.hourly ? " checked" : "") + "> " + esc(gettext("saathesabı")) + "</label></td>" +
                    '<td><button type="button" class="wl-chip__btn wl-chip__btn--remove" data-wl-kind-remove data-line="' + li + '" data-item="' + ii + '" aria-label="' + esc(gettext("Sətri sil")) + '">&times;</button></td>' +
                    "</tr>";
            });
            if (!line.joint_elsewhere) {
                html +=
                    '<tr class="wl-kt__add"><td colspan="5"><button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-kind-add data-line="' + li + '">' +
                    '<i class="fas fa-plus" aria-hidden="true"></i> ' + esc(gettext("Müəllim əlavə et")) + "</button></td></tr>";
            }
        });
        host.innerHTML = html;
        if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.init(host);
    }

    /** Əməliyyatlar SIRA ilə: əvvəl silmələr, sonra mövcudların dəyişməsi (azaltma), sonra yeni xətlər — əks halda
     *  əlavə saat sətrin cəmini müvəqqəti aşır və server «qalıq» xətası verir. */
    function kindOps() {
        var removes = [], edits = [], adds = [];
        var over = [];
        K.lines.forEach(function (entry, li) {
            if (rowRemaining(li) < 0) over.push(entry.line.label);
            entry.items.forEach(function (item) {
                if (item.removed) {
                    if (item.id) removes.push({ kind: "unassign", data: { assignment_id: item.id } });
                    return;
                }
                var signature = [item.teacher_id, Number(item.hours), item.sub_number].join("|");
                if (item.id && signature === item.original && !item.hourlyChanged) return;
                (item.id ? edits : adds).push({
                    kind: "assign",
                    data: {
                        row_id: entry.line.row_id,
                        assignment_id: item.id || "",
                        activity: K.kind,
                        teacher_id: item.teacher_id,
                        hours: item.hours,
                        group_id: entry.line.group_id || "",
                        sub_number: item.sub_number || "",
                        is_hourly_paid: item.hourly ? "1" : "",
                    },
                });
            });
        });
        return { ops: removes.concat(edits, adds), over: over };
    }

    function saveKind() {
        var D = dist();
        var host = D ? D.root() : null;
        if (!host || !K.card) return;
        var invalid = K.lines.some(function (entry) {
            return entry.items.some(function (item) { return !item.removed && !(Number(item.hours) > 0); });
        });
        if (invalid) {
            showError("[data-wl-kind-error]", gettext("Saat sıfırdan böyük olmalıdır."));
            return;
        }
        var plan = kindOps();
        if (plan.over.length) {
            showError("[data-wl-kind-error]", fmt(gettext("Sətrin cəmindən çox saat bölünüb: %(groups)s"), { groups: plan.over.join(", ") }));
            return;
        }
        if (!plan.ops.length) {
            var instance = modal("[data-wl-kind-modal]");
            if (instance) instance.hide();
            return;
        }
        var amend = {};
        var button = q("[data-wl-kind-save]");
        if (button) button.disabled = true;
        (function runNext(i) {
            if (i >= plan.ops.length) {
                if (button) button.disabled = false;
                var done = modal("[data-wl-kind-modal]");
                if (done) done.hide();
                D.loadRows();
                return;
            }
            var op = plan.ops[i];
            var data = Object.assign({}, op.data, amend);
            window.EMSWorkloadAmend.write({
                url: op.kind === "assign" ? host.dataset.assignUrl : host.dataset.unassignUrl,
                data: data,
                modal: "[data-wl-kind-modal]",
                error: "[data-wl-kind-error]",
                done: function (result) {
                    // Düzəliş səbəbi bir dəfə soruşulur — qalan sorğulara köçürülür.
                    if (data.amend_reason) amend = { amend_reason: data.amend_reason, amend_note: data.amend_note };
                    if (result && result.warning && window.EMSToast) window.EMSToast.show(result.warning, "warning");
                    runNext(i + 1);
                },
            }).then(function () {
                if (button) button.disabled = false;
            });
        })(0);
    }

    function bind() {
        var EMSDelegate = window.EMSDelegate;
        if (!EMSDelegate) return;
        EMSDelegate.on("click", "[data-wl-streams-open]", function (event, btn) { openStreams(btn.dataset.cardId); });
        EMSDelegate.on("click", "[data-wl-kind-open]", function (event, btn) { openKind(btn.dataset.cardId, btn.dataset.kind); });
        EMSDelegate.on("click", "[data-wl-card-rows-toggle]", function (event, btn) {
            var details = q('[data-wl-card-rows][data-card-id="' + (btn.dataset.cardId || "").replace(/[^0-9a-fA-F-]/g, "") + '"]');
            if (details) {
                details.open = !details.open;
                if (details.open && details.scrollIntoView) details.scrollIntoView({ block: "nearest" });
            }
        });
        EMSDelegate.on("change", "[data-wl-stream-select]", function (event, field) {
            S.units.forEach(function (unit) { if (unit.row_id === field.dataset.rowId) unit.stream = Number(field.value); });
            renderPreview();
        });
        EMSDelegate.on("change", "[data-wl-stream-teacher]", function (event, field) {
            S.lecturers[Number(field.dataset.stream)] = field.value;
            S.touched[Number(field.dataset.stream)] = true;
        });
        EMSDelegate.on("click", "[data-wl-streams-save]", saveStreams);
        EMSDelegate.on("change", "[data-wl-kind-field]", function (event, field) {
            var item = (K.lines[Number(field.dataset.line)] || { items: [] }).items[Number(field.dataset.item)];
            if (!item) return;
            var name = field.dataset.wlKindField; // data-wl-kind-field="teacher_id|sub_number|hours|hourly"
            if (name === "hourly") {
                item.hourly = field.checked;
                item.hourlyChanged = true;
            } else {
                item[name] = field.value;
            }
            if (name === "hours") renderKind();
        });
        EMSDelegate.on("click", "[data-wl-kind-add]", function (event, btn) {
            var entry = K.lines[Number(btn.dataset.line)];
            if (!entry) return;
            var remaining = rowRemaining(Number(btn.dataset.line));
            entry.items.push({
                id: "",
                teacher_id: "",
                teacher_name: "",
                hours: Math.max(1, Math.min(entry.line.plan || remaining || 1, remaining > 0 ? remaining : entry.line.plan || 1)),
                sub_number: "",
                hourly: false,
                removed: false,
                original: "",
            });
            renderKind();
        });
        EMSDelegate.on("click", "[data-wl-kind-remove]", function (event, btn) {
            var item = (K.lines[Number(btn.dataset.line)] || { items: [] }).items[Number(btn.dataset.item)];
            if (!item) return;
            item.removed = true;
            renderKind();
        });
        EMSDelegate.on("click", "[data-wl-kind-save]", saveKind);
    }

    window.EMSWorkloadPickers = { openStreams: openStreams, openKind: openKind, cardById: cardById };

    if (window.EMSReady) {
        window.EMSReady.once("workload-distribution-pickers-bind", bind);
        window.EMSReady(function () { pool = { key: "", items: [], promise: null }; });
    }
})(window, document);
