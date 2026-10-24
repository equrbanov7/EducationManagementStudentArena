/* «Sillabusa bax» paneli — müəllim jurnalı VƏ tələbə kabineti üçün ORTAQ.
 *
 * AJAX-safe: bütün klik-lər `EMSDelegate.on` ilə `document`-ə delegasiya olunur,
 * ona görə tələbə kabinetinin bölmə swap-ından sonra da işləyir (jurnal isə tam
 * səhifədir). `document`/`window` listener-ləri `EMSReady.once` ilə YALNIZ BİR
 * DƏFƏ qoşulur — təkrar swap-da yığılmır.
 *
 * Dinamik dəyər şablondan `data-*` atributları ilə gəlir (CSP: xarici fayl
 * Django template engine-dən keçmir).
 */
(function () {
    "use strict";

    if (!window.EMSDelegate || !window.EMSReady) {
        return;
    }

    var lastTrigger = null;

    function panel() {
        return document.querySelector("[data-sylv]");
    }

    function q(root, name) {
        return root ? root.querySelector("[data-sylv-" + name + "]") : null;
    }

    function setText(root, name, value) {
        var node = q(root, name);
        if (node) {
            node.textContent = value || "";
        }
    }

    function show(node, visible) {
        if (node) {
            node.hidden = !visible;
        }
    }

    function renderBlocks(root, blocks) {
        var host = q(root, "blocks");
        if (!host) {
            return;
        }
        host.textContent = "";
        (blocks || []).forEach(function (block) {
            var section = document.createElement("section");
            section.className = "sylv-block";
            var title = document.createElement("h4");
            title.className = "sylv-block__title";
            title.textContent = block.title || "";
            var body = document.createElement("p");
            body.className = "sylv-block__body";
            // textContent — server mətni HTML kimi şərh olunmur (XSS qapısı).
            body.textContent = block.body || "";
            section.appendChild(title);
            section.appendChild(body);
            host.appendChild(section);
        });
    }

    /* Həftəlik plan ↔ jurnal (sahib 2026-10-25): hər sətir «Keçilib» + tarix(lər) / «Keçilməyib». */
    function renderProgress(root, progress) {
        var box = q(root, "progress");
        if (!box) {
            return;
        }
        var list = q(box, "progress-list");
        var rows = (progress && progress.rows) || [];
        if (list) {
            list.textContent = "";
        }
        show(box, rows.length > 0);
        if (!rows.length || !list) {
            return;
        }
        var summary = box.getAttribute("data-label-summary") || "";
        setText(
            box,
            "progress-summary",
            summary.replace("{covered}", String(progress.covered || 0)).replace("{total}", String(progress.total || 0))
        );
        rows.forEach(function (row) {
            var state = row.covered ? "covered" : row.planned ? "planned" : "pending";
            var item = document.createElement("li");
            item.className = "sylv-progress__row is-" + state;
            var num = document.createElement("span");
            num.className = "sylv-progress__num";
            num.textContent = String(row.week) + ".";
            var title = document.createElement("span");
            title.className = "sylv-progress__title";
            title.textContent = row.title || "—";
            var badge = document.createElement("span");
            badge.className = "sylv-progress__badge";
            badge.textContent = box.getAttribute("data-label-" + state) || "";
            var dates = row.covered ? row.dates : row.upcoming;
            if (dates && dates.length) {
                badge.textContent += " · " + dates.join(", ");
            }
            item.appendChild(num);
            item.appendChild(title);
            item.appendChild(badge);
            list.appendChild(item);
        });
    }

    function render(root, data) {
        setText(root, "code", data.code);
        setText(root, "name", data.name || data.subject);
        setText(root, "version", data.version);
        var badge = q(root, "status");
        if (badge) {
            badge.textContent = data.status_label || "";
            badge.setAttribute("data-tone", data.status || "");
        }
        var meta = [data.program, data.period, data.author].filter(Boolean).join(" · ");
        if (data.approved_at) {
            meta = meta ? meta + " · " + data.approved_at : data.approved_at;
        }
        /* Bağlı sillabus (2026-10-08): «Təsdiq: <qrup> sillabusundan …» — server mətni. */
        if (data.approval_note) {
            meta = meta ? meta + " · " + data.approval_note : data.approval_note;
        }
        setText(root, "meta", meta);

        var note = q(root, "note");
        if (note) {
            note.textContent = data.student_note || "";
            show(note, Boolean(data.student_note));
        }
        var pdf = q(root, "pdf");
        if (pdf) {
            if (data.pdf_url) {
                pdf.setAttribute("href", data.pdf_url);
            }
            show(pdf, Boolean(data.pdf_url));
        }
        renderBlocks(root, data.blocks);
        renderProgress(root, data.week_progress);
    }

    function open(url, trigger) {
        var root = panel();
        if (!root || !url) {
            return;
        }
        lastTrigger = trigger || null;
        root.hidden = false;
        document.body.classList.add("sylv-open");
        show(q(root, "loading"), true);
        show(q(root, "error"), false);
        renderBlocks(root, []);
        renderProgress(root, null);

        var box = root.querySelector(".sylv__panel");
        if (box) {
            box.focus();
        }

        var request =
            window.EMSCore && window.EMSCore.fetchJSON
                ? window.EMSCore.fetchJSON(url, { method: "GET" })
                : fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } }).then(function (response) {
                      return response.json();
                  });

        request
            .then(function (data) {
                show(q(root, "loading"), false);
                if (!data || data.ok !== true) {
                    show(q(root, "error"), true);
                    return;
                }
                render(root, data);
            })
            .catch(function () {
                show(q(root, "loading"), false);
                show(q(root, "error"), true);
            });
    }

    function close() {
        var root = panel();
        if (!root || root.hidden) {
            return;
        }
        root.hidden = true;
        document.body.classList.remove("sylv-open");
        if (lastTrigger && document.contains(lastTrigger)) {
            lastTrigger.focus();
        }
        lastTrigger = null;
    }

    window.EMSDelegate.on("click", "[data-sylv-open]", function (event, button) {
        event.preventDefault();
        open(button.getAttribute("data-sylv-open") || button.getAttribute("href"), button);
    });

    window.EMSDelegate.on("click", "[data-sylv-close]", function (event) {
        event.preventDefault();
        close();
    });

    window.EMSReady.once("sylv-esc", function () {
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                close();
            }
        });
    });
})();
