/* ═══════════════════════════════════════════════════════════════════════════
   programs_detail.js — «İxtisaslar» reyestrinin «Ətraflı» çekmecəsi

   Sahib (2026-09-09): «ixtisasın üzərinə vuranda ətraflı açıla bilər; açılan
   yerdə o ixtisasda aktiv oxuyan qrupları, qruplardan həmin ixtisasdakı
   tələbələri … görmək olsun».

   Panel SERVER-RENDER-lidir; burada YALNIZ çekmecənin məzmunu var və o, tək
   OXU son nöqtəsindən gəlir (`registrar:program_detail`). Yazma YOXDUR.

   AJAX-safe: `EMSDelegate` (swap-dan sonra da işləyir). Mətn HƏMİŞƏ
   `textContent` ilə yazılır — ad, qrup və tələbə adları istifadəçi
   məlumatıdır, `innerHTML` burada XSS qapısı olardı.
   ═══════════════════════════════════════════════════════════════════════════ */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    var DRAWER_ID = "pgdDetail";

    function core() {
        return window.EMSCore;
    }

    function body() {
        return document.querySelector("[data-pgd-body]");
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null) {
            node.textContent = String(text);
        }
        return node;
    }

    function stat(label, value, note) {
        var box = el("div", "pgd-stat");
        box.appendChild(el("span", "pgd-stat__label", label));
        box.appendChild(el("span", "pgd-stat__value", value));
        if (note) {
            box.appendChild(el("span", "pgd-stat__note", note));
        }
        return box;
    }

    function section(host, title, count) {
        var head = el("div", "pgd-sectionhead");
        head.appendChild(el("h3", "pgd-sectionhead__title", title));
        if (count !== undefined && count !== null) {
            head.appendChild(el("span", "pgd-sectionhead__count", count));
        }
        host.appendChild(head);
    }

    function renderGroups(host, program, t) {
        section(host, t.tGroups, program.groups.length);
        if (!program.groups.length) {
            host.appendChild(el("p", "pgd-empty", t.tNogroups));
            return;
        }
        var list = el("ul", "pgd-groups");
        program.groups.forEach(function (group) {
            var li = el("li", "pgd-group");
            li.appendChild(el("span", "pgd-group__name", group.name));
            li.appendChild(el("span", "pgd-group__count", group.students));
            list.appendChild(li);
        });
        host.appendChild(list);
    }

    function renderStatuses(host, program, t) {
        if (!program.statuses.length) {
            return;
        }
        section(host, t.tStatuses);
        var wrap = el("div", "pgd-chips");
        program.statuses.forEach(function (row) {
            var chip = el("span", "pgd-chip");
            chip.appendChild(el("span", "pgd-chip__label", row.label));
            chip.appendChild(el("span", "pgd-chip__count", row.total));
            wrap.appendChild(chip);
        });
        host.appendChild(wrap);
    }

    function renderStudents(host, program, t) {
        section(host, t.tStudents, program.students_total);
        if (!program.students.length) {
            host.appendChild(el("p", "pgd-empty", t.tNostudents));
            return;
        }
        var table = el("table", "pgd-table");
        var tbody = el("tbody");
        program.students.forEach(function (student) {
            var tr = el("tr");
            var name = el("td");
            name.appendChild(el("span", "pgd-student__name", student.name));
            name.appendChild(el("span", "pgd-student__login", "@" + student.username));
            tr.appendChild(name);
            tr.appendChild(el("td", "pgd-td-muted", student.group || "—"));
            tr.appendChild(el("td", "pgd-td-num", student.year));
            tr.appendChild(el("td", "pgd-td-muted", student.status_label));
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        host.appendChild(table);
        if (program.students_more > 0) {
            host.appendChild(el("p", "pgd-more", (t.tMore || "%s").replace("%s", program.students_more)));
        }
    }

    function render(program) {
        var host = body();
        if (!host) {
            return;
        }
        var t = host.dataset;
        host.textContent = "";

        var title = document.getElementById(DRAWER_ID + "-title");
        if (title) {
            title.textContent = program.name;
        }

        var meta = el("p", "pgd-meta");
        [program.official_code || "—", program.degree_label, program.form_label, program.unit]
            .filter(Boolean)
            .forEach(function (part, index) {
                if (index) {
                    meta.appendChild(el("span", "pgd-meta__dot", "·"));
                }
                meta.appendChild(el("span", null, part));
            });
        host.appendChild(meta);

        var stats = el("div", "pgd-stats");
        stats.appendChild(stat(t.tTotal, program.students_total, program.students_ungrouped
            ? t.tUngrouped + ": " + program.students_ungrouped
            : ""));
        stats.appendChild(stat(t.tPlan, program.plan_rows));
        stats.appendChild(stat(t.tOfferings, program.offerings, program.period));
        host.appendChild(stats);

        renderGroups(host, program, t);
        renderStatuses(host, program, t);
        renderStudents(host, program, t);
    }

    DELEGATE.on("click", "[data-pgd-open]", function (event, button) {
        event.preventDefault();
        var root = document.querySelector("[data-pgd-url]");
        var http = core();
        var host = body();
        if (!root || !http || !host || !window.EMSOverlay) {
            return;
        }
        host.textContent = "";
        host.appendChild(el("p", "pgd-empty", host.dataset.tLoading));
        window.EMSOverlay.open(DRAWER_ID);

        var url = root.getAttribute("data-pgd-url") + "?id=" + encodeURIComponent(button.getAttribute("data-pgd-open"));
        http.fetchJSON(url)
            .then(function (payload) {
                render(payload.program);
            })
            .catch(function () {
                host.textContent = "";
                host.appendChild(el("p", "pgd-empty", host.dataset.tError));
            });
    });
})(window, document);
