/* ═══════════════════════════════════════════════════════════════════════════
   unit_exams.js — «Bölmə imtahanları» (dekan / kafedra müdiri, OXU-ONLY)

   * İmtahanın adına klik → «İmtahan haqqında» çekmecəsi. Məzmun serverə yeni
     sorğu GÖNDƏRMƏDƏN cari səhifənin `#ueRowsData` JSON blokundan gəlir.
   * KPI kartı (AKTİV / BİTMİŞ) → «Status» filtri: seçicini dəyişib filtr
     panelinin öz avto-göndəriş axınını işə salırıq (server tərəfli filtr).
   * Axtarış / select / tarix — ortaq `filter_bar.js` (+ EMSSearchInput, 1500 ms).

   AJAX-safe: dinləyicilər `EMSDelegate` / document səviyyəsində BİR DƏFƏ
   qoşulur (skript hər swap-da yenidən icra olunsa belə); DOM hər klikdə
   yenidən oxunur. Mətn HƏMİŞƏ `textContent` ilə yazılır (XSS qapısı yoxdur).
   ═══════════════════════════════════════════════════════════════════════════ */
(function (window, document) {
    "use strict";

    if (window.__emsUnitExamsBound) {
        return;
    }
    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }
    window.__emsUnitExamsBound = true;

    var DRAWER_ID = "ueDetail";
    var PANEL = '[data-profile-section-panel="unit-exams"]';

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null && text !== "") {
            node.textContent = String(text);
        }
        return node;
    }

    function rows() {
        var blob = document.getElementById("ueRowsData");
        if (!blob) {
            return [];
        }
        try {
            return JSON.parse(blob.textContent || "[]") || [];
        } catch (err) {
            return [];
        }
    }

    function findRow(id) {
        var list = rows();
        for (var i = 0; i < list.length; i += 1) {
            if (String(list[i].id) === String(id)) {
                return list[i];
            }
        }
        return null;
    }

    function heading(host, text, count) {
        var head = el("div", "ue-detail__head");
        head.appendChild(el("h3", "ue-detail__heading", text));
        if (count !== undefined && count !== null) {
            head.appendChild(el("span", "ue-detail__count", count));
        }
        host.appendChild(head);
    }

    function facts(host, pairs) {
        var list = el("dl", "ue-facts");
        pairs.forEach(function (pair) {
            if (!pair[1] && pair[1] !== 0) {
                return;
            }
            var item = el("div", "ue-facts__item");
            item.appendChild(el("dt", "ue-facts__label", pair[0]));
            item.appendChild(el("dd", "ue-facts__value", pair[1]));
            list.appendChild(item);
        });
        if (list.childNodes.length) {
            host.appendChild(list);
        }
    }

    function stat(label, value) {
        var box = el("div", "ue-stat");
        box.appendChild(el("span", "ue-stat__label", label));
        box.appendChild(el("span", "ue-stat__value", value === "" || value === null ? "—" : value));
        return box;
    }

    function render(host, row) {
        var t = host.dataset;
        host.textContent = "";

        var title = document.getElementById(DRAWER_ID + "-title");
        if (title) {
            title.textContent = row.title;
        }

        var meta = el("p", "ue-detail__meta");
        var badge = el("span", "ems-badge ems-badge--" + (row.status_tone || "neutral"));
        badge.appendChild(el("span", "ems-badge__dot"));
        badge.lastChild.setAttribute("aria-hidden", "true");
        badge.appendChild(document.createTextNode(row.status || ""));
        meta.appendChild(badge);
        [row.kind, row.form, row.mode].filter(Boolean).forEach(function (part) {
            meta.appendChild(el("span", "ue-detail__dot", "·"));
            meta.appendChild(el("span", null, part));
        });
        host.appendChild(meta);

        facts(host, [
            [t.tSubject, row.subject],
            [t.tChair, row.chair],
            [t.tCourse, row.course],
            [t.tAuthor, row.author]
        ]);

        heading(host, t.tSchedule);
        var minutes = row.duration ? (t.tMinutes || "{n}").replace("{n}", row.duration) : t.tNolimit;
        facts(host, [
            [t.tStart, row.start || "—"],
            [t.tEnd, row.end || "—"],
            [t.tDuration, minutes],
            [t.tCreated, row.created]
        ]);

        heading(host, t.tGroups, (row.groups || []).length);
        if (row.groups && row.groups.length) {
            var chips = el("div", "ue-groups ue-groups--wrap");
            row.groups.forEach(function (name) {
                chips.appendChild(el("span", "ue-chip", name));
            });
            host.appendChild(chips);
        } else {
            host.appendChild(el("p", "ue-detail__empty", t.tNogroups));
        }

        heading(host, t.tResults);
        var stats = el("div", "ue-stats");
        stats.appendChild(stat(t.tQuestions, row.questions));
        stats.appendChild(stat(t.tParticipants, row.participants));
        stats.appendChild(stat(t.tFinished, row.finished));
        stats.appendChild(stat(t.tAttempts, row.attempts));
        stats.appendChild(stat(t.tAvg, row.avg));
        stats.appendChild(stat(t.tPass, row.pass_rate));
        host.appendChild(stats);
        if (!row.attempts) {
            host.appendChild(el("p", "ue-detail__empty", t.tNoresults));
        } else if (row.hidden_small) {
            host.appendChild(el("p", "ue-detail__note", t.tSmall));
        }
        host.appendChild(el("p", "ue-detail__note", t.tReadonly));

        if (row.detail_url || row.results_url) {
            var links = el("div", "ue-detail__links");
            if (row.detail_url) {
                var open = el("a", "ems-btn", t.tOpen);
                open.href = row.detail_url;
                links.appendChild(open);
            }
            if (row.results_url) {
                var res = el("a", "ems-btn", t.tOpenresults);
                res.href = row.results_url;
                links.appendChild(res);
            }
            host.appendChild(links);
        }
    }

    DELEGATE.on("click", "[data-ue-open]", function (event, button) {
        event.preventDefault();
        var host = document.querySelector("[data-ue-body]");
        if (!host || !window.EMSOverlay) {
            return;
        }
        var row = findRow(button.getAttribute("data-ue-open"));
        if (row) {
            render(host, row);
        } else {
            host.textContent = "";
            host.appendChild(el("p", "ue-detail__empty", host.dataset.tMissing));
        }
        window.EMSOverlay.open(DRAWER_ID);
    });

    // KPI kartı → «Status» filtri (nav.js `ems:kpi-filter` yayır; təkrar klik = sıfırla).
    document.addEventListener("ems:kpi-filter", function (event) {
        var target = event.target;
        var panel = target && target.closest ? target.closest(PANEL) : null;
        if (!panel) {
            return;
        }
        var raw = (event.detail && event.detail.filter) || "";
        var select = panel.querySelector('select[name="ue_status"]');
        if (!select) {
            return;
        }
        var value = raw.indexOf("status:") === 0 ? raw.slice(7) : "";
        if (select.value === value) {
            return;
        }
        select.value = value;
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
            window.EMSBootstrapSelect.refresh(select);
        }
        select.dispatchEvent(new Event("change", { bubbles: true }));
    });
})(window, document);
