/*
 * «Yük bölgüsü» — FƏNN KARTI render modulu (`EMSWorkloadRender.cards`, sahib 2026-11-09; aydınlıq 2026-11-19).
 *
 * Server (`apps/workload/services/subject_cards.py`) eyni fənn + semestr + kredit sətirlərini bir kartda qaytarır;
 * burada yalnız data → DOM. Sahib 2026-11-19: «patok dərsi olanda, seminar bölünəndə qarışıqdır, axın yazısı aydın
 * deyil» — ona görə kart ADDIM-ADDIM oxunur:
 *
 *   1 · MÜHAZİRƏ — hər axın nömrəli sətirdir: «Axın 1 · 534 Bİ az · 534 Bİ ing · 2 qrup birlikdə → müəllim · 45 s»;
 *       axının nə olduğu (patok: saat yükə 1 dəfə, jurnal hər qrupda) kartın özündə yazılıb;
 *   2 · SEMİNAR / 3 · LABORATORİYA — başlıqlı cədvəl (qrup · plan · müəllim və saat); bütün sətrə yazılmış («qruplara
 *       ayrılmamış») saat TƏK xətt kimi göstərilir, qrup xətləri əbəs yerə «təyin olunmayıb» demir;
 *   • kartın başında vəziyyət: «Tam bölünüb» / «Bölünməyib: N s»; qardaş qruplardan fərqlənən saat (45 əvəzinə 38,
 *     30 əvəzinə 37) «saatı yoxlayın» nişanı alır.
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

    /** Ən çox təkrarlanan müsbət dəyər (qardaş qrupların «normal» saatı); tək dəyər varsa 0 — müqayisə yoxdur. */
    function typical(values) {
        var counts = {};
        var best = 0;
        var distinct = 0;
        values.forEach(function (value) {
            if (!(value > 0)) return;
            if (!counts[value]) distinct += 1;
            counts[value] = (counts[value] || 0) + 1;
        });
        if (distinct < 2) return 0;
        Object.keys(counts).forEach(function (key) {
            if (!best || counts[key] > counts[best]) best = Number(key);
        });
        // Bərabərlikdə «normal» yoxdur (2 qrup 45, 2 qrup 30 — hansının səhv olduğu bilinmir).
        var ties = Object.keys(counts).filter(function (key) { return counts[key] === counts[best]; }).length;
        return ties > 1 ? 0 : best;
    }

    /**
     * Qardaş saatı TƏHSİL FORMASI üzrə: əyani 45 s ilə qiyabi 15 s eyni kartda ola bilər — bu səhv deyil.
     * `items` — `{row, value}`; qaytarır: sətir id-si → həmin formanın «normal» saatı (yoxdursa 0).
     */
    function typicalByForm(card, items) {
        var forms = {};
        (card.rows || []).forEach(function (row) { forms[row.id] = row.education_form || ""; });
        var buckets = {};
        items.forEach(function (item) {
            var form = forms[item.row] || "";
            (buckets[form] = buckets[form] || []).push(item.value);
        });
        var usual = {};
        Object.keys(buckets).forEach(function (form) { usual[form] = typical(buckets[form]); });
        return function (rowId) { return usual[forms[rowId] || ""] || 0; };
    }

    function oddBadge(value, usual) {
        if (!usual || !(value > 0) || value === usual) return "";
        return (
            '<span class="wl-badge wl-badge--warn wl-badge--odd" title="' +
            esc(gettext("Eyni fənnin digər qruplarında saat fərqlidir. Səhvdirsə «Tapşırıq sətirləri» → «Redaktə» ilə düzəldin.")) +
            '"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i> ' +
            esc(fmt(gettext("digər qruplarda %(hours)s — saatı yoxlayın"), { hours: hours(usual) })) + "</span>"
        );
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

    function pills(groups) {
        return (groups || []).map(function (group) { return '<span class="wl-pill">' + esc(group.name) + "</span>"; }).join("");
    }

    function groupChips(groups) {
        if (!groups || !groups.length) return "";
        return (
            '<ul class="wl-card__groups" aria-label="' + esc(gettext("Qruplar")) + '">' +
            groups.map(function (group) { return '<li class="wl-card__group">' + esc(group.name) + "</li>"; }).join("") +
            "</ul>"
        );
    }

    function kindHead(step, label, summary, button) {
        return (
            '<div class="wl-kind__head">' +
            '<span class="wl-kind__step" aria-hidden="true">' + step + "</span>" +
            '<span class="wl-kind__label">' + esc(label) + "</span>" +
            '<span class="wl-kind__sum">' + summary + "</span>" +
            (button || "") +
            "</div>"
        );
    }

    // ── 1 · Mühazirə axınları ───────────────────────────────────────────────
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
                ? '<span class="wl-badge wl-badge--info" title="' +
                  esc(gettext("Bu sətrin qrupları mühazirəni bir neçə axında keçir, amma sətir qruplara ayrılmayıb.")) + '">' +
                  esc(fmt(gettext("%(n)s axın bir sətirdə"), { n: stream.union_count })) + "</span>"
                : "";
        }
        var text = stream.warning === "foreign_lead"
            ? gettext("Axının mühazirəçisi başqa kartdadır")
            : gettext("Axına bağlanmayıb — mühazirə heç kimin yükünə düşmür");
        if (stream.lead_teacher_name) text += " · " + stream.lead_teacher_name;
        return '<span class="wl-badge wl-badge--warn">' + esc(text) + "</span>";
    }

    function streamMode(stream) {
        var count = (stream.groups || []).length;
        if (count > 1) {
            return (
                '<span class="wl-stream__mode is-joint" title="' +
                esc(gettext("Bu qruplar mühazirəni birlikdə dinləyir: saat müəllimin yükünə 1 dəfə yazılır, jurnal hər qrupda açılır.")) +
                '"><i class="fas fa-people-group" aria-hidden="true"></i> ' +
                esc(fmt(gettext("%(n)s qrup birlikdə"), { n: count })) + "</span>"
            );
        }
        return '<span class="wl-stream__mode">' + esc(gettext("tək qrup")) + "</span>";
    }

    function streamsBlock(card, labels, teacher, editable) {
        var lecture = card.lecture || {};
        var streams = lecture.streams || [];
        if (!streams.length) return "";
        // «Axın» sözü yalnız həqiqi patok olanda işlənir; qruplar ayrıca keçirsə sadəcə «qrup → müəllim» siyahısıdır.
        var joint = streams.some(function (s) { return (s.groups || []).length > 1 || s.union_count > 1; });
        var usual = typicalByForm(card, streams.map(function (s) { return { row: s.lead_row_id, value: s.plan }; }));
        var summary = joint
            ? fmt(gettext("%(n)s axın · müəllim yükünə cəmi %(hours)s"), { n: streams.length, hours: hours(lecture.load_hours) })
            : streams.length > 1
                ? fmt(gettext("%(n)s qrup ayrıca keçir · müəllim yükünə cəmi %(hours)s"), { n: streams.length, hours: hours(lecture.load_hours) })
                : hours(lecture.load_hours);
        var action = joint ? gettext("Axınları dəyiş") : streams.length > 1 ? gettext("Patok qur") : gettext("Mühazirəçi seç");
        var button = editable
            ? '<button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-streams-open data-card-id="' +
              esc(card.id) + '" title="' +
              esc(gettext("Hansı qrupların mühazirəni birlikdə dinlədiyini (patok) və mühazirəçini seçin.")) + '">' +
              '<i class="fas fa-people-group" aria-hidden="true"></i> ' + esc(action) + "</button>"
            : "";
        var many = joint; // nömrəli axın nişanı və «birlikdə / tək qrup» qeydi yalnız patoklu kartda
        return (
            '<section class="wl-kind wl-kind--lecture">' +
            kindHead(1, labels.lecture || gettext("Mühazirə"), esc(summary), button) +
            (many
                ? '<p class="wl-kind__rule"><i class="fas fa-circle-info" aria-hidden="true"></i> <span>' +
                  esc(gettext("Axın (patok) — mühazirəni birlikdə dinləyən qruplar. Bir axının saatı müəllimin yükünə 1 dəfə yazılır, jurnal isə hər qrupda açılır.")) +
                  "</span></p>"
                : "") +
            '<ul class="wl-streams">' +
            streams
                .map(function (stream, index) {
                    var cls = stream.orphan ? " is-orphan" : stream.is_complete ? " is-complete" : " is-open";
                    return (
                        '<li class="wl-stream' + cls + '" data-lead-row-id="' + esc(stream.lead_row_id) + '">' +
                        (many ? '<span class="wl-stream__tag">' + esc(fmt(gettext("Axın %(n)s"), { n: index + 1 })) + "</span>" : "") +
                        '<span class="wl-stream__groups">' + pills(stream.groups) + "</span>" +
                        (many ? streamMode(stream) : "") +
                        '<span class="wl-stream__arrow" aria-hidden="true">→</span>' +
                        '<span class="wl-stream__who">' + streamTeachers(stream, teacher) + "</span>" +
                        oddBadge(stream.plan, usual(stream.lead_row_id)) +
                        streamWarning(stream) +
                        (stream.remaining > 0 && !stream.orphan && editable
                            ? '<button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-assign-open data-row-id="' +
                              esc(stream.lead_row_id) + '" data-activity="lecture">' +
                              esc(fmt(gettext("Bölünməyib: %(hours)s"), { hours: hours(stream.remaining) })) + "</button>"
                            : "") +
                        '<span class="wl-stream__hours">' + esc(hours(stream.hours)) + "</span>" +
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
            "</section>"
        );
    }

    // ── 2 · Seminar / 3 · Laboratoriya xətləri ─────────────────────────────
    /**
     * Xətləri sətir üzrə yığır. Çox qruplu sətrin saatı yalnız «bütün sətrə» yazılıbsa (qrup bağı yoxdur) qrup
     * xətləri gizlənir və TƏK xətt qalır; qarışıq halda boş qrup xətti «ümumi bölgüyə daxildir» deyir.
     */
    function arrange(lines) {
        var byRow = {};
        var order = [];
        lines.forEach(function (line) {
            if (!byRow[line.row_id]) {
                byRow[line.row_id] = [];
                order.push(line.row_id);
            }
            byRow[line.row_id].push(line);
        });
        var out = [];
        order.forEach(function (rowId) {
            var set = byRow[rowId];
            var shared = set.filter(function (line) { return line.shared; })[0];
            var own = set.filter(function (line) { return !line.shared; });
            if (shared && own.length && own.every(function (line) { return !line.entries.length; })) {
                out.push({ line: shared, whole: own.length });
                return;
            }
            set.forEach(function (line) {
                out.push({ line: line, covered: !!shared && !line.shared && !line.entries.length && line.remaining <= 0 });
            });
        });
        return out;
    }

    function linePlan(item) {
        var line = item.line;
        if (item.whole) return fmt(gettext("%(n)s qrup · %(hours)s"), { n: item.whole, hours: hours(line.total) });
        if (line.shared) return "—";
        if (line.joint) return hours(line.total || line.plan);
        return hours(line.plan);
    }

    function lineHtml(item, teacher, seenRows, usual) {
        var line = item.line;
        var badges = "";
        if (line.joint) {
            badges += '<span class="wl-badge wl-badge--info" title="' +
                esc(gettext("Bu qruplar məşğələni birlikdə keçir — saat müəllimin yükünə 1 dəfə yazılır.")) + '">' +
                esc(gettext("Qruplar birlikdə keçir")) + "</span>";
        }
        if (line.shared) {
            badges += '<span class="wl-badge" title="' +
                esc(gettext("Saat bütün sətrə yazılıb. Hər qrupa ayrıca müəllim vermək üçün «Bölüşdür» düyməsinə basın.")) + '">' +
                esc(gettext("Qruplara ayrılmayıb")) + "</span>";
        }
        if (line.joint_elsewhere) {
            badges += '<span class="wl-badge wl-badge--info">' + esc(gettext("Birgə — saat başqa sətirdədir")) + "</span>";
        }
        if (!line.shared && !line.joint) badges += oddBadge(line.plan, usual(line.row_id));
        var first = !seenRows[line.row_id];
        seenRows[line.row_id] = true;
        if (first && line.remaining > 0 && !line.joint_elsewhere) {
            badges += '<span class="wl-badge wl-badge--warn">' +
                esc(fmt(gettext("Bölünməyib: %(hours)s"), { hours: hours(line.remaining) })) + "</span>";
        }
        var entries;
        if (line.entries.length) {
            entries = '<ul class="wl-line__entries">' +
                line.entries.map(function (entry) { return chip(entry, line.row_id, teacher, line.sections); }).join("") + "</ul>";
        } else if (item.covered) {
            entries = '<span class="wl-line__covered">' + esc(gettext("Ümumi bölgüyə daxildir")) + "</span>";
        } else if (line.joint_elsewhere) {
            entries = '<span class="wl-line__covered">' + esc(gettext("Birgə keçilir")) + "</span>";
        } else {
            entries = '<span class="wl-line__vacant"><i class="fas fa-user-slash" aria-hidden="true"></i> ' +
                esc(gettext("Müəllim təyin olunmayıb")) + "</span>";
        }
        var done = line.entries.length && line.remaining <= 0;
        return (
            '<li class="wl-line' + (done ? " is-complete" : "") + (item.covered ? " is-covered" : "") + '" data-row-id="' +
            esc(line.row_id) + '">' +
            '<span class="wl-line__group">' + esc(line.label) + "</span>" +
            '<span class="wl-line__plan">' + esc(linePlan(item)) + "</span>" +
            entries +
            (badges ? '<span class="wl-line__badges">' + badges + "</span>" : "") +
            "</li>"
        );
    }

    /** Növün sətirlər üzrə cəmi: bölünmüş və qalıq saat (çox qruplu sətir BİR dəfə sayılır). */
    function kindTotals(lines) {
        var seen = {};
        var totals = { assigned: 0, remaining: 0 };
        lines.forEach(function (line) {
            if (seen[line.row_id]) return;
            seen[line.row_id] = true;
            totals.assigned += Number(line.assigned) || 0;
            if (line.remaining > 0 && !line.joint_elsewhere) totals.remaining += Number(line.remaining) || 0;
        });
        return totals;
    }

    function kindBlock(card, kind, step, labels, teacher, editable) {
        var block = card[kind] || {};
        var lines = block.lines || [];
        if (!lines.length) return "";
        var seenRows = {};
        var items = arrange(lines);
        var totals = kindTotals(lines);
        var groupsCount = lines.filter(function (line) { return line.group_id; }).length;
        var usual = typicalByForm(
            card,
            lines.filter(function (line) { return line.group_id; }).map(function (line) { return { row: line.row_id, value: line.plan }; })
        );
        var summary = esc(
            (groupsCount ? fmt(gettext("%(n)s qrup"), { n: groupsCount }) + " · " : "") +
            fmt(gettext("cəmi %(total)s · bölünüb %(assigned)s"), { total: hours(block.total), assigned: hours(totals.assigned) })
        );
        // 2026-11-26: «Bölüşdür» addımlı «Bölgü sehrbazı»nı açır; köhnə cədvəl «Ətraflı cədvəl» kimi qalır.
        var button = editable
            ? '<span class="wl-kind__actions"><button type="button" class="wl-btn wl-btn--primary wl-btn--sm" data-wl-wiz-open data-card-id="' +
              esc(card.id) + '" data-kind="' + esc(kind) + '" title="' +
              esc(gettext("Addım-addım: qrupları alt qruplara bölün, tələbələri yerləşdirin, hər bölməyə müəllim verin.")) +
              '"><i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i> ' + esc(gettext("Bölüşdür")) + "</button>" +
              '<button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-kind-open data-card-id="' +
              esc(card.id) + '" data-kind="' + esc(kind) + '" title="' +
              esc(gettext("Hər qrupa müəllim və saat verin; qrupu Lab-1 / Lab-2 kimi alt qruplara da bölə bilərsiniz.")) +
              '"><i class="fas fa-table-cells-large" aria-hidden="true"></i> ' + esc(gettext("Ətraflı cədvəl")) + "</button></span>"
            : "";
        return (
            '<section class="wl-kind wl-kind--' + esc(kind) + '">' +
            kindHead(step, labels[kind] || block.label || kind, summary, button) +
            '<ul class="wl-lines">' +
            '<li class="wl-lines__head" aria-hidden="true"><span>' + esc(gettext("Qrup")) + "</span><span>" +
            esc(gettext("Plan saatı")) + "</span><span>" + esc(gettext("Müəllim və saat")) + "</span></li>" +
            items.map(function (item) { return lineHtml(item, teacher, seenRows, usual); }).join("") +
            "</ul>" +
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

    /** Kartın vəziyyət nişanı: tədris saatı (mühazirə + seminar + lab) tam bölünübmü, neçə saat qalıb. */
    function stateBadge(card) {
        if (card.row_kind !== "teaching") return "";
        var left = 0;
        ((card.lecture || {}).streams || []).forEach(function (stream) {
            if (!stream.orphan && stream.remaining > 0) left += stream.remaining;
        });
        ["seminar", "lab"].forEach(function (kind) {
            left += kindTotals((card[kind] || {}).lines || []).remaining;
        });
        if (card.teaching_complete && !left) {
            var vacant = 0; // saat bölünüb, amma «Vakant»a — müəllim hələ yoxdur
            (card.rows || []).forEach(function (row) {
                (row.assignments || []).forEach(function (item) {
                    if (item.is_vacant && /^(lecture|seminar|lab)$/.test(item.activity)) vacant += Number(item.hours) || 0;
                });
            });
            if (vacant) {
                return '<span class="wl-state wl-state--open" title="' +
                    esc(gettext("Saat bölünüb, amma müəllim hələ təyin edilməyib (vakant).")) +
                    '"><i class="fas fa-user-clock" aria-hidden="true"></i> ' +
                    esc(fmt(gettext("Vakant: %(hours)s"), { hours: hours(vacant) })) + "</span>";
            }
            return '<span class="wl-state wl-state--ok"><i class="fas fa-circle-check" aria-hidden="true"></i> ' +
                esc(gettext("Tam bölünüb")) + "</span>";
        }
        return '<span class="wl-state wl-state--open"><i class="fas fa-hourglass-half" aria-hidden="true"></i> ' +
            esc(left ? fmt(gettext("Bölünməyib: %(hours)s"), { hours: hours(left) }) : gettext("Natamam")) + "</span>";
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
        var step = 1;
        var lecture = streamsBlock(card, labels, teacher, editable);
        if (lecture) step += 1;
        var seminar = kindBlock(card, "seminar", step, labels, teacher, editable);
        if (seminar) step += 1;
        var lab = kindBlock(card, "lab", step, labels, teacher, editable);
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
            stateBadge(card) +
            '<button type="button" class="wl-btn wl-btn--ghost wl-btn--sm" data-wl-card-rows-toggle data-card-id="' + esc(card.id) + '">' +
            '<i class="fas fa-table-list" aria-hidden="true"></i> ' + esc(fmt(gettext("Sətirlər (%(n)s)"), { n: rows.length })) +
            "</button>" +
            "</div></header>" +
            groupChips(card.groups) +
            ((card.warnings || []).indexOf("patok_unlinked") >= 0
                ? '<p class="wl-card__warn"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i> ' +
                  esc(gettext("Bu fəndə heç bir axına bağlanmamış mühazirə sətri var — «Axınları dəyiş» ilə qrupları axına salın.")) + "</p>"
                : "") +
            lecture +
            seminar +
            lab +
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
    Cards.arrange = arrange;
    Cards.typical = typical;
})(window, document);
