/* ═══════════════════════════════════════════════════════════════════════════
   Sillabus təsdiqi — BAXIŞ PANELİNİN render-i (dizayn təhvili §3.3)
   ───────────────────────────────────────────────────────────────────────────
   Mühərrik (`syllabus_review.js`) şəbəkə, vəziyyət və dialoqla məşğuldur; bu
   fayl YALNIZ JSON → DOM çevrilməsini edir. Bölünmə modul ölçüsü qaydasına
   (SOFT_CAP=600) görədir və sərhəd təmizdir: burada `fetch` YOXDUR.

   ⚠️ MƏTN BURADA YAZILMIR — bütün etiketlər şablondakı `json_script`
   blokundan (`#syl-review-texts`) gəlir; xarici `.js` Django template
   engine-dən keçmir.
   ⚠️ Məzmun HƏMİŞƏ `textContent` ilə yerləşdirilir (innerHTML YOX) — müəllimin
   yazdığı mətn HTML kimi şərh olunmur.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    "use strict";

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null) {
            node.textContent = text;
        }
        return node;
    }

    /* ── Bölmə kartları (hər birinə şərh sahəsi) ──────────────────────── */
    function sectionCard(section, texts, notes) {
        var note = notes[section.id] || section.note || "";
        var card = el("div", "syl-rvsec");
        if (section.changed) {
            card.classList.add("is-changed");
        }
        if (note.trim()) {
            card.classList.add("has-note");
        }
        card.setAttribute("data-syl-rv-section", section.id);

        var head = el("div", "syl-rvsec__head");
        head.appendChild(el("span", "syl-rvsec__title", section.label));
        if (section.changed) {
            head.appendChild(el("span", "syl-chip-static syl-chip-static--warning", texts.changed));
        }
        var badge = el("span", "syl-chip-static syl-chip-static--primary", texts.has_note);
        badge.setAttribute("data-syl-rv-notebadge", "");
        badge.hidden = !note.trim();
        head.appendChild(badge);

        var toggle = el("button", "syl-btn syl-btn--secondary syl-btn--sm", texts.add_note);
        toggle.type = "button";
        toggle.setAttribute("data-syl-rv-notetoggle", section.id);
        toggle.setAttribute("aria-expanded", "false");
        head.appendChild(toggle);
        card.appendChild(head);

        card.appendChild(el("div", "syl-rvsec__body", section.body));

        var box = el("div", "syl-rvsec__note");
        box.hidden = true;
        var inputId = "syl-rv-note-" + section.id;
        var label = el("label", null, texts.note_label);
        label.setAttribute("for", inputId);
        var area = el("textarea");
        area.id = inputId;
        area.rows = 2;
        area.value = note;
        area.placeholder = texts.note_placeholder;
        area.setAttribute("data-syl-rv-note", section.id);
        box.appendChild(label);
        box.appendChild(area);
        card.appendChild(box);
        return card;
    }

    /* ── Yanaşı fərq kartı ────────────────────────────────────────────── */
    function diffCard(row, texts) {
        var card = el("div", "syl-diff " + (row.changed ? "is-changed" : "is-same"));
        var head = el("div", "syl-diff__head");
        head.appendChild(el("span", "syl-diff__field", row.label));
        head.appendChild(el("span", "syl-diff__kind", row.kind));
        card.appendChild(head);

        var cols = el("div", "syl-diff__cols");
        [
            ["old", texts.old_column, row.old],
            ["new", texts.new_column, row.new]
        ].forEach(function (pair) {
            var col = el("div", "syl-diff__col syl-diff__col--" + pair[0]);
            col.appendChild(el("span", "syl-diff__label", pair[1]));
            col.appendChild(el("div", "syl-diff__text", pair[2]));
            cols.appendChild(col);
        });
        card.appendChild(cols);

        if (row.warning) {
            card.appendChild(el("div", "syl-diff__warning", row.warning));
        }
        return card;
    }

    /* ── Audit xronologiyası ──────────────────────────────────────────── */
    function timelineRow(event) {
        var row = el("li", "syl-timeline__row");
        var rail = el("div", "syl-timeline__rail");
        rail.appendChild(el("span", "syl-timeline__dot syl-timeline__dot--" + (event.tone || "neutral")));
        rail.appendChild(el("span", "syl-timeline__line"));
        row.appendChild(rail);

        var main = el("div", "syl-timeline__main");
        var head = el("div");
        head.appendChild(el("span", "syl-timeline__what", event.what));
        head.appendChild(el("span", "syl-timeline__when", event.when));
        main.appendChild(head);
        main.appendChild(el("span", "syl-timeline__who", event.who));
        if (event.body) {
            main.appendChild(el("div", "syl-timeline__body", event.body));
        }
        row.appendChild(main);
        return row;
    }

    function setText(root, selector, value) {
        var node = root.querySelector(selector);
        if (node) {
            node.textContent = value || "";
        }
    }

    function render(root, data, texts, notes) {
        setText(root, "[data-syl-rv-code]", data.code);
        setText(root, "[data-syl-rv-name]", data.name);
        setText(root, "[data-syl-rv-version]", data.version_label);
        setText(root, "[data-syl-rv-meta]", data.meta);
        setText(root, "[data-syl-rv-note]", data.teacher_note);
        setText(root, "[data-syl-rv-compare]", data.compare);

        var status = root.querySelector("[data-syl-rv-status]");
        if (status) {
            status.textContent = data.status_label || "";
            status.className = "syl-badge syl-badge--" + (data.status_tone || "neutral");
        }
        var wait = root.querySelector("[data-syl-rv-wait]");
        if (wait) {
            wait.textContent = data.wait_text || "";
            wait.className = "syl-wait syl-wait--" + (data.wait_tone || "muted");
        }

        var sections = root.querySelector("[data-syl-rv-pane='sections']");
        if (sections) {
            sections.textContent = "";
            (data.sections || []).forEach(function (section) {
                sections.appendChild(sectionCard(section, texts, notes));
            });
        }

        var count = root.querySelector("[data-syl-rv-diffcount]");
        var diffs = root.querySelector("[data-syl-rv-diffs]");
        if (diffs) {
            diffs.textContent = "";
            if (!data.has_base) {
                if (count) {
                    count.hidden = true;
                }
                diffs.appendChild(el("p", "syl-empty__body", texts.no_diff));
            } else {
                if (count) {
                    count.hidden = false;
                    count.textContent = (data.diff && data.diff.count) || "";
                }
                ((data.diff && data.diff.rows) || []).forEach(function (row) {
                    diffs.appendChild(diffCard(row, texts));
                });
            }
        }

        var timeline = root.querySelector("[data-syl-rv-timeline]");
        if (timeline) {
            timeline.textContent = "";
            (data.timeline || []).forEach(function (event) {
                timeline.appendChild(timelineRow(event));
            });
        }
        paintFoot(root, texts);
    }

    /* ── Şərh sayğacı (altlıqdakı izah sətri) ─────────────────────────── */
    function collectNotes(root) {
        var notes = {};
        root.querySelectorAll("[data-syl-rv-note]").forEach(function (node) {
            var value = (node.value || "").trim();
            if (value) {
                notes[node.getAttribute("data-syl-rv-note")] = value;
            }
        });
        return notes;
    }

    function paintFoot(root, texts) {
        var foot = root.querySelector("[data-syl-rv-foot]");
        if (!foot) {
            return;
        }
        var count = Object.keys(collectNotes(root)).length;
        foot.textContent = (texts.foot || "").replace("%(count)s", count);
    }

    /* ── Bölmə siyahısı — «düzəliş tələb olunan bölmələr» çipləri ─────── */
    function sectionChoices(root) {
        var rows = [];
        root.querySelectorAll("[data-syl-rv-section]").forEach(function (node) {
            var title = node.querySelector(".syl-rvsec__title");
            rows.push({
                id: node.getAttribute("data-syl-rv-section"),
                label: title ? title.textContent : ""
            });
        });
        return rows;
    }

    window.EMSSyllabusReviewPanel = {
        render: render,
        collectNotes: collectNotes,
        paintFoot: paintFoot,
        sectionChoices: sectionChoices,
        el: el
    };
})();
