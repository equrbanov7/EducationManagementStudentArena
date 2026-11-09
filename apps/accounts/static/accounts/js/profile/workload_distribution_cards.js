/*
 * «Yük bölgüsü» — FƏNN KARTI render modulu (`EMSWorkloadRender.cards`, sahib 2026-11-09).
 *
 * Sahib: «Xətti cəbr və riyazi analiz 4 ayrı kartdır … eyni fənn, eyni kredit, eyni semestr — BİR yük olsun, qruplar
 * içində bölünsün». Server (`apps/workload/services/subject_cards.py`) eyni fənn + semestr + kredit sətirlərini bir
 * kartda qaytarır; burada yalnız data → DOM:
 *
 *   • mühazirə AXINLARI (patok): «536 MU · MU1 · MU2 → Mehdi Balayev · 45 s» — bir axının mühazirəsi yükə bir dəfə
 *     düşür; «Axınları dəyiş» (`workload_distribution_pickers.js`) qaydanı AÇIQ seçdirir;
 *   • seminar / laboratoriya XƏTLƏRİ qrup başına — «Bölüşdür» cədvəl modalını açır (qrup → müəllim · saat · Lab-1);
 *   • digər fəaliyyətlər (məsləhət, imtahan …) köhnə zolaq kimi; sətirlərin özü (Redaktə / Sil) açılan hissədə.
 *
 * Saf render: fetch/listener YOX; `EMSWorkloadRender.rowHtml` (köhnə sətir kartı) açılan hissədə təkrar işlənir.
 */
(function (window, document) {
    "use strict";

    var Render = (window.EMSWorkloadRender = window.EMSWorkloadRender || {});
    var Cards = (window.EMSWorkloadCards = window.EMSWorkloadCards || {});
    var gettext = window.gettext || function (value) { return value; };

    function fmt(template, params) {
        if (typeof window.interpolate === "function") return window.interpolate(template, params, true);
        return template.replace(/%\((\w+)\)s/g, function (_, key) {
            return params[key] == null ? "" : String(params[key]);
        });
    }

    function esc(value) {
        var node = document.createElement("span");
        node.textContent = value == null ? "" : String(value);
        return node.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function hours(value) {
        return fmt(gettext("%(hours)s s"), { hours: value == null ? 0 : value });
    }

    function isMatch(entry, teacher) {
        if (!teacher) return false;
        return teacher === "vacant" ? !!entry.is_vacant : String(entry.teacher_id) === String(teacher);
    }

    function sectionLabel(entry, sections) {
        if (!entry.sub_number) return "";
        var found = (sections || []).filter(function (item) { return item.number === entry.sub_number; })[0];
        return found ? found.label : fmt(gettext("№%(n)s"), { n: entry.sub_number });
    }

    /** Bölgü çipi: müəllim · saat (· Lab-1) + redaktə / sil (köhnə `data-wl-assign-*` dinləyiciləri). */
    function chip(entry, rowId, teacher, sections) {
        var section = sectionLabel(entry, sections);
        return (
            '<li class="wl-chip' + (entry.is_vacant ? " is-vacant" : "") + (isMatch(entry, teacher) ? " is-match" : "") +
            (entry.unclear ? " is-unclear" : "") + '">' +
            '<span class="wl-chip__name">' + esc(entry.teacher_name) + "</span>" +
            '<span class="wl-chip__hours">' + esc(hours(entry.hours)) + "</span>" +
            (section ? '<span class="wl-chip__section">' + esc(section) + "</span>" : "") +
            (entry.unclear ? '<span class="wl-chip__note" title="' + esc(gettext("Qrup qeydi tanınmadı")) + '">' +
                esc(entry.groups_note || "?") + "</span>" : "") +
            '<button type="button" class="wl-chip__btn" aria-label="' + esc(gettext("Bölgünü redaktə et")) + '"' +
            ' data-wl-assign-edit data-row-id="' + esc(rowId) + '" data-assignment-id="' + esc(entry.id) + '">' +
            '<i class="fas fa-pen" aria-hidden="true"></i></button>' +
            '<button type="button" class="wl-chip__btn wl-chip__btn--remove" aria-label="' + esc(gettext("Bölgünü sil")) +
            '" data-wl-assign-remove data-assignment-id="' + esc(entry.id) + '">&times;</button>' +
            "</li>"
        );
    }

    function groupChips(groups) {
        if (!groups || !groups.length) return "";
        return (
            '<ul class="wl-card__groups" aria-label="' + esc(gettext("Qruplar")) + '">' +
            groups.map(function (group) { return '<li class="wl-card__group">' + esc(group.name) + "</li>"; }).join("") +
            "</ul>"
        );
    }

    // ── Mühazirə axınları ───────────────────────────────────────────────────
    function streamTeachers(stream, teacher) {
        if (!stream.entries.length) {
            return '<span class="wl-stream__teacher is-vacant">' + esc(gettext("Mühazirəçi seçilməyib")) + "</span>";
        }
        return stream.entries
            .map(function (entry) {
                return (
                    '<span class="wl-stream__teacher' + (entry.is_vacant ? " is-vacant" : "") +
                    (isMatch(entry, teacher) ? " is-match" : "") + '">' + esc(entry.teacher_name) +
                    (stream.entries.length > 1 ? " · " + esc(hours(entry.hours)) : "") + "</span>"
                );
            })
            .join("");
    }

    function streamWarning(stream) {
        if (!stream.orphan) {
            return stream.union_count > 1
                ? '<span class="wl-badge wl-badge--info">' +
                  esc(fmt(gettext("%(n)s axın (qruplar ayrılmayıb)"), { n: stream.union_count })) + "</span>"
                : "";
        }
        var text = stream.warning === "foreign_lead"
            ? gettext("Aparıcı başqa kartdadır")
            : gettext("Aparıcı seçilməyib — mühazirə yükə düşmür");
        if (stream.lead_teacher_name) text += " · " + stream.lead_teacher_name;
        return '<span class="wl-badge wl-badge--warn">' + esc(text) + "</span>";
    }

    function streamsBlock(card, labels, teacher, editable) {
        var lecture = card.lecture || {};
        var streams = lecture.streams || [];
        if (!streams.length) return "";
        var summary = fmt(gettext("%(n)s axın · yükə %(hours)s"), { n: streams.length, hours: hours(lecture.load_hours) });
        return (
            '<section class="wl-kind wl-kind--lecture">' +
            '<div class="wl-kind__head">' +
            '<span class="wl-kind__label">' + esc(labels.lecture || gettext("Mühazirə")) + "</span>" +
            '<span class="wl-kind__sum">' + esc(summary) + "</span>" +
            (editable
                ? '<button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-streams-open data-card-id="' +
                  esc(card.id) + '"><i class="fas fa-people-group" aria-hidden="true"></i> ' +
                  esc(gettext("Axınları dəyiş")) + "</button>"
                : "") +
            "</div>" +
            '<ul class="wl-streams">' +
            streams
                .map(function (stream) {
                    var cls = stream.orphan ? " is-orphan" : stream.is_complete ? " is-complete" : " is-open";
                    return (
                        '<li class="wl-stream' + cls + '" data-lead-row-id="' + esc(stream.lead_row_id) + '">' +
                        '<span class="wl-stream__groups">' +
                        stream.groups.map(function (g) { return esc(g.name); }).join('<span class="wl-stream__dot">·</span>') +
                        "</span>" +
                        '<span class="wl-stream__arrow" aria-hidden="true">→</span>' +
                        '<span class="wl-stream__who">' + streamTeachers(stream, teacher) + "</span>" +
                        '<span class="wl-stream__hours">' + esc(hours(stream.hours)) + "</span>" +
                        (stream.remaining > 0 && !stream.orphan && editable
                            ? '<button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-assign-open data-row-id="' +
                              esc(stream.lead_row_id) + '" data-activity="lecture">' +
                              esc(fmt(gettext("Qalıq %(hours)s"), { hours: hours(stream.remaining) })) + "</button>"
                            : "") +
                        streamWarning(stream) +
                        "</li>"
                    );
                })
                .join("") +
            "</ul>" +
            (lecture.without_groups && lecture.without_groups.length
                ? '<p class="wl-kind__note">' + esc(fmt(gettext("Mühazirəsiz qruplar: %(groups)s"), {
                      groups: lecture.without_groups.map(function (g) { return g.name; }).join(", "),
                  })) + "</p>"
                : "") +
            '<p class="wl-kind__rule"><i class="fas fa-circle-info" aria-hidden="true"></i> ' +
            esc(gettext("Patok: bir axının mühazirəsi müəllimin yükünə bir dəfə düşür və hər qrupun jurnalında görünür.")) +
            "</p>" +
            "</section>"
        );
    }

    // ── Seminar / laboratoriya xətləri ─────────────────────────────────────
    function lineHtml(line, teacher, seenRows) {
        var badges = "";
        if (line.joint) badges += '<span class="wl-badge wl-badge--info">' + esc(gettext("Bütün qruplar birlikdə")) + "</span>";
        if (line.shared) badges += '<span class="wl-badge">' + esc(gettext("Qrupsuz bölgü")) + "</span>";
        if (line.joint_elsewhere) {
            badges += '<span class="wl-badge wl-badge--info">' + esc(gettext("Birgə — saat başqa sətirdədir")) + "</span>";
        }
        var first = !seenRows[line.row_id];
        seenRows[line.row_id] = true;
        if (first && line.remaining > 0 && !line.joint_elsewhere) {
            badges += '<span class="wl-badge wl-badge--warn">' + esc(fmt(gettext("Qalıq %(hours)s"), { hours: hours(line.remaining) })) + "</span>";
        }
        var entries = line.entries.length
            ? '<ul class="wl-line__entries">' +
              line.entries.map(function (entry) { return chip(entry, line.row_id, teacher, line.sections); }).join("") +
              "</ul>"
            : '<span class="wl-line__vacant">' + esc(gettext("Təyin olunmayıb")) + "</span>";
        return (
            '<li class="wl-line' + (line.entries.length && line.remaining <= 0 ? " is-complete" : "") + '" data-row-id="' +
            esc(line.row_id) + '">' +
            '<span class="wl-line__group">' + esc(line.label) + "</span>" +
            '<span class="wl-line__plan">' + esc(hours(line.plan)) + "</span>" +
            entries +
            (badges ? '<span class="wl-line__badges">' + badges + "</span>" : "") +
            "</li>"
        );
    }

    function kindBlock(card, kind, labels, teacher, editable) {
        var block = card[kind] || {};
        var lines = block.lines || [];
        if (!lines.length) return "";
        var seenRows = {};
        var groupsCount = lines.filter(function (line) { return line.group_id; }).length;
        var summary = groupsCount
            ? fmt(gettext("%(n)s qrup · %(hours)s"), { n: groupsCount, hours: hours(block.total) })
            : hours(block.total);
        return (
            '<section class="wl-kind wl-kind--' + esc(kind) + '">' +
            '<div class="wl-kind__head">' +
            '<span class="wl-kind__label">' + esc(labels[kind] || block.label || kind) + "</span>" +
            '<span class="wl-kind__sum">' + esc(summary) + "</span>" +
            (editable
                ? '<button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-kind-open data-card-id="' +
                  esc(card.id) + '" data-kind="' + esc(kind) + '"><i class="fas fa-table-cells-large" aria-hidden="true"></i> ' +
                  esc(gettext("Bölüşdür")) + "</button>"
                : "") +
            "</div>" +
            '<ul class="wl-lines">' + lines.map(function (line) { return lineHtml(line, teacher, seenRows); }).join("") + "</ul>" +
            "</section>"
        );
    }

    // ── Digər fəaliyyətlər (məsləhət, imtahan …) ───────────────────────────
    function otherBlock(card, teacher, editable) {
        var items = card.other || [];
        if (!items.length) return "";
        return (
            '<section class="wl-kind wl-kind--other">' +
            items
                .map(function (item) {
                    return (
                        '<div class="wl-act' + (item.is_complete ? " is-complete" : "") + '">' +
                        '<span class="wl-act__label">' + esc(item.label) + "</span>" +
                        '<span class="wl-act__bar"><span class="wl-act__fill" style="--wl-fill:' +
                        (item.total ? Math.min(100, Math.round((item.assigned * 100) / item.total)) : 0) + '%"></span></span>' +
                        '<span class="wl-act__numbers">' + item.assigned + " / " + item.total + "</span>" +
                        (editable
                            ? '<button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-assign-open data-row-id="' +
                              esc(item.row_id) + '" data-activity="' + esc(item.activity) + '">' + esc(gettext("Bölüşdür")) + "</button>"
                            : "<span></span>") +
                        (item.entries.length
                            ? '<ul class="wl-line__entries wl-act__chips">' +
                              item.entries.map(function (entry) { return chip(entry, item.row_id, teacher, []); }).join("") + "</ul>"
                            : "") +
                        "</div>"
                    );
                })
                .join("") +
            "</section>"
        );
    }

    function cardHtml(card, labels, teacher) {
        if (card.intensive && typeof Render.rowHtml === "function") return Render.rowHtml(card.rows[0], labels, teacher);
        var editable = card.row_kind === "teaching";
        var meta = [card.season_label];
        if (card.credits) meta.push(fmt(gettext("%(credits)s kredit"), { credits: card.credits }));
        meta.push(fmt(gettext("%(n)s qrup"), { n: card.groups.length }));
        meta.push(fmt(gettext("%(hours)s saat"), { hours: card.total_hours }));
        if (card.student_count) meta.push(fmt(gettext("%(n)s tələbə"), { n: card.student_count }));
        (card.specialties || []).forEach(function (name) { meta.push(name); });
        var rows = card.rows || [];
        var rowsHtml = typeof Render.rowHtml === "function"
            ? rows.map(function (row) { return Render.rowHtml(row, labels, teacher); }).join("")
            : "";
        return (
            '<article class="wl-card' + (card.teaching_complete ? " is-complete" : "") + '" role="listitem" data-wl-card data-card-id="' +
            esc(card.id) + '" data-card-key="' + esc(card.key) + '">' +
            '<header class="wl-card__head"><div>' +
            '<h3 class="wl-card__subject">' + esc(card.subject) + "</h3>" +
            '<div class="wl-card__meta">' +
            (card.is_amend_target ? '<span class="wl-row__amend">' + esc(gettext("Düzəliş açıqdır")) + "</span>" : "") +
            meta.map(function (text) { return "<span>" + esc(text) + "</span>"; }).join("") +
            "</div></div>" +
            '<div class="wl-card__actions">' +
            '<button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-card-rows-toggle data-card-id="' + esc(card.id) + '">' +
            '<i class="fas fa-table-list" aria-hidden="true"></i> ' + esc(fmt(gettext("Sətirlər (%(n)s)"), { n: rows.length })) +
            "</button>" +
            "</div></header>" +
            groupChips(card.groups) +
            ((card.warnings || []).indexOf("patok_unlinked") >= 0
                ? '<p class="wl-card__warn"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i> ' +
                  esc(gettext("Bu fəndə aparıcısı seçilməmiş patok sətri var — «Axınları dəyiş» ilə qrupları axına bağlayın.")) + "</p>"
                : "") +
            streamsBlock(card, labels, teacher, editable) +
            kindBlock(card, "seminar", labels, teacher, editable) +
            kindBlock(card, "lab", labels, teacher, editable) +
            otherBlock(card, teacher, editable) +
            '<details class="wl-card__rows" data-wl-card-rows data-card-id="' + esc(card.id) + '">' +
            "<summary>" + esc(fmt(gettext("Tapşırıq sətirləri (%(n)s) — redaktə, silmə, saatlar"), { n: rows.length })) + "</summary>" +
            '<div class="wl-card__rows-body">' + rowsHtml + "</div>" +
            "</details>" +
            "</article>"
        );
    }

    /** Kartları siyahı sahəsinə yazır (`opts.append` — tənbəl yükləmə; `opts.teacher` — seçilmiş müəllim vurğusu). */
    Render.cards = function renderCards(host, cards, labels, opts) {
        if (!host) return;
        opts = opts || {};
        labels = labels || {};
        var html = (cards || []).map(function (card) { return cardHtml(card, labels, opts.teacher || ""); }).join("");
        if (opts.append) host.insertAdjacentHTML("beforeend", html);
        else host.innerHTML = html;
    };

    Cards.html = cardHtml;
    Cards.hours = hours;
    Cards.esc = esc;
    Cards.fmt = fmt;
})(window, document);
