/* «Akademik qeydlər» — TƏLƏBƏ DETALI ÇEKMƏCƏSİ (drill-down).
 *
 * Niyə ayrı fayl? Cədvəl/süzgəc modulu (`academic_records.js`) ilə bu modul
 * arasında paylaşılan VƏZİYYƏT yoxdur: çekməcə yalnız sətir düyməsindəki
 * `data-*` atributlarından və endpoint-dən asılıdır. Ayırmaq həm modul ölçü
 * büdcəsini (600 sətir) saxlayır, həm də «cədvəl» ilə «detal» məsuliyyətlərini
 * bir-birindən təmizləyir.
 *
 * Çekməcənin DAVRANIŞI bu faylda deyil: fokus tələsi, Escape, fon klikı və
 * fokusun açan düyməyə qayıtması `static/js/ems_ui/overlay.js`-dədir. Burada
 * yalnız məzmun qurulur (semestr blokları) və `EMSOverlay.open()` çağırılır.
 *
 * Markup `ems_ui` sinifləri ilədir; köçürülmüş qiymət nişanı isə qəsdən
 * `registrar/partials/_legacy_grade_mark.html` ilə eyni markup-u təkrarlayır
 * (sətirlər JSON-dan qurulduğu üçün şablon include edilə bilmir) — CSS
 * ORTAQDIR (`css/legacy_mark.css`), yəni görünüş bir yerdən idarə olunur.
 */
(function () {
    "use strict";

    var DRAWER_ID = "acrStudentDrawer";

    function esc(value) {
        var box = document.createElement("div");
        box.textContent = value == null ? "" : value;
        // `innerHTML` dırnağı escape ETMİR — atribut dəyəri üçün əl ilə əlavə olunur.
        return box.innerHTML.replace(/"/g, "&quot;");
    }

    function i18nOf(root) {
        try {
            return JSON.parse(root.querySelector(".js-acr-i18n").textContent);
        } catch (err) {
            return {};
        }
    }

    function stateBox(icon, title, kind) {
        return (
            '<div class="ems-state' + (kind ? " ems-state--" + kind : "") + '" role="status">' +
            '<i class="fas ' + icon + ' ems-state__icon" aria-hidden="true"></i>' +
            (title ? '<p class="ems-state__title">' + esc(title) + "</p>" : "") +
            "</div>"
        );
    }

    function statusCell(T, row) {
        if (row.barred) {
            return '<span class="acr-status is-barred">' + esc(T.barred) + "</span>";
        }
        if (row.passed) {
            return '<span class="acr-status is-pass">' + esc(T.passed) + "</span>";
        }
        if (row.failed) {
            return '<span class="acr-status is-fail">' + esc(T.failed) + "</span>";
        }
        if (row.ungraded) {
            return '<span class="acr-status is-ungraded">' + esc(T.ungraded) + "</span>";
        }
        return '<span class="acr-status is-progress">' + esc(T.progress) + "</span>";
    }

    /* Kəsr/qiymətləndirilməmə səbəbi — RƏNG + MƏTN (rəng tək məna daşımır). */
    function reasonBadge(T, row) {
        if (row.fail_reason === "qb") {
            return '<div class="acr-reason is-qb"><i class="fas fa-user-clock" aria-hidden="true"></i> ' +
                esc(T.qb_badge) + "</div>";
        }
        if (row.fail_reason === "exam25") {
            return '<div class="acr-reason is-exam"><i class="fas fa-file-circle-xmark" aria-hidden="true"></i> ' +
                esc(T.exam25_badge) + "</div>";
        }
        if (row.ungraded) {
            return '<div class="acr-reason is-ungraded"><i class="fas fa-circle-question" aria-hidden="true"></i> ' +
                esc(T.ungraded_badge) + "</div>";
        }
        return "";
    }

    /* Qırmızı qeyd review statusundan ASILI DEYİL — VERIFIED halda da server
     * `lg.warning`-i saxlayır (bax exam_eligibility / legacy_grade_read). */
    function legacyMark(T, row) {
        var lg = row.legacy;
        if (!lg) {
            return "";
        }
        var lines = [lg.label + " — " + lg.notice];
        [
            ["source_system", T.legacy_source],
            ["source_reference", T.legacy_ref],
            ["recorded_at", T.legacy_date],
            ["raw_entry", T.legacy_raw_entry],
            ["raw_exam", T.legacy_raw_exam],
            ["raw_resit", T.legacy_raw_resit],
            ["raw_final", T.legacy_raw_final],
        ].forEach(function (pair) {
            if (lg[pair[0]]) {
                lines.push(pair[1] + ": " + lg[pair[0]]);
            }
        });
        if (lg.review_notice) {
            lines.push(lg.review_notice);
        }
        return (
            '<span class="legacy-grade-indicators"><span class="legacy-mark' +
            (lg.review_required ? " legacy-mark--unreviewed" : "") +
            '" tabindex="0" role="img" aria-label="' + esc(lg.label) + '" title="' + esc(lines.join("\n")) +
            '"><i class="fas fa-clock-rotate-left" aria-hidden="true"></i></span>' +
            (lg.warning ? '<strong class="legacy-grade-warning">' + esc(lg.warning) + "</strong>" : "") +
            "</span>"
        );
    }

    function subjectRow(T, row) {
        return (
            "<tr" + (row.failed ? ' class="acr-row--fail"' : "") + ">" +
            '<td class="acr-ta-left"><b>' + esc(row.code) + '</b><span class="acr-sem-subject">' + esc(row.name) +
            "</span>" + reasonBadge(T, row) + "</td>" +
            "<td" + (row.ungraded ? ' class="acr-muted"' : "") + ">" + esc(row.credit) + "</td>" +
            '<td class="acr-ta-left">' + esc(row.teacher) + "</td>" +
            "<td>" + esc(row.entry == null ? "—" : row.entry) + "</td>" +
            "<td>" + esc(row.exit == null ? "—" : row.exit) + "</td>" +
            "<td>" + (row.total == null ? "—" : "<b>" + esc(row.total) + "</b>") + legacyMark(T, row) + "</td>" +
            "<td>" + (row.letter
                ? '<span class="grade-' + esc(row.letter) + ' acr-letter">' + esc(row.letter) + "</span>"
                : "—") + "</td>" +
            "<td>" + statusCell(T, row) + "</td></tr>"
        );
    }

    function semesterBlock(T, sem) {
        var head =
            '<div class="acr-sem-head"><span class="acr-sem-title">' +
            '<i class="fas fa-calendar-alt" aria-hidden="true"></i> ' + esc(sem.year) + " · " + esc(sem.season) +
            '</span><span class="acr-sem-meta"><span class="ems-chip">' +
            '<i class="fas fa-award" aria-hidden="true"></i> ' + esc(sem.credits_earned) + " " + esc(T.sem_credit) +
            "</span>" +
            (sem.gpa != null ? '<span class="ems-chip">' + esc(T.avg_gpa) + " " + esc(sem.gpa) + "</span>" : "") +
            "</span></div>";
        var thead = [T.subject, T.credit, T.teacher, T.entry, T.exit, T.total, T.grade, T.status]
            .map(function (label, index) {
                var left = index === 0 || index === 2 ? ' class="acr-ta-left"' : "";
                return '<th scope="col"' + left + ">" + esc(label) + "</th>";
            })
            .join("");
        var body = (sem.rows || [])
            .map(function (row) {
                return subjectRow(T, row);
            })
            .join("");
        return (
            '<div class="acr-sem">' + head + '<div class="acr-sem-tablewrap"><table class="acr-sem-table"><thead><tr>' +
            thead + "</tr></thead><tbody>" + body + "</tbody></table></div></div>"
        );
    }

    function render(root, data) {
        var T = i18nOf(root);
        var body = root.querySelector(".js-acr-drawer-body");
        if (!body) {
            return;
        }
        if (!data || data.has_access === false) {
            body.innerHTML = stateBox("fa-triangle-exclamation", T.detail_error, "error");
            return;
        }
        var semesters = data.semesters || [];
        if (!semesters.length) {
            body.innerHTML = stateBox("fa-folder-open", T.no_record);
            return;
        }
        body.innerHTML = semesters
            .map(function (sem) {
                return semesterBlock(T, sem);
            })
            .join("");
    }

    /* Sətir düyməsi → çekməcə. Deleqasiya SƏNƏD səviyyəsindədir: cədvəl hər
     * render-də yenidən qurulsa da dinləyici yığılmır (AJAX-safe). */
    window.EMSDelegate.on("click", ".js-acr-view", function (event, btn) {
        var root = btn.closest(".acr");
        if (!root) {
            return;
        }
        var title = root.querySelector(".js-acr-drawer-title");
        var sub = root.querySelector(".js-acr-drawer-sub");
        var body = root.querySelector(".js-acr-drawer-body");
        if (!title || !body) {
            return;
        }
        title.textContent = btn.getAttribute("data-name") || "";
        if (sub) {
            sub.textContent = btn.getAttribute("data-meta") || "";
        }
        body.innerHTML = stateBox("fa-spinner fa-spin", "");
        if (window.EMSOverlay) {
            window.EMSOverlay.open(DRAWER_ID);
        } else {
            document.getElementById(DRAWER_ID).hidden = false;
        }
        fetch(root.dataset.detailUrl + "?student=" + encodeURIComponent(btn.getAttribute("data-sid")), {
            headers: { "X-Requested-With": "XMLHttpRequest" },
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("HTTP " + response.status);
                }
                return response.json();
            })
            .then(function (data) {
                render(root, data);
            })
            .catch(function () {
                render(root, null);
            });
    });
})();
