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

    function esc(value) {
        var node = document.createElement("span");
        node.textContent = value == null ? "" : String(value);
        return node.innerHTML;
    }

    function percent(assigned, total) {
        if (!total) return 0;
        return Math.min(100, Math.round((assigned * 100) / total));
    }

    /** Bir sətrin fəaliyyət zolaqları. */
    function activityBlock(row, labels) {
        var keys = Object.keys(row.activities || {});
        if (!keys.length) {
            return '<p class="wl-act__numbers">Bu sətirdə bölünəcək saat yoxdur.</p>';
        }
        return keys
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
                    '">Bölüşdür</button>' +
                    "</div>"
                );
            })
            .join("");
    }

    function assignmentChips(row) {
        if (!row.assignments || !row.assignments.length) return "";
        return (
            '<ul class="wl-assign-list">' +
            row.assignments
                .map(function (item) {
                    return (
                        '<li class="wl-assign-chip' +
                        (item.is_vacant ? " is-vacant" : "") +
                        '">' +
                        esc(item.teacher_name) +
                        " · " +
                        esc(item.activity_label) +
                        " · " +
                        item.hours +
                        "s" +
                        '<button type="button" class="wl-assign-chip__remove" aria-label="Bölgünü sil"' +
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

    /** Sətir kartlarını cədvəl sahəsinə yazır. */
    Render.rows = function renderRows(host, rows, labels) {
        if (!host) return;
        labels = labels || {};
        host.innerHTML = (rows || [])
            .map(function (row) {
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
                    '">Redaktə</button>' +
                    '<button type="button" class="wl-btn wl-btn--danger" data-wl-row-remove data-row-id="' +
                    esc(row.id) +
                    '">Sil</button>' +
                    "</div>" +
                    "</div>" +
                    '<div class="wl-row__meta">' +
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
                    assignmentChips(row) +
                    "</article>"
                );
            })
            .join("");
    };

    /** Sağ paneldəki müəllim kartları. */
    Render.teachers = function renderTeachers(host, cards) {
        if (!host) return;
        if (!cards || !cards.length) {
            host.innerHTML = '<p class="wl-teacher__numbers">Hələ bölgü yoxdur.</p>';
            return;
        }
        host.innerHTML = cards
            .map(function (card) {
                var cls = card.is_vacant ? " is-vacant" : card.is_over_norm ? " is-over" : "";
                return (
                    '<div class="wl-teacher' +
                    cls +
                    '">' +
                    '<div class="wl-teacher__name">' +
                    esc(card.name) +
                    "</div>" +
                    '<div class="wl-teacher__numbers">' +
                    card.hours +
                    (card.norm_hours ? " / " + card.norm_hours : "") +
                    " saat · " +
                    card.fill_percent +
                    "%</div>" +
                    '<div class="wl-teacher__bar"><span class="wl-teacher__fill" style="--wl-fill:' +
                    Math.min(100, card.fill_percent || 0) +
                    '%"></span></div>' +
                    "</div>"
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
            '<div class="wl-confirm__stat"><span>Sətir</span><b>' +
            readiness.row_count +
            "</b></div>" +
            '<div class="wl-confirm__stat"><span>Jurnal açılışı</span><b>' +
            readiness.sync_candidates +
            "</b></div>" +
            '<div class="wl-confirm__stat"><span>Vakant saat</span><b>' +
            readiness.vacant_hours +
            "</b></div>" +
            '<div class="wl-confirm__stat"><span>Yarımçıq sətir</span><b>' +
            (readiness.incomplete_rows || []).length +
            "</b></div>";
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
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
            window.EMSBootstrapSelect.refresh(select);
        }
    };
})(window, document);
