/* ═══════════════════════════════════════════════════════════════════════════
   Sillabus redaktoru — BÖLMƏ SAHƏLƏRİ (dizayn təhvili §3.2)
   ───────────────────────────────────────────────────────────────────────────
   Bu modul iki iş görür və başqa heç nə:

     1. `collect(el, sectionId)` — bölmənin DOM-unu autosave gövdəsinə çevirir.
        Nəticə `apps/syllabus/services/drafts.BLANK_SECTION_DATA` sxemi ilə
        EYNİ olmalıdır — server sahə adlarını burada gözləyir.
     2. `refresh(el)` — yalnız TÖRƏMƏ göstəriciləri yeniləyir (simvol sayğacı,
        saat çipləri, aralıq/layihə balı). Biznes qərarı VERMİR: tamamlanma
        faizi və çatışmazlıq siyahısı yeganə mənbədən — serverin autosave
        cavabından — gəlir.

   Niyə ayrı fayl: `syllabus_editor.js` autosave mühərriki və naviqasiyadır;
   sahə sxemi isə domenlə birlikdə dəyişir. Modul ölçüsü qaydası (SOFT_CAP=600)
   da bu bölgünü tələb edir.

   Mətn YOXDUR — bütün etiketlər şablondakı `data-t-*` atributlarından oxunur.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    "use strict";

    /* Dərs növləri — `apps.syllabus.constants.LESSON_HOUR_KINDS` ilə eynidir. */
    var HOUR_KINDS = ["lecture", "seminar", "lab"];

    function panel(el, id) {
        return el ? el.querySelector("[data-syl-panel='" + id + "']") : null;
    }

    function text(node) {
        return node ? String(node.value == null ? "" : node.value) : "";
    }

    function int(value) {
        var parsed = parseInt(value, 10);
        return isNaN(parsed) ? 0 : parsed;
    }

    /* Sətir-əsaslı sahə (ədəbiyyat): boş sətirlər atılır. */
    function toLines(value) {
        return String(value || "")
            .split("\n")
            .map(function (line) {
                return line.trim();
            })
            .filter(function (line) {
                return line.length > 0;
            });
    }

    /* `data-field` atributu olan hər input → {ad: dəyər}. */
    function plainFields(box) {
        var out = {};
        if (!box) {
            return out;
        }
        box.querySelectorAll("[data-field]").forEach(function (node) {
            out[node.getAttribute("data-field")] = text(node);
        });
        return out;
    }

    /* ── Bölmə-bölmə toplayıcılar ─────────────────────────────────────── */

    function collectInfo(box) {
        var data = plainFields(box);
        return {
            teacher: data.teacher || "",
            office_hours: data.office_hours || "",
            prerequisites: data.prerequisites || ""
        };
    }

    function collectDesc(box) {
        var data = plainFields(box);
        return { description: data.description || "", goal: data.goal || "" };
    }

    function collectOut(box) {
        var outcomes = [];
        if (box) {
            box.querySelectorAll("[data-outcome]").forEach(function (node) {
                outcomes.push(text(node).trim());
            });
        }
        return { outcomes: outcomes };
    }

    function collectWeek(box) {
        var rows = [];
        if (!box) {
            return { rows: rows };
        }
        box.querySelectorAll("[data-syl-week-row]").forEach(function (tr) {
            var row = { topic: "", outcome: "" };
            var topic = tr.querySelector("[data-week='topic']");
            var outcome = tr.querySelector("[data-week='outcome']");
            row.topic = text(topic).trim();
            row.outcome = text(outcome).trim();
            HOUR_KINDS.forEach(function (kind) {
                row[kind] = int(text(tr.querySelector("[data-week='" + kind + "']")));
            });
            rows.push(row);
        });
        return { rows: rows };
    }

    function collectMethod(box) {
        var methods = [];
        if (box) {
            box.querySelectorAll("[data-syl-method].is-on").forEach(function (node) {
                methods.push(node.getAttribute("data-syl-method"));
            });
        }
        return { methods: methods, note: plainFields(box).note || "" };
    }

    /* Qiymətləndirmə: yalnız `midterm` sürüşdürülür — `project` ONDAN törəyir
       (cəm universitet siyasəti ilə sabitdir), ona görə burada hesablanır. */
    function collectAssess(box) {
        var slider = box ? box.querySelector("[data-syl-midterm]") : null;
        var flex = slider ? int(slider.getAttribute("data-flex")) : 0;
        var midterm = slider ? int(slider.value) : 0;
        return {
            midterm: midterm,
            project: Math.max(0, flex - midterm),
            note: plainFields(box).note || ""
        };
    }

    /* Sərbəst iş: qiyməti OLAN tapşırığın `graded`/`graded_count` sahələri
       olduğu kimi geri yazılır — əks halda arxivləmə qadağası pozulardı. */
    function collectSelf(box) {
        var active = box ? box.querySelector("[data-syl-selfwork].is-on") : null;
        var topics = [];
        var archived = [];
        if (box) {
            box.querySelectorAll("[data-syl-slot]").forEach(function (slot) {
                topics.push({
                    title: text(slot.querySelector("[data-selfwork-title]")).trim(),
                    graded: slot.getAttribute("data-graded") === "1",
                    graded_count: int(slot.getAttribute("data-graded-count"))
                });
            });
            box.querySelectorAll("[data-syl-archived-row]").forEach(function (row) {
                archived.push({
                    title: row.getAttribute("data-title") || "",
                    note: row.getAttribute("data-note") || ""
                });
            });
        }
        return {
            option: active ? active.getAttribute("data-syl-selfwork") : "",
            topics: topics,
            archived: archived
        };
    }

    function collectLit(box) {
        var out = { primary: [], additional: [] };
        if (!box) {
            return out;
        }
        box.querySelectorAll("[data-field-lines]").forEach(function (node) {
            out[node.getAttribute("data-field-lines")] = toLines(text(node));
        });
        return out;
    }

    var COLLECTORS = {
        info: collectInfo,
        desc: collectDesc,
        out: collectOut,
        week: collectWeek,
        method: collectMethod,
        assess: collectAssess,
        self: collectSelf,
        lit: collectLit
    };

    /* `prev` / `send` qayda bölməsi deyil — məzmunu yoxdur, saxlanılmır. */
    function collect(el, sectionId) {
        var fn = COLLECTORS[sectionId];
        return fn ? fn(panel(el, sectionId), el) : null;
    }

    /* Hansı bölmənin sahəsi dəyişdi — autosave hədəfini tapmaq üçün. */
    function sectionOf(node) {
        var box = node && node.closest ? node.closest("[data-syl-panel]") : null;
        return box ? box.getAttribute("data-syl-panel") : null;
    }

    /* ── Törəmə göstəricilər (yalnız görüntü) ─────────────────────────── */

    function i18n(el, key) {
        var box = el ? el.querySelector("[data-syl-i18n]") : null;
        return (box && box.getAttribute("data-t-" + key)) || "";
    }

    /* «Ən azı %(min)s simvol — hazırda %(have)s» şablonunu doldurur. */
    function charNote(el, have, min) {
        if (have >= min) {
            return have + " " + i18n(el, "chars");
        }
        return i18n(el, "chars-min")
            .replace("%(min)s", String(min))
            .replace("%(have)s", String(have));
    }

    function refreshCounters(el) {
        el.querySelectorAll("[data-syl-counter]").forEach(function (note) {
            var input = document.getElementById(note.getAttribute("data-syl-counter"));
            if (!input) {
                return;
            }
            var min = int(input.getAttribute("data-min"));
            var have = text(input).trim().length;
            note.textContent = charNote(el, have, min);
            note.classList.toggle("is-bad", have < min);
            input.classList.toggle("is-bad", have < min);
        });
    }

    /* Saat çipləri: hər dərs növü tədris planı ilə AYRICA uyğunlaşmalıdır. */
    function refreshHours(el) {
        var box = panel(el, "week");
        var hours = el.querySelector("[data-syl-hours]");
        if (!box || !hours) {
            return;
        }
        var rows = collectWeek(box).rows;
        var allOk = true;
        HOUR_KINDS.forEach(function (kind) {
            var chip = hours.querySelector("[data-syl-hour-chip='" + kind + "']");
            if (!chip) {
                return;
            }
            var have = rows.reduce(function (sum, row) {
                return sum + row[kind];
            }, 0);
            var planNode = chip.querySelector("[data-syl-hour-plan]");
            var haveNode = chip.querySelector("[data-syl-hour-have]");
            var planned = planNode ? int(planNode.textContent) : 0;
            if (haveNode) {
                haveNode.textContent = String(have);
            }
            var bad = have !== planned;
            chip.classList.toggle("is-bad", bad);
            if (bad) {
                allOk = false;
            }
        });
        hours.classList.toggle("syl-hours--ok", allOk);
        hours.classList.toggle("syl-hours--warn", !allOk);
        var note = hours.querySelector("[data-syl-hours-note]");
        if (note) {
            note.textContent = note.getAttribute(allOk ? "data-t-ok" : "data-t-warn") || "";
        }
    }

    /* Aralıq imtahan sürüşdürüləndə semestr layihəsi əks istiqamətdə dəyişir. */
    function refreshMidterm(el) {
        var slider = el.querySelector("[data-syl-midterm]");
        if (!slider) {
            return;
        }
        var flex = int(slider.getAttribute("data-flex"));
        var midterm = int(slider.value);
        var midNode = el.querySelector("[data-syl-midterm-value]");
        var projNode = el.querySelector("[data-syl-project-value]");
        if (midNode) {
            midNode.textContent = String(midterm);
        }
        if (projNode) {
            projNode.textContent = String(Math.max(0, flex - midterm));
        }
    }

    /* TN etiketləri sıra nömrəsindən asılıdır — silinmədən sonra yenilənir. */
    function retagOutcomes(el) {
        var box = panel(el, "out");
        if (!box) {
            return;
        }
        var label = box.querySelector("[data-syl-outcomes]");
        var suffix = label ? label.getAttribute("data-t-label") : "";
        var removeText = label ? label.getAttribute("data-t-remove") : "";
        box.querySelectorAll("[data-syl-outcome]").forEach(function (row, index) {
            var tag = "TN" + (index + 1);
            var tagNode = row.querySelector("[data-syl-outcome-tag]");
            var input = row.querySelector("[data-outcome]");
            var remove = row.querySelector("[data-syl-outcome-remove]");
            if (tagNode) {
                tagNode.textContent = tag;
            }
            if (input) {
                input.setAttribute("aria-label", tag + " — " + suffix);
            }
            if (remove) {
                remove.setAttribute("aria-label", tag + " " + removeText);
            }
        });
    }

    function refresh(el) {
        if (!el) {
            return;
        }
        refreshCounters(el);
        refreshHours(el);
        refreshMidterm(el);
        retagOutcomes(el);
    }

    /* ── Server vəziyyətinin render-i ─────────────────────────────────── */

    /* dizayn §3.2 `saveState` — altı vəziyyət, hər biri üçün çip + banner. */
    var SAVE_STATES = ["saving", "saved", "failed", "offline", "conflict", "stale"];

    function paintSaveState(el, state, suffix) {
        if (!el) {
            return;
        }
        var chip = el.querySelector("[data-syl-save]");
        if (chip) {
            SAVE_STATES.forEach(function (name) {
                chip.classList.toggle("syl-save--" + name, name === state);
            });
            var label = chip.querySelector("[data-syl-save-text]");
            if (label) {
                var base = chip.getAttribute("data-t-" + state) || "";
                label.textContent = suffix ? base + " — " + suffix : base;
            }
        }
        /* Eyni anda yalnız bir banner görünür; `saving`/`saved` bannersizdir. */
        el.querySelectorAll("[data-syl-banner]").forEach(function (banner) {
            banner.hidden = banner.getAttribute("data-syl-banner") !== state;
        });
        var retry = el.querySelector(".syl-savebox [data-syl-retry]");
        if (retry) {
            retry.hidden = state !== "failed";
        }
        el.setAttribute("data-save-state", state);
    }

    /* Tamamlanma hesabatı SERVERDƏN gəlir (`apps.syllabus.completion`) — burada
       yalnız çəkilir, yenidən hesablanmır. */
    function paintCompletion(el, report, readonly) {
        if (!el || !report) {
            return;
        }
        var sections = report.sections || {};
        var percent = Math.max(0, Math.min(int(report.percent), 100));
        var tone = percent >= 100 ? "success" : "primary";

        var fill = el.querySelector("[data-syl-progress-fill]");
        if (fill) {
            fill.style.width = percent + "%";
            fill.setAttribute("data-syl-percent", String(percent));
        }
        var value = el.querySelector("[data-syl-progress-value]");
        if (value) {
            value.textContent = percent + "%";
            value.className = "syl-bar__value syl-bar__value--" + tone;
        }
        var bar = el.querySelector(".syl-bar");
        if (bar) {
            bar.className = "syl-bar syl-bar--" + tone;
        }

        /* Bölmə başına çatışmazlıq sayı — sol naviqasiyanın «N xəta» rozetkası. */
        var counts = {};
        (report.issues || []).forEach(function (issue) {
            counts[issue.section] = (counts[issue.section] || 0) + 1;
        });

        el.querySelectorAll(".syl-step[data-syl-step]").forEach(function (button) {
            var id = button.getAttribute("data-syl-step");
            if (!(id in sections)) {
                return;
            }
            var done = !!sections[id];
            button.classList.toggle("syl-step--done", done);
            button.classList.toggle("syl-step--error", !done);
            button.classList.remove("syl-step--todo");
            var mark = button.querySelector(".syl-step__mark");
            if (mark) {
                mark.textContent = done ? "✓" : "!";
            }
            var warn = button.querySelector(".syl-step__warn");
            if (warn) {
                warn.hidden = !counts[id];
            }
        });

        /* Panel başlığındakı «tamamlanıb / çatışan tələblər var» rozetkası. */
        Object.keys(sections).forEach(function (id) {
            var state = el.querySelector("[data-syl-panel='" + id + "'] .syl-panel__state");
            if (state && !state.classList.contains("syl-panel__state--check")) {
                state.classList.toggle("syl-panel__state--done", !!sections[id]);
                state.classList.toggle("syl-panel__state--todo", !sections[id]);
            }
        });

        var canSubmit = percent >= 100 && !readonly;
        el.querySelectorAll("[data-syl-submit]").forEach(function (button) {
            button.disabled = !canSubmit;
        });
    }

    window.EMSSyllabusFields = {
        HOUR_KINDS: HOUR_KINDS,
        collect: collect,
        i18n: i18n,
        paintCompletion: paintCompletion,
        paintSaveState: paintSaveState,
        panel: panel,
        refresh: refresh,
        retagOutcomes: retagOutcomes,
        sectionOf: sectionOf
    };
})();
