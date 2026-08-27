/* Staff hierarchical academic-records ("Akademik qeydlər") cabinet section.
 * Fakültə → kafedra → ixtisas → qrup → tələbə süzgəcləri (paylaşılan
 * EMSSearchableSelect komponenti ilə: debounce + lazy + kaskad), xülasə box-ları
 * + səhifələnmiş tələbə cədvəli + tələbə detalı modalı. Data registrar
 * "hesabatlar" endpoint-lərindən gəlir; hər şey server tərəfdə unit scope-a görə
 * məhdudlaşdırılır (istifadəçi yalnız öz strukturunun altını görür). Profil SPA-nın
 * digər data-driven bölmələri (exam-center-stats) ilə eyni boot nümunəsi.
 */
(function () {
    "use strict";

    function boot() {
        if (!window.EMSSearchableSelect) {
            window.setTimeout(boot, 30);
            return;
        }
        var root = document.querySelector(".acr");
        if (!root || root.dataset.acrInit === "1") {
            return;
        }
        root.dataset.acrInit = "1";

        var U = {
            data: root.dataset.dataUrl,
            summary: root.dataset.summaryUrl,
            detail: root.dataset.detailUrl,
            faculty: root.dataset.facultyUrl,
            department: root.dataset.departmentUrl,
            program: root.dataset.programUrl,
            group: root.dataset.groupUrl,
            student: root.dataset.studentUrl,
        };
        var cards = root.querySelector(".js-acr-cards");
        var rows = root.querySelector(".js-acr-rows");
        var pager = root.querySelector(".js-acr-pager");
        var T = {};
        try {
            T = JSON.parse(root.querySelector(".js-acr-i18n").textContent);
        } catch (e) {
            T = {};
        }

        var page = 0; // offset (0-based)
        var LIMIT = 25;
        var yearSel = root.querySelector(".js-acr-year");
        var seasonSel = root.querySelector(".js-acr-season");
        var yearPopulated = false;

        function esc(s) {
            var d = document.createElement("div");
            d.textContent = s == null ? "" : s;
            return d.innerHTML;
        }

        var SS = window.EMSSearchableSelect;
        var facultyPick = SS.create(root.querySelector(".js-acr-faculty"), { url: U.faculty, onChange: reload });
        var deptPick = SS.create(root.querySelector(".js-acr-department"), {
            url: U.department,
            dependParam: "faculty",
            getDependValue: function () {
                return facultyPick.value();
            },
            onChange: reload,
        });
        var programPick = SS.create(root.querySelector(".js-acr-program"), {
            url: U.program,
            dependParam: "department",
            getDependValue: function () {
                return deptPick.value();
            },
            onChange: reload,
        });
        var groupPick = SS.create(root.querySelector(".js-acr-group"), {
            url: U.group,
            dependParam: "department",
            getDependValue: function () {
                return deptPick.value();
            },
            onChange: reload,
        });
        var studentPick = SS.create(root.querySelector(".js-acr-student"), {
            url: U.student,
            dependParam: "group",
            getDependValue: function () {
                return groupPick.value();
            },
            onChange: reload,
        });

        // Kaskad — üst dəyişəndə alt seçimlər sıfırlanır (növbəti sorğu daralır).
        facultyPick.on("change", function () {
            deptPick.reset();
            programPick.reset();
            groupPick.reset();
            studentPick.reset();
        });
        deptPick.on("change", function () {
            programPick.reset();
            groupPick.reset();
            studentPick.reset();
        });
        groupPick.on("change", function () {
            studentPick.reset();
        });

        function params(extra) {
            var p = new URLSearchParams();
            if (facultyPick.value()) p.set("faculty", facultyPick.value());
            if (deptPick.value()) p.set("department", deptPick.value());
            if (programPick.value()) p.set("program", programPick.value());
            if (groupPick.value()) p.set("group", groupPick.value());
            if (studentPick.value()) p.set("student", studentPick.value());
            if (yearSel && yearSel.value) p.set("year", yearSel.value);
            if (seasonSel && seasonSel.value) p.set("season", seasonSel.value);
            if (extra) {
                Object.keys(extra).forEach(function (k) {
                    p.set(k, extra[k]);
                });
            }
            return p;
        }

        function card(n, label, mod) {
            return (
                '<div class="acr-card' + (mod ? " acr-card--" + mod : "") + '">' +
                '<div class="acr-card__n">' + esc(n) + "</div>" +
                '<div class="acr-card__l">' + esc(label) + "</div></div>"
            );
        }

        function renderCards(s) {
            if (!s) {
                cards.innerHTML = "";
                return;
            }
            cards.innerHTML =
                card(s.students, T.students) +
                card(s.credits_earned, T.credits, "ok") +
                card(s.fails, T.fails, "bad") +
                card(s.qb, T.qb, "warn") +
                card(s.exam25, T.exam25, "warn") +
                // Nə keçib, nə kəsilib — imtahan çıxış balı yoxdur. Ayrıca qutu
                // olmasa rəqəmlər cəmlənmir (tələbə × fənn sayı ilə uyğun gəlmir).
                card(s.ungraded, T.ungraded, "muted") +
                card(s.avg_gpa, T.avg_gpa);
        }

        function skeleton() {
            var tr = "";
            for (var i = 0; i < 8; i++) {
                tr += "<tr>";
                for (var c = 0; c < 11; c++) {
                    tr += '<td><div class="acr-skel"></div></td>';
                }
                tr += "</tr>";
            }
            rows.innerHTML = tr;
        }

        function renderRows(d) {
            if (d.has_access === false) {
                rows.innerHTML =
                    '<tr><td colspan="11"><div class="acr-state"><i class="fas fa-lock"></i>' + esc(T.no_access) + "</div></td></tr>";
                pager.innerHTML = "";
                cards.innerHTML = "";
                return;
            }
            var list = d.results || [];
            if (!list.length) {
                rows.innerHTML =
                    '<tr><td colspan="11"><div class="acr-state"><i class="fas fa-folder-open"></i>' + esc(T.none) + "</div></td></tr>";
                pager.innerHTML = "";
                return;
            }
            rows.innerHTML = list
                .map(function (r, i) {
                    var failCls = r.fails > 0 ? " acr-row--fail" : "";
                    return (
                        '<tr' + failCls + '>' +
                        '<td class="acr-td-no">' + (page + i + 1) + "</td>" +
                        '<td><b>' + esc(r.name) + '</b><br><span class="acr-uname">@' + esc(r.username) + "</span></td>" +
                        '<td class="acr-clip" title="' + esc(r.program) + '">' + esc(r.program) + "</td>" +
                        "<td>" + esc(r.group) + "</td>" +
                        '<td class="acr-num acr-strong">' + esc(r.credits_earned) + "</td>" +
                        '<td class="acr-num' + (r.fails > 0 ? " acr-bad" : "") + '">' + esc(r.fails) + "</td>" +
                        '<td class="acr-num' + (r.qb > 0 ? " acr-warn" : "") + '">' + esc(r.qb) + "</td>" +
                        '<td class="acr-num' + (r.exam25 > 0 ? " acr-warn" : "") + '">' + esc(r.exam25) + "</td>" +
                        '<td class="acr-num' + (r.ungraded > 0 ? " acr-muted" : "") + '">' + esc(r.ungraded) + "</td>" +
                        '<td class="acr-num">' + esc(r.gpa) + "</td>" +
                        '<td><button type="button" class="acr-view js-acr-view" data-sid="' + esc(r.student_id) +
                        '" data-name="' + esc(r.name) + '"><i class="fas fa-eye"></i> ' + esc(T.view) + "</button></td></tr>"
                    );
                })
                .join("");
            var total = d.total || 0;
            var from = total ? page + 1 : 0;
            var to = Math.min(page + LIMIT, total);
            pager.innerHTML =
                '<button class="js-acr-prev"' + (page > 0 ? "" : " disabled") + ">" + esc(T.prev) + "</button>" +
                "<span>" + from + "–" + to + " / " + total + "</span>" +
                '<button class="js-acr-next"' + (d.has_more ? "" : " disabled") + ">" + esc(T.next) + "</button>";
            var pv = pager.querySelector(".js-acr-prev");
            var nx = pager.querySelector(".js-acr-next");
            if (pv)
                pv.addEventListener("click", function () {
                    if (page > 0) {
                        page = Math.max(0, page - LIMIT);
                        load();
                    }
                });
            if (nx)
                nx.addEventListener("click", function () {
                    if (d.has_more) {
                        page += LIMIT;
                        load();
                    }
                });
            rows.querySelectorAll(".js-acr-view").forEach(function (btn) {
                btn.addEventListener("click", function () {
                    openDetail(btn.getAttribute("data-sid"), btn.getAttribute("data-name"));
                });
            });
        }

        function populateYears(years) {
            if (yearPopulated || !yearSel || !years || !years.length) return;
            yearPopulated = true;
            years.forEach(function (y) {
                var o = document.createElement("option");
                o.value = y;
                o.textContent = y;
                yearSel.appendChild(o);
            });
            if (typeof yearSel._refreshBootstrapSelect === "function") {
                yearSel._refreshBootstrapSelect();
            }
        }

        // Box-lar süzgəc sahəsinin TAMI üzrə aqreqatdır (cədvəl isə yalnız görünən
        // ~25 tələbə). Ona görə iki AYRI sorğu gedir: cədvəl dərhal gəlir, box-lar
        // öz skeleton-u ilə sonra dolur — cədvəl box-ları gözləmir.
        var summarySeq = 0;

        function cardSkeleton() {
            var html = "";
            for (var i = 0; i < 6; i++) {
                html += '<div class="acr-card acr-card--loading"><div class="acr-skel acr-skel--card"></div></div>';
            }
            cards.innerHTML = html;
        }

        function loadSummary() {
            var seq = ++summarySeq;
            cardSkeleton();
            fetch(U.summary + "?" + params().toString(), {
                headers: { "X-Requested-With": "XMLHttpRequest" },
            })
                .then(function (r) {
                    return r.ok ? r.json() : null;
                })
                .then(function (d) {
                    if (seq !== summarySeq) return; // köhnəlmiş cavab — süzgəc dəyişib
                    if (!d) {
                        cards.innerHTML = "";
                        return;
                    }
                    populateYears(d.year_options);
                    renderCards(d.summary);
                })
                .catch(function () {
                    if (seq === summarySeq) cards.innerHTML = "";
                });
        }

        var rowsSeq = 0;

        function load() {
            var seq = ++rowsSeq;
            skeleton();
            fetch(U.data + "?" + params({ offset: page, limit: LIMIT }).toString(), {
                headers: { "X-Requested-With": "XMLHttpRequest" },
            })
                .then(function (r) {
                    return r.ok ? r.json() : null;
                })
                .then(function (d) {
                    if (seq !== rowsSeq || !d) return;
                    renderRows(d);
                });
        }

        function reload() {
            page = 0;
            load();
            loadSummary();
        }

        [yearSel, seasonSel].forEach(function (sel) {
            if (sel) sel.addEventListener("change", reload);
        });

        // ── Tələbə detalı modalı ──────────────────────────────────────────────
        var modal = root.querySelector(".js-acr-modal");
        var modalTitle = root.querySelector(".js-acr-modal-title");
        var modalBody = root.querySelector(".js-acr-modal-body");

        function closeModal() {
            modal.hidden = true;
        }
        root.querySelectorAll(".js-acr-modal-close").forEach(function (el) {
            el.addEventListener("click", closeModal);
        });
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && !modal.hidden) closeModal();
        });

        function statusCell(row) {
            if (row.barred) return '<span class="acr-status is-barred">' + esc(T.barred) + "</span>";
            if (row.passed) return '<span class="acr-status is-pass">' + esc(T.passed) + "</span>";
            if (row.failed) return '<span class="acr-status is-fail">' + esc(T.failed) + "</span>";
            if (row.ungraded) return '<span class="acr-status is-ungraded">' + esc(T.ungraded) + "</span>";
            return '<span class="acr-status is-progress">' + esc(T.progress) + "</span>";
        }

        function ungradedBadge(row) {
            if (!row.ungraded) return "";
            return '<div class="acr-reason is-ungraded"><i class="fas fa-circle-question"></i> ' + esc(T.ungraded_badge) + "</div>";
        }

        function reasonBadge(row) {
            if (row.fail_reason === "qb")
                return '<div class="acr-reason is-qb"><i class="fas fa-user-clock"></i> ' + esc(T.qb_badge) + "</div>";
            if (row.fail_reason === "exam25")
                return '<div class="acr-reason is-exam"><i class="fas fa-file-circle-xmark"></i> ' + esc(T.exam25_badge) + "</div>";
            return "";
        }

        function renderDetail(d) {
            if (!d || d.has_access === false) {
                modalBody.innerHTML = '<div class="acr-state">' + esc(T.detail_error) + "</div>";
                return;
            }
            var sems = d.semesters || [];
            if (!sems.length) {
                modalBody.innerHTML = '<div class="acr-state"><i class="fas fa-folder-open"></i>' + esc(T.no_record) + "</div>";
                return;
            }
            modalBody.innerHTML = sems
                .map(function (sem) {
                    var head =
                        '<div class="acr-sem-head"><span class="acr-sem-title"><i class="fas fa-calendar-alt"></i> ' +
                        esc(sem.year) + " · " + esc(sem.season) + "</span>" +
                        '<span class="acr-sem-meta"><span class="acr-sem-credit"><i class="fas fa-award"></i> ' +
                        esc(sem.credits_earned) + " " + esc(T.sem_credit) + "</span>" +
                        (sem.gpa != null ? '<span class="acr-sem-gpa">' + esc(T.avg_gpa) + " " + esc(sem.gpa) + "</span>" : "") +
                        "</span></div>";
                    var body = (sem.rows || [])
                        .map(function (row) {
                            var cls = row.failed ? " acr-row--fail" : "";
                            return (
                                '<tr class="' + cls.trim() + '">' +
                                '<td class="acr-ta-left"><b>' + esc(row.code) + "</b><br><span class=\"acr-uname\">" + esc(row.name) + "</span>" +
                                reasonBadge(row) + ungradedBadge(row) + "</td>" +
                                '<td class="' + (row.ungraded ? "acr-muted" : "") + '">' + esc(row.credit) + "</td>" +
                                '<td class="acr-ta-left">' + esc(row.teacher) + "</td>" +
                                "<td>" + esc(row.entry == null ? "—" : row.entry) + "</td>" +
                                "<td>" + esc(row.exit == null ? "—" : row.exit) + "</td>" +
                                "<td>" + (row.total == null ? "—" : "<b>" + esc(row.total) + "</b>") + "</td>" +
                                "<td>" + (row.letter ? '<span class="grade-' + esc(row.letter) + ' acr-letter">' + esc(row.letter) + "</span>" : "—") + "</td>" +
                                "<td>" + statusCell(row) + "</td></tr>"
                            );
                        })
                        .join("");
                    return (
                        '<div class="acr-sem">' + head +
                        '<div class="acr-sem-tablewrap"><table class="acr-sem-table"><thead><tr>' +
                        '<th class="acr-ta-left">' + esc(T.subject) + "</th><th>" + esc(T.credit) + '</th><th class="acr-ta-left">' + esc(T.teacher) +
                        "</th><th>" + esc(T.entry) + "</th><th>" + esc(T.exit) + "</th><th>" + esc(T.total) + "</th><th>" + esc(T.grade) +
                        "</th><th>" + esc(T.status) + "</th></tr></thead><tbody>" + body + "</tbody></table></div></div>"
                    );
                })
                .join("");
        }

        function openDetail(sid, name) {
            modalTitle.textContent = name || "";
            modalBody.innerHTML = '<div class="acr-state"><i class="fas fa-spinner fa-spin"></i></div>';
            modal.hidden = false;
            fetch(U.detail + "?student=" + encodeURIComponent(sid), { headers: { "X-Requested-With": "XMLHttpRequest" } })
                .then(function (r) {
                    return r.ok ? r.json() : null;
                })
                .then(renderDetail);
        }

        root.querySelector(".js-acr-reset").addEventListener("click", function () {
            facultyPick.reset();
            deptPick.reset();
            programPick.reset();
            groupPick.reset();
            studentPick.reset();
            [yearSel, seasonSel].forEach(function (sel) {
                if (!sel) return;
                sel.value = "";
                if (typeof sel._refreshBootstrapSelect === "function") sel._refreshBootstrapSelect();
                else if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.sync === "function") {
                    window.EMSBootstrapSelect.sync(sel);
                }
            });
            reload();
        });

        load();
        loadSummary();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
