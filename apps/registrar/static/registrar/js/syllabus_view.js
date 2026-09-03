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
