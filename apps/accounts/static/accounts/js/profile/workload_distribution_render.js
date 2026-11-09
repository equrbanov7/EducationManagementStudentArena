/*
 * Dərs yükü — SAF RENDER modulu (`window.EMSWorkloadRender`).
 *
 * Burada NƏ fetch, NƏ də listener var: yalnız data → DOM. Əsas modul
 * (`workload_distribution.js`) bunu null-safe oxuyur, ona görə fayl sırası
 * pozulsa da səhifə çökmür (bölmə sadəcə init olunmur).
 *
 * AJAX-safe: DOM lookup-ları hər çağırışda yenidən aparılır, qlobal vəziyyət
 * saxlanılmır.
 */
(function (window, document) {
    "use strict";

    var Render = (window.EMSWorkloadRender = window.EMSWorkloadRender || {});

    // 2026-09-13 frontend auditi F7: AZ literallar `gettext()`-ə keçirildi
    // (JavaScriptCatalog `base.html`-dədir; fallback msgid-in özüdür).
    var gettext = window.gettext || function (value) { return value; };

    function esc(value) {
        var node = document.createElement("span");
        node.textContent = value == null ? "" : String(value);
        return node.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function percent(assigned, total) {
        if (!total) return 0;
        return Math.min(100, Math.round((assigned * 100) / total));
    }

    /**
     * Patokun ikinci/üçüncü qrupu (sahib 2026-11-07): mühazirə aparıcı sətirdə bölünür, burada YALNIZ görünür —
     * saat qrupun saatıdır, müəllimin yükünə ikinci dəfə düşmür (redaktə/bölgü düyməsi yoxdur).
     */
    function patokLine(row, labels) {
        var info = row.patok_lecture;
        if (!info) return "";
        var note = info.groups
            ? interpolate(gettext("Patok · %(groups)s ilə birlikdə"), { groups: info.groups }, true)
            : gettext("Patok");
        if (info.teacher_name) note += " · " + info.teacher_name;
        return (
            '<div class="wl-act wl-act--patok is-complete">' +
            '<span class="wl-act__label">' + esc(labels.lecture || "") + "</span>" +
            '<span class="wl-act__bar"><span class="wl-act__fill" style="--wl-fill:100%"></span></span>' +
            '<span class="wl-act__numbers">' + info.hours + " " + esc(gettext("saat")) + "</span>" +
            '<span class="wl-act__patok">' + esc(note) + "</span>" +
            "</div>"
        );
    }

    /** Bir sətrin fəaliyyət zolaqları. */
    function activityBlock(row, labels) {
        var keys = Object.keys(row.activities || {});
        if (!keys.length) {
            return patokLine(row, labels) ||
                '<p class="wl-act__numbers">' + esc(gettext("Bu sətirdə bölünəcək saat yoxdur.")) + "</p>";
        }
        return patokLine(row, labels) + keys
            .map(function (key) {
                var info = row.activities[key];
                var cls = info.is_complete ? " is-complete" : "";
                return (
                    '<div class="wl-act' +
                    cls +
                    '">' +
                    '<span class="wl-act__label">' +
                    esc(labels[key] || key) +
                    "</span>" +
                    '<span class="wl-act__bar"><span class="wl-act__fill" style="--wl-fill:' +
                    percent(info.assigned, info.total) +
                    '%"></span></span>' +
                    '<span class="wl-act__numbers">' +
                    info.assigned +
                    " / " +
                    info.total +
                    "</span>" +
                    '<button type="button" class="wl-btn wl-btn--ghost" data-wl-assign-open data-row-id="' +
                    esc(row.id) +
                    '" data-activity="' +
                    esc(key) +
                    '">' + esc(gettext("Bölüşdür")) + "</button>" +
                    // 2026-10-15: fəaliyyəti sətirdən çıxar (cəm 0, bölgüsü silinir; təsdiqlənmişdə — düzəliş ilə).
                    '<button type="button" class="wl-act__remove" data-wl-activity-remove data-row-id="' +
                    esc(row.id) + '" data-activity="' + esc(key) + '" data-activity-label="' +
                    esc(labels[key] || key) + '" aria-label="' + esc(gettext("Fəaliyyəti çıxar")) +
                    '" title="' + esc(gettext("Fəaliyyəti çıxar")) + '">&times;</button>' +
                    "</div>"
                );
            })
            .join("");
    }

    /** Sağ paneldə seçilmiş müəllimin (və ya «Vakant»ın) təyinatı mı — çip vurğulanır. */
    function isMatch(item, teacher) {
        if (!teacher) return false;
        return teacher === "vacant" ? !!item.is_vacant : String(item.teacher_id) === String(teacher);
    }

    function assignmentChips(row, teacher) {
        if (!row.assignments || !row.assignments.length) return "";
        return (
            '<ul class="wl-assign-list">' +
            row.assignments
                .map(function (item) {
                    return (
                        '<li class="wl-assign-chip' +
                        (item.is_vacant ? " is-vacant" : "") +
                        (isMatch(item, teacher) ? " is-match" : "") +
                        '">' +
                        esc(item.teacher_name) +
                        " · " +
                        esc(item.activity_label) +
                        " · " +
                        item.hours +
                        "s" +
                        '<button type="button" class="wl-assign-chip__edit" aria-label="' + esc(gettext("Bölgünü redaktə et")) + '"' +
                        ' data-wl-assign-edit data-row-id="' + esc(row.id) + '" data-assignment-id="' + esc(item.id) +
                        '"><i class="fas fa-pen" aria-hidden="true"></i></button>' +
                        '<button type="button" class="wl-assign-chip__remove" aria-label="' + esc(gettext("Bölgünü sil")) + '"' +
                        ' data-wl-assign-remove data-assignment-id="' +
                        esc(item.id) +
                        '">&times;</button>' +
                        "</li>"
                    );
                })
                .join("") +
            "</ul>"
        );
    }

    /** İntensiv kurs sətri (2026-10-25): redaktə/bölgü düymələri YOX — jurnal keçidi + «Ləğv et». */
    function intensiveRow(row) {
        var info = row.intensive || {};
        var chips = (row.assignments || [])
            .map(function (item) {
                return '<li class="wl-assign-chip">' + esc(item.teacher_name) + " · " + esc(item.activity_label) +
                    " · " + item.hours + "s</li>";
            })
            .join("");
        return (
            '<article class="wl-row wl-row--intensive is-complete" role="listitem" data-wl-row data-row-id="' +
            esc(row.id) + '">' +
            '<div class="wl-row__head"><h3 class="wl-row__subject">' + esc(row.subject) +
            ' <span class="wl-intensive-badge">' + esc(gettext("İntensiv")) + "</span></h3>" +
            '<div class="wl-row__actions">' +
            (info.journal_url ? '<a class="wl-btn wl-btn--ghost" href="' + esc(info.journal_url) + '">' +
                esc(gettext("Jurnal")) + "</a>" : "") +
            '<button type="button" class="wl-btn wl-btn--danger" data-wl-intensive-cancel data-row-id="' +
            esc(row.id) + '">' + esc(gettext("Ləğv et")) + "</button>" +
            "</div></div>" +
            '<div class="wl-row__meta"><span>' + esc(info.starts_on) + " – " + esc(info.ends_on) + "</span>" +
            "<span>" + row.total_hours + " " + esc(gettext("saat")) + "</span>" +
            "<span>" + esc(info.students) + " " + esc(gettext("tələbə")) + "</span>" +
            (row.groups_text ? "<span>" + esc(row.groups_text) + "</span>" : "") +
            (info.note ? "<span>" + esc(info.note) + "</span>" : "") +
            "</div>" +
            (chips ? '<ul class="wl-assign-list">' + chips + "</ul>" : "") +
            "</article>"
        );
    }

    /**
     * «Bütün kafedralar» (2026-11-04): YALNIZ OXU kartı — kafedra adı, saat zolaqları, bölgü çipləri; heç bir
     * yazı düyməsi yoxdur. Redaktə sətrin öz kafedrasında: `row.edit_url` (server `can_edit` verəndə) həmin
     * kafedranı + ili + sətir fokusunu açır; əhatədən kənar kafedrada «Yalnız baxış» nişanı.
     */
    function readonlyRow(row, labels, teacher) {
        var acts = Object.keys(row.activities || {})
            .map(function (key) {
                var info = row.activities[key];
                return (
                    '<div class="wl-act' + (info.is_complete ? " is-complete" : "") + '">' +
                    '<span class="wl-act__label">' + esc(labels[key] || key) + "</span>" +
                    '<span class="wl-act__bar"><span class="wl-act__fill" style="--wl-fill:' +
                    percent(info.assigned, info.total) + '%"></span></span>' +
                    '<span class="wl-act__numbers">' + info.assigned + " / " + info.total + "</span>" +
                    "</div>"
                );
            })
            .join("");
        var chips = (row.assignments || [])
            .map(function (item) {
                return (
                    '<li class="wl-assign-chip' + (item.is_vacant ? " is-vacant" : "") +
                    (isMatch(item, teacher) ? " is-match" : "") + '">' +
                    esc(item.teacher_name) + " · " + esc(item.activity_label) + " · " + item.hours + "s</li>"
                );
            })
            .join("");
        var action = row.edit_url
            ? '<a class="wl-btn wl-btn--ghost" href="' + esc(row.edit_url) + '">' +
              '<i class="fas fa-pen" aria-hidden="true"></i> ' + esc(gettext("Kafedrada redaktə et")) + "</a>"
            : '<span class="wl-row__readonly"><i class="fas fa-eye" aria-hidden="true"></i>' +
              esc(gettext("Yalnız baxış")) + "</span>";
        return (
            '<article class="wl-row wl-row--readonly' + (row.teaching_complete ? " is-complete" : "") +
            '" role="listitem" data-wl-row data-row-id="' + esc(row.id) + '">' +
            '<div class="wl-row__head"><div><h3 class="wl-row__subject">' + esc(row.subject) +
            (row.intensive ? ' <span class="wl-intensive-badge">' + esc(gettext("İntensiv")) + "</span>" : "") +
            "</h3>" +
            '<p class="wl-row__chair"><span class="wl-row__chair-name">' + esc(row.chair_name) + "</span>" +
            (row.faculty_name ? "<span>" + esc(row.faculty_name) + "</span>" : "") +
            (row.task_status_label ? "<span>· " + esc(row.task_status_label) + "</span>" : "") +
            "</p></div>" +
            '<div class="wl-row__actions">' + action + "</div></div>" +
            '<div class="wl-row__meta"><span>' + esc(row.season_label) + "</span>" +
            (row.specialty ? "<span>" + esc(row.specialty) + "</span>" : "") +
            (row.groups_text ? "<span>" + esc(row.groups_text) + "</span>" : "") +
            "<span>" + row.total_hours + " " + esc(gettext("saat")) + "</span>" +
            (row.credits ? "<span>" + esc(row.credits) + " kredit</span>" : "") +
            "</div>" +
            patokLine(row, labels) +
            acts +
            (chips ? '<ul class="wl-assign-list">' + chips + "</ul>" : "") +
            "</article>"
        );
    }

    function rowHtml(row, labels, teacher) {
        if (row.chair_name !== undefined) return readonlyRow(row, labels, teacher); // «Bütün kafedralar»
        if (row.intensive) return intensiveRow(row);
        return (
            '<article class="wl-row' +
            (row.teaching_complete ? " is-complete" : "") +
            '" role="listitem" data-wl-row data-row-id="' +
            esc(row.id) +
            '">' +
            '<div class="wl-row__head">' +
            '<h3 class="wl-row__subject">' +
            esc(row.subject) +
            "</h3>" +
            '<div class="wl-row__actions">' +
            '<button type="button" class="wl-btn wl-btn--ghost" data-wl-row-edit data-row-id="' +
            esc(row.id) +
            '">' + esc(gettext("Redaktə")) + "</button>" +
            '<button type="button" class="wl-btn wl-btn--danger" data-wl-row-remove data-row-id="' +
            esc(row.id) +
            '">' + esc(gettext("Sil")) + "</button>" +
            "</div>" +
            "</div>" +
            '<div class="wl-row__meta">' +
            (row.is_amend_target
                ? '<span class="wl-row__amend">' + esc(gettext("Düzəliş açıqdır")) + "</span>"
                : "") +
            "<span>" +
            esc(row.season_label) +
            "</span>" +
            (row.specialty ? "<span>" + esc(row.specialty) + "</span>" : "") +
            (row.groups_text ? "<span>" + esc(row.groups_text) + "</span>" : "") +
            "<span>" +
            row.total_hours +
            " saat</span>" +
            (row.credits ? "<span>" + esc(row.credits) + " kredit</span>" : "") +
            "</div>" +
            activityBlock(row, labels) +
            assignmentChips(row, teacher) +
            "</article>"
        );
    }

    /** 2026-11-09: fənn kartının açılan «Sətirlər» hissəsi köhnə sətir kartını təkrar işlədir (`workload_distribution_cards.js`). */
    Render.rowHtml = rowHtml;

    /**
     * Sətir kartlarını cədvəl sahəsinə yazır. ``opts.append`` — mövcud kartların ARDINA əlavə (tənbəl yükləmə,
     * 2026-10-25); ``opts.teacher`` — seçilmiş müəllimin çipləri vurğulanır.
     */
    Render.rows = function renderRows(host, rows, labels, opts) {
        if (!host) return;
        opts = opts || {};
        labels = labels || {};
        var html = (rows || [])
            .map(function (row) {
                return rowHtml(row, labels, opts.teacher || "");
            })
            .join("");
        if (opts.append) {
            host.insertAdjacentHTML("beforeend", html);
        } else {
            host.innerHTML = html;
        }
    };

    /**
     * Sağ paneldəki müəllim kartları. Hər kart DÜYMƏDİR (``aria-pressed``): klik sol siyahını həmin müəllimə
     * süzür (``workload_distribution_list.js``); ``opts.active`` — seçilmiş müəllim ("vacant" — Vakant kartı).
     */
    Render.teachers = function renderTeachers(host, cards, opts) {
        if (!host) return;
        var active = (opts && opts.active) || "";
        if (!cards || !cards.length) {
            host.innerHTML = '<p class="wl-teacher__numbers">' + esc(gettext("Hələ bölgü yoxdur.")) + "</p>";
            return;
        }
        host.innerHTML = cards
            .map(function (card) {
                var key = card.is_vacant ? "vacant" : String(card.teacher_id);
                var cls = card.is_vacant ? " is-vacant" : card.is_over_norm ? " is-over" : "";
                var on = key === String(active);
                return (
                    '<button type="button" class="wl-teacher' +
                    cls +
                    (on ? " is-active" : "") +
                    '" data-wl-teacher-id="' +
                    esc(key) +
                    '" data-wl-teacher-name="' +
                    esc(card.name) +
                    '" aria-pressed="' +
                    (on ? "true" : "false") +
                    '">' +
                    '<span class="wl-teacher__name">' +
                    esc(card.name) +
                    "</span>" +
                    '<span class="wl-teacher__numbers">' +
                    card.hours +
                    (card.norm_hours ? " / " + card.norm_hours : "") +
                    " saat · " +
                    card.fill_percent +
                    "%</span>" +
                    '<span class="wl-teacher__bar"><span class="wl-teacher__fill" style="--wl-fill:' +
                    Math.min(100, card.fill_percent || 0) +
                    '%"></span></span>' +
                    "</button>"
                );
            })
            .join("");
    };

    /** Təsdiq modalının rəqəm zolağı. */
    Render.readiness = function renderReadiness(host, readiness) {
        if (!host) return;
        if (!readiness) {
            host.innerHTML = "";
            return;
        }
        host.innerHTML =
            '<div class="wl-confirm__stat"><span>' + esc(gettext("Sətir")) + "</span><b>" +
            readiness.row_count +
            "</b></div>" +
            '<div class="wl-confirm__stat"><span>' + esc(gettext("Jurnal açılışı")) + "</span><b>" +
            readiness.sync_candidates +
            "</b></div>" +
            '<div class="wl-confirm__stat"><span>Vakant saat</span><b>' +
            readiness.vacant_hours +
            "</b></div>" +
            '<div class="wl-confirm__stat"><span>' + esc(gettext("Yarımçıq sətir")) + "</span><b>" +
            (readiness.incomplete_rows || []).length +
            "</b></div>";
    };

    /** Bölgü modalının müəllim siyahısı: «Vakant» + hovuz (cari saat, kənar/bağlanmamış qeydi). */
    Render.teacherPicker = function teacherPicker(select, results) {
        if (!select) return;
        var html = '<option value="">' + esc(gettext("Vakant (müəllim təyin edilməyib)")) + "</option>";
        (results || []).forEach(function (item) {
            var suffix = item.current_hours != null ? " · " + item.current_hours + "s" : "";
            // Başqa kafedranın müəllimi (saathesabı): ştat kafedrası yazılır; təyinatda bu kafedrada
            // ƏLAVƏ üzvlük alır, ştatı dəyişmir (sahib 2026-10-25).
            var mark = item.is_outside
                ? " — " + gettext("kənar, ştat: %(chair)s").replace("%(chair)s", item.home_chair || "—")
                : item.is_chair_member
                  ? ""
                  : " " + gettext("(kafedraya bağlanmamış)");
            html += '<option value="' + esc(item.id) + '">' + esc(item.full_name) + suffix + esc(mark) + "</option>";
        });
        select.innerHTML = html;
        if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.refresh(select);
    };

    Render.options = function fillOptions(select, items, opts) {
        if (!select) return;
        opts = opts || {};
        var placeholder = opts.placeholder;
        var html = placeholder ? '<option value="">' + esc(placeholder) + "</option>" : "";
        html += (items || [])
            .map(function (item) {
                return (
                    '<option value="' +
                    esc(item.id || item.key) +
                    '">' +
                    esc(item.label || item.name) +
                    "</option>"
                );
            })
            .join("");
        select.innerHTML = html;
        if (select.multiple && window.EMSMultiSelect) {
            window.EMSMultiSelect.refresh(select); // qruplar — stilli çoxseçim
        } else if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
            window.EMSBootstrapSelect.refresh(select);
        }
    };
})(window, document);
