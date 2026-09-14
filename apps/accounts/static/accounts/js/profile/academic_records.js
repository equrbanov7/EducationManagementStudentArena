/* «Akademik qeydlər» (staff hierarchical academic records) kabinet bölməsi.
 *
 * Fakültə → kafedra → ixtisas → qrup → tələbə süzgəcləri (paylaşılan
 * EMSSearchableSelect komponenti: debounce + lazy + kaskad), `ems_ui` qutuları,
 * səhifələnmiş tələbə cədvəli və tələbə detalı ÇEKMƏCƏSİ. Data
 * `apps/accounts/views/academic_records.py` endpoint-lərindən gəlir; hər şey
 * server tərəfdə unit scope-a görə məhdudlaşdırılır.
 *
 * 2026-09-10 REDİZAYN — bu faylda nə dəyişdi:
 *   * markup artıq `ems_ui` sinifləri ilədir (`ems-kpi*`, `ems-table*`,
 *     `ems-state*`, `ems-btn*`) — bölmənin öz «ada» üslubu yoxdur;
 *   * SIFIR rəqəmlər soluq tire kimi çıxır, ona görə gözə yalnız əsl siqnal dəyir;
 *   * hər xanaya `data-label` qoyulur → mobil CSS cədvəli kart yığınına çevirir;
 *   * səhifə çevrilişində `total` SERVERDƏN İSTƏNMİR (sayğac sorğusu getmir) —
 *     rəqəm ilk səhifədən saxlanılır (bax apps/accounts/academic_records.py);
 *   * sətir/pager düymələri `EMSDelegate` ilə DELEQASİYA olunur: hər render-də
 *     yenidən `addEventListener` edilmir (AJAX-safe, dinləyici yığılmır);
 *   * tələbə detalı artıq mərkəzi modal deyil, `ems_ui` ÇEKMƏCƏSİDİR və ayrıca
 *     modula çıxıb (`academic_records_detail.js`) — burada yalnız süzgəc,
 *     qutular, cədvəl və səhifələmə qalır.
 */
(function () {
    "use strict";

    var COLSPAN = 9;

    /* Cari bölmə vəziyyəti — deleqasiya olunmuş handler-lər bunu oxuyur.
     * Bölmə swap olunanda `boot()` yenidən qurur (köhnə obyekt atılır). */
    var S = null;

    function esc(value) {
        var box = document.createElement("div");
        box.textContent = value == null ? "" : value;
        // `innerHTML` dırnağı escape ETMİR — atribut dəyərində istifadə etdiyimiz
        // üçün (title=, data-label=) əl ilə əlavə edilir.
        return box.innerHTML.replace(/"/g, "&quot;");
    }

    function state(icon, title, body, kind) {
        return (
            '<tr><td colspan="' + COLSPAN + '"><div class="ems-state' + (kind ? " ems-state--" + kind : "") +
            '" role="status"><i class="fas ' + icon + ' ems-state__icon" aria-hidden="true"></i>' +
            '<p class="ems-state__title">' + esc(title) + "</p>" +
            (body ? '<p class="ems-state__body">' + esc(body) + "</p>" : "") +
            "</div></td></tr>"
        );
    }

    /* ── Qutular (ems-kpi) ───────────────────────────────────────────────── */

    function kpi(value, label, tone) {
        return (
            '<div class="ems-kpi' + (tone ? " ems-kpi--" + tone : "") + '">' +
            '<div class="ems-kpi__label">' + esc(label) + "</div>" +
            '<div class="ems-kpi__value">' + esc(value) + "</div></div>"
        );
    }

    function renderCards(summary) {
        var T = S.T;
        if (!summary) {
            S.cards.innerHTML = "";
            return;
        }
        S.cards.innerHTML =
            kpi(summary.students, T.students, "accent-primary") +
            // Boş ÜOMG = hesablana bilmir (köhnə sistemdə nəticə yoxdur) —
            // sıfır yazmaq «sıfır bal aldı» iddiası olardı.
            kpi(summary.avg_gpa || T.gpa_na, T.avg_gpa, "accent-primary") +
            kpi(summary.credits_earned, T.credits, "accent-success") +
            kpi(summary.fails, T.fails, "accent-danger") +
            kpi(summary.qb, T.qb, "accent-warning") +
            kpi(summary.exam25, T.exam25, "accent-warning") +
            // Nə keçib, nə kəsilib — ayrıca qutu olmasa rəqəmlər cəmlənmir.
            kpi(summary.ungraded, T.ungraded, null);
    }

    function cardSkeleton() {
        var html = "";
        for (var i = 0; i < 7; i += 1) {
            html += '<div class="ems-kpi acr-kpi--loading"><div class="acr-skel acr-skel--card"></div></div>';
        }
        S.cards.innerHTML = html;
    }

    /* ── Cədvəl ──────────────────────────────────────────────────────────── */

    function rowSkeleton() {
        var html = "";
        for (var i = 0; i < 6; i += 1) {
            html += "<tr>";
            for (var c = 0; c < COLSPAN; c += 1) {
                html += '<td><div class="acr-skel"></div></td>';
            }
            html += "</tr>";
        }
        S.rows.innerHTML = html;
    }

    /* Rəqəm xanası: SIFIR soluq tire kimi çıxır (cədvəlin oxunaqlığı buradan). */
    function numCell(value, tone, label) {
        var body =
            Number(value) > 0
                ? '<span class="' + tone + '">' + esc(value) + "</span>"
                : '<span class="acr-zero" title="' + esc(S.T.zero) + '">—</span>';
        return '<td class="ems-table__num acr-n" data-label="' + esc(label) + '">' + body + "</td>";
    }

    function headCell(row, index) {
        return (
            '<th scope="row"><span class="acr-who"><span class="acr-idx">' + (S.page + index + 1) + "</span>" +
            '<span><span class="acr-name">' + esc(row.name) + "</span>" +
            '<span class="acr-sub"><span>@' + esc(row.username) + "</span>" +
            '<span class="acr-grp">' + esc(row.group) + "</span></span></span></span></th>"
        );
    }

    function gpaCell(row, label) {
        var T = S.T;
        var body = row.gpa
            ? esc(row.gpa)
            : '<span class="acr-gpa--na" title="' + esc(T.gpa_na) + '">—</span>';
        return '<td class="ems-table__num acr-gpa" data-label="' + esc(label) + '">' + body + "</td>";
    }

    function rowHtml(row, index) {
        var L = S.labels;
        var T = S.T;
        return (
            "<tr" + (row.fails > 0 ? ' class="acr-row--fail"' : "") + ">" +
            headCell(row, index) +
            // Xanada AD + rəsmi şifr AYRI sətirdədir (`program` etiketi şifri onsuz
            // da daşıyır — ikisini birlikdə yazsaq şifr təkrarlanırdı);
            // title isə tam etiketdir: ad + HƏR İKİ nəsil şifr.
            '<td class="acr-td-prog" data-label="' + esc(L[1]) + '"><span class="acr-prog__name" title="' +
            esc(row.program_full || row.program) + '">' + esc(row.program_name || row.program) + "</span>" +
            (row.program_code ? '<span class="acr-prog__code ems-mono">' + esc(row.program_code) + "</span>" : "") +
            "</td>" +
            numCell(row.credits_earned, "acr-credit", L[2]) +
            gpaCell(row, L[3]) +
            numCell(row.fails, "acr-n--bad", L[4]) +
            numCell(row.qb, "acr-n--warn", L[5]) +
            numCell(row.exam25, "acr-n--warn", L[6]) +
            numCell(row.ungraded, "acr-n--muted", L[7]) +
            '<td class="acr-td-act"><button type="button" class="ems-btn ems-btn--sm js-acr-view"' +
            ' data-sid="' + esc(row.student_id) + '" data-name="' + esc(row.name) + '"' +
            ' data-meta="' + esc(row.group + " · " + row.program) + '"' +
            ' aria-label="' + esc(T.view_full + ": " + row.name) + '">' +
            '<i class="fas fa-eye" aria-hidden="true"></i> ' + esc(T.view) + "</button></td></tr>"
        );
    }

    function renderPager(hasMore) {
        var T = S.T;
        var shown = S.shown;
        var total = S.total;
        var from = shown ? S.page + 1 : 0;
        var to = S.page + shown;
        S.count.textContent = total == null
            ? T.range + " " + from + "–" + to
            : T.range + " " + from + "–" + to + " / " + total + " " + T.of_total;
        S.pager.innerHTML =
            '<button type="button" class="ems-btn ems-btn--sm js-acr-prev"' + (S.page > 0 ? "" : " disabled") +
            '><i class="fas fa-chevron-left" aria-hidden="true"></i> ' + esc(T.prev) + "</button>" +
            '<button type="button" class="ems-btn ems-btn--sm js-acr-next"' + (hasMore ? "" : " disabled") +
            ">" + esc(T.next) + ' <i class="fas fa-chevron-right" aria-hidden="true"></i></button>';
    }

    function renderRows(data) {
        var T = S.T;
        if (data.has_access === false) {
            S.rows.innerHTML = state("fa-lock", T.no_access, T.no_access_body, "error");
            S.pager.innerHTML = "";
            S.count.textContent = "";
            S.cards.innerHTML = "";
            return;
        }
        // Yekun say YALNIZ ilk səhifədə gəlir (server sayğac sorğusunu atır) —
        // sonrakı səhifələrdə `null` olur və əvvəlki dəyər saxlanılır.
        if (data.total != null) {
            S.total = data.total;
        }
        var list = data.results || [];
        S.shown = list.length;
        if (!list.length) {
            S.rows.innerHTML = state("fa-folder-open", T.none, T.none_body);
            S.pager.innerHTML = "";
            S.count.textContent = "";
            return;
        }
        S.rows.innerHTML = list.map(rowHtml).join("");
        renderPager(!!data.has_more);
    }

    /* ── Sorğular ────────────────────────────────────────────────────────── */

    function params(extra) {
        var p = new URLSearchParams();
        var picks = S.picks;
        Object.keys(picks).forEach(function (key) {
            var value = picks[key].value();
            if (value) {
                p.set(key, value);
            }
        });
        if (S.yearSel && S.yearSel.value) {
            p.set("year", S.yearSel.value);
        }
        if (S.seasonSel && S.seasonSel.value) {
            p.set("season", S.seasonSel.value);
        }
        if (extra) {
            Object.keys(extra).forEach(function (k) {
                p.set(k, extra[k]);
            });
        }
        return p;
    }

    function getJSON(url) {
        return fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } }).then(function (response) {
            if (!response.ok) {
                throw new Error("HTTP " + response.status);
            }
            return response.json();
        });
    }

    function populateYears(years) {
        if (S.yearsDone || !S.yearSel || !years || !years.length) {
            return;
        }
        S.yearsDone = true;
        years.forEach(function (year) {
            var option = document.createElement("option");
            option.value = year;
            option.textContent = year;
            S.yearSel.appendChild(option);
        });
        if (typeof S.yearSel._refreshBootstrapSelect === "function") {
            S.yearSel._refreshBootstrapSelect();
        }
    }

    /* Qutular süzgəc sahəsinin TAMI üzrə aqreqatdır (cədvəl isə yalnız görünən
     * səhifə). Ona görə İKİ AYRI sorğu gedir: cədvəl dərhal gəlir, qutular öz
     * skeleton-u ilə sonra dolur — cədvəl onları gözləmir. */
    function loadSummary() {
        var seq = (S.summarySeq += 1);
        cardSkeleton();
        getJSON(S.url.summary + "?" + params().toString())
            .then(function (data) {
                if (seq !== S.summarySeq) {
                    return; // köhnəlmiş cavab — süzgəc dəyişib
                }
                populateYears(data.year_options);
                renderCards(data.summary);
            })
            .catch(function () {
                if (seq === S.summarySeq) {
                    S.cards.innerHTML = "";
                }
            });
    }

    function load() {
        var seq = (S.rowsSeq += 1);
        rowSkeleton();
        getJSON(S.url.data + "?" + params({ offset: S.page, limit: S.limit }).toString())
            .then(function (data) {
                if (seq === S.rowsSeq) {
                    renderRows(data);
                }
            })
            .catch(function () {
                if (seq === S.rowsSeq) {
                    S.rows.innerHTML = state("fa-triangle-exclamation", S.T.load_error, S.T.load_error_body, "error");
                    S.pager.innerHTML = "";
                    S.count.textContent = "";
                }
            });
    }

    function reload() {
        S.page = 0;
        S.total = null;
        load();
        loadSummary();
    }

    /* ── Deleqasiya (bir dəfə, sənəd səviyyəsində) ───────────────────────── */

    window.EMSDelegate.on("click", ".js-acr-prev", function () {
        if (S && S.page > 0) {
            S.page = Math.max(0, S.page - S.limit);
            load();
        }
    });

    window.EMSDelegate.on("click", ".js-acr-next", function (event, btn) {
        if (S && !btn.disabled) {
            S.page += S.limit;
            load();
        }
    });

    window.EMSDelegate.on("click", ".js-acr-reset", function () {
        if (!S) {
            return;
        }
        Object.keys(S.picks).forEach(function (key) {
            S.picks[key].reset();
        });
        [S.yearSel, S.seasonSel].forEach(function (select) {
            if (!select) {
                return;
            }
            select.value = "";
            if (typeof select._refreshBootstrapSelect === "function") {
                select._refreshBootstrapSelect();
            } else if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.sync === "function") {
                window.EMSBootstrapSelect.sync(select);
            }
        });
        reload();
    });

    /* ── Qurulum ─────────────────────────────────────────────────────────── */

    function buildPickers(root) {
        var SS = window.EMSSearchableSelect;
        var url = S.url;
        var faculty = SS.create(root.querySelector(".js-acr-faculty"), { url: url.faculty, onChange: reload });
        var department = SS.create(root.querySelector(".js-acr-department"), {
            url: url.department,
            dependParam: "faculty",
            getDependValue: function () {
                return faculty.value();
            },
            onChange: reload,
        });
        var program = SS.create(root.querySelector(".js-acr-program"), {
            url: url.program,
            dependParam: "department",
            getDependValue: function () {
                return department.value();
            },
            onChange: reload,
        });
        var group = SS.create(root.querySelector(".js-acr-group"), {
            url: url.group,
            dependParam: "department",
            getDependValue: function () {
                return department.value();
            },
            onChange: reload,
        });
        var student = SS.create(root.querySelector(".js-acr-student"), {
            url: url.student,
            dependParam: "group",
            getDependValue: function () {
                return group.value();
            },
            onChange: reload,
        });
        // Kaskad — üst dəyişəndə alt seçimlər sıfırlanır (növbəti sorğu daralır).
        faculty.on("change", function () {
            [department, program, group, student].forEach(function (pick) {
                pick.reset();
            });
        });
        department.on("change", function () {
            [program, group, student].forEach(function (pick) {
                pick.reset();
            });
        });
        group.on("change", function () {
            student.reset();
        });
        return { faculty: faculty, department: department, program: program, group: group, student: student };
    }

    function boot() {
        if (!window.EMSSearchableSelect) {
            window.setTimeout(boot, 30); // komponent `defer` ilə gəlir — gözlə
            return;
        }
        var root = document.querySelector(".acr");
        if (!root || root.dataset.acrInit === "1") {
            return;
        }
        root.dataset.acrInit = "1";

        var sizeSel = root.querySelector(".js-acr-size");
        var labels = [];
        root.querySelectorAll(".acr-table thead th").forEach(function (th) {
            labels.push((th.textContent || "").trim());
        });

        var i18n = {};
        try {
            i18n = JSON.parse(root.querySelector(".js-acr-i18n").textContent);
        } catch (err) {
            i18n = {};
        }

        S = {
            T: i18n,
            labels: labels,
            url: {
                data: root.dataset.dataUrl,
                summary: root.dataset.summaryUrl,
                detail: root.dataset.detailUrl,
                faculty: root.dataset.facultyUrl,
                department: root.dataset.departmentUrl,
                program: root.dataset.programUrl,
                group: root.dataset.groupUrl,
                student: root.dataset.studentUrl,
            },
            cards: root.querySelector(".js-acr-cards"),
            rows: root.querySelector(".js-acr-rows"),
            pager: root.querySelector(".js-acr-pager"),
            count: root.querySelector(".js-acr-count"),
            yearSel: root.querySelector(".js-acr-year"),
            seasonSel: root.querySelector(".js-acr-season"),
            page: 0,
            limit: sizeSel ? Number(sizeSel.value) || 25 : 25,
            total: null,
            shown: 0,
            yearsDone: false,
            summarySeq: 0,
            rowsSeq: 0,
            picks: null,
        };
        S.picks = buildPickers(root);

        [S.yearSel, S.seasonSel].forEach(function (select) {
            if (select) {
                select.addEventListener("change", reload);
            }
        });
        if (sizeSel) {
            sizeSel.addEventListener("change", function () {
                S.limit = Number(sizeSel.value) || 25;
                S.page = 0;
                load();
            });
        }

        load();
        loadSummary();
    }

    window.EMSReady(boot);
})();
