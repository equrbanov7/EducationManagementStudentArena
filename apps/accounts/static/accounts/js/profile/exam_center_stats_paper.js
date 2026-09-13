/*
 * exam_center_stats_paper.js — İmtahan statistikaları: KAĞIZ (yazılı / praktiki)
 * imtahan KPI-ları (2026-09-14, W2 `w2paper`, addendum).
 *
 * Boot skripti (`exam_center_stats_boot.js`) hər yükləmədə `ecs:filters`
 * hadisəsini (detail.query = cari filtr sətri) göndərir; bura həmin sətrə
 * `paper=1` (+ seçilmiş `paper_kind`) əlavə edib eyni data endpoint-inə gedir —
 * cəhd cədvəli yenidən yüklənmir. Çip klikində yalnız bu blok yenilənir.
 * CSP: inline yoxdur; etiketlər `data-label-*` atributlarından. AJAX-safe:
 * `EMSReady` + `EMSDelegate` (açar `click|[data-ecs-paper-kind]` yalnız bu faylda).
 */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    function root() {
        return document.querySelector("[data-ecs-paper]");
    }

    function label(host, key) {
        return host.getAttribute("data-label-" + key) || "";
    }

    function dataUrl(host) {
        var ecs = host.closest(".ecs");
        return ecs ? ecs.getAttribute("data-data-url") || "" : "";
    }

    function card(value, text) {
        var box = document.createElement("div");
        box.className = "ecs-card";
        var n = document.createElement("div");
        n.className = "ecs-card__n";
        n.textContent = value === null || value === undefined ? "—" : String(value);
        var l = document.createElement("div");
        l.className = "ecs-card__l";
        l.textContent = text;
        box.appendChild(n);
        box.appendChild(l);
        return box;
    }

    function chip(host, value, text) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "ems-chip";
        btn.setAttribute("data-ecs-paper-kind", value);
        btn.setAttribute("aria-pressed", (host.getAttribute("data-kind") || "") === value ? "true" : "false");
        btn.textContent = text;
        return btn;
    }

    function render(host, rows) {
        var chips = host.querySelector("[data-ecs-paper-chips]");
        var cards = host.querySelector("[data-ecs-paper-cards]");
        if (!chips || !cards) {
            return;
        }
        chips.textContent = "";
        chips.appendChild(chip(host, "", label(host, "all")));
        (host.paperKinds || []).forEach(function (kind) {
            chips.appendChild(chip(host, kind.kind, kind.label));
        });
        cards.textContent = "";
        if (!rows.length) {
            cards.appendChild(card("—", label(host, "empty")));
            return;
        }
        rows.forEach(function (row) {
            cards.appendChild(card(row.sheets, row.label + " · " + label(host, "sheets")));
            cards.appendChild(card(row.entries, row.label + " · " + label(host, "entries")));
            cards.appendChild(card(row.changes, row.label + " · " + label(host, "changes")));
            cards.appendChild(card(row.avg, row.label + " · " + label(host, "avg")));
        });
    }

    function load(host) {
        var url = dataUrl(host);
        if (!url) {
            return;
        }
        var query = host.getAttribute("data-query") || "";
        var params = new URLSearchParams(query);
        params.set("paper", "1");
        params.set("page", "1");
        var kind = host.getAttribute("data-kind") || "";
        if (kind) {
            params.set("paper_kind", kind);
        } else {
            params.delete("paper_kind");
        }
        fetch(url + "?" + params.toString(), { headers: { "X-Requested-With": "XMLHttpRequest" } })
            .then(function (response) {
                return response.ok ? response.json() : null;
            })
            .then(function (data) {
                if (!data || !host.isConnected) {
                    return;
                }
                var rows = data.paper || [];
                if (!kind) {
                    // Çip siyahısı bütün növlərdən qurulur (filtrsiz cavab hamısını verir).
                    host.paperKinds = rows.map(function (row) {
                        return { kind: row.kind, label: row.label };
                    });
                }
                render(host, rows);
            })
            .catch(function () {
                render(host, []);
            });
    }

    document.addEventListener("ecs:filters", function (event) {
        var host = root();
        if (!host) {
            return;
        }
        host.setAttribute("data-query", (event.detail && event.detail.query) || "");
        load(host);
    });

    DELEGATE.on("click", "[data-ecs-paper-kind]", function (event, btn) {
        event.preventDefault();
        var host = root();
        if (!host) {
            return;
        }
        host.setAttribute("data-kind", btn.getAttribute("data-ecs-paper-kind") || "");
        load(host);
    });

    window.EMSReady(function () {
        var host = root();
        if (host && !host.getAttribute("data-query")) {
            host.setAttribute("data-query", "");
            load(host);
        }
    });
})(window, document);
