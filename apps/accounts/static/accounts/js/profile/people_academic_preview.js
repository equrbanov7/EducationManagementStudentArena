/* Köçürmə ön baxışının RENDER-i — `people_academic.js`-in alt moduludur.
 *
 * NİYƏ AYRI FAYL: çekməcə modulu 628 sətrə çatmışdı və `check_module_size.py`
 * SOFT_CAP=600 həddini keçirdi. Bölgü təsadüfi deyil: bu fayl SAF render-dir —
 * şəbəkə sorğusu, vəziyyət (state) və əməl göndərməsi YOXDUR. Ona verilən
 * `preview` obyekti `GET …/transfer-preview/` cavabının eynisidir.
 *
 * Müqavilə (`people_academic.js` buna söykənir):
 *
 *     window.EMSPeopleAcademicPreview.render(root, preview, label)
 *
 *   root    — `[data-psm-root]` elementi (içindəki `[data-psm-totals]`,
 *             `[data-psm-warnings]`, `[data-psm-preview-table]` doldurulur)
 *   preview — server cavabı: {ok, from_group, to_group, rows[], totals{},
 *             warnings[], blocking[]}
 *   label   — açar → tərcümə funksiyası (mətnlər `data-i18n-*` atributlarından
 *             gəlir; bu fayl Django şablon mühərrikindən KEÇMİR)
 *
 * Modul yüklənməyibsə çağıran tərəf ön baxışı sadəcə göstərmir — çekməcənin
 * qalan hissəsi işləməyə davam edir (null-safe).
 */
(function () {
    "use strict";

    /* Server kodu → `data-i18n-*` açarı. Naməlum kod SƏSSİZCƏ atılır: köhnə
     * brauzer keşi yeni server kodu ilə qarşılaşanda boş sətir göstərməsin. */
    var WARNING_KEYS = {
        attendance_resets: "warnAttendance",
        barred_cleared: "warnBarred",
        final_grades_hidden: "warnFinals",
        offerings_created: "warnOfferings"
    };
    var BLOCK_KEYS = {
        same_group: "blockSame",
        no_current_period: "blockPeriod",
        target_group_outside_scope: "blockScope"
    };

    function el(tag, className, value) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (value !== undefined && value !== null) {
            node.textContent = String(value);
        }
        return node;
    }

    function totalTile(value, labelText, modifier) {
        var tile = el("div", "psm__total" + (modifier ? " psm__total--" + modifier : ""));
        tile.appendChild(el("span", "psm__total-value", value));
        tile.appendChild(el("span", "psm__total-label", labelText));
        return tile;
    }

    function renderTotals(totals, preview, label) {
        if (!totals) {
            return;
        }
        totals.textContent = "";
        totals.appendChild(
            totalTile((preview.from_group && preview.from_group.name) || "—", label("summaryFrom"), "from")
        );
        totals.appendChild(totalTile((preview.to_group && preview.to_group.name) || "—", label("summaryTo"), "to"));
        if (preview.ok) {
            var sums = preview.totals || {};
            totals.appendChild(totalTile(sums.subjects || 0, label("summarySubjects")));
            totals.appendChild(totalTile(sums.absence_hours || 0, label("summaryAbsence")));
            totals.appendChild(totalTile(sums.marks || 0, label("summaryMarks")));
        }
    }

    function renderWarnings(warnings, preview, label) {
        if (!warnings) {
            return;
        }
        warnings.textContent = "";
        // Blok səbəbləri ƏVVƏL gəlir: onlar əməli ümumiyyətlə dayandırır.
        (preview.blocking || []).forEach(function (code) {
            warnings.appendChild(el("li", "psm__warning psm__warning--block", label(BLOCK_KEYS[code] || "error")));
        });
        (preview.warnings || []).forEach(function (code) {
            var key = WARNING_KEYS[code];
            if (key) {
                warnings.appendChild(el("li", "psm__warning", label(key)));
            }
        });
    }

    function renderTable(table, preview, label, warnings) {
        if (!table) {
            return;
        }
        table.textContent = "";
        var rows = preview.ok ? preview.rows || [] : [];
        var wrap = table.parentElement;
        if (!rows.length) {
            if (wrap) {
                wrap.hidden = true;
            }
            // Boş cədvəl əvəzinə mənalı cümlə: «köçürüləcək yazılış yoxdur».
            if (preview.ok && warnings) {
                warnings.appendChild(el("li", "psm__warning", label("previewEmpty")));
            }
            return;
        }
        if (wrap) {
            wrap.hidden = false;
        }
        var head = document.createElement("tr");
        [label("colSubject"), label("colAbsence"), label("colMarks"), label("colTarget")].forEach(function (title) {
            var th = el("th", null, title);
            th.scope = "col";
            head.appendChild(th);
        });
        var thead = document.createElement("thead");
        thead.appendChild(head);
        table.appendChild(thead);

        var body = document.createElement("tbody");
        rows.forEach(function (row) {
            var tr = document.createElement("tr");
            tr.appendChild(el("td", null, [row.subject_code, row.subject_name].filter(Boolean).join(" · ")));
            tr.appendChild(el("td", null, row.absence_hours || 0));
            tr.appendChild(el("td", null, (row.mark_count || 0) + (row.component_count || 0)));
            tr.appendChild(
                el(
                    "td",
                    row.target_offering_exists ? "psm__tag--ok" : "psm__tag--new",
                    row.target_offering_exists ? label("targetYes") : label("targetNo")
                )
            );
            body.appendChild(tr);
        });
        table.appendChild(body);
    }

    window.EMSPeopleAcademicPreview = {
        render: function (root, preview, label) {
            if (!root || !preview) {
                return;
            }
            var warnings = root.querySelector("[data-psm-warnings]");
            renderTotals(root.querySelector("[data-psm-totals]"), preview, label);
            renderWarnings(warnings, preview, label);
            renderTable(root.querySelector("[data-psm-preview-table]"), preview, label, warnings);
        }
    };
})();
