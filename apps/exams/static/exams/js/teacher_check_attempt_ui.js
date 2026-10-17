/*
 * teacher_check_attempt_ui.js — yoxlama səhifəsinin VƏZİYYƏT qatı (Paket B, 2026-10-17).
 * Source: exams/teacher/teacher_check_attempt.html
 *
 * Hər sual kartında bal (`#hidden_score_<id>`, name=score_<id>) və rəy
 * (`#hidden_feedback_<id>`) birbaşa yazılır. Bu fayl:
 *   • kart vəziyyətini (scored | pending | empty), badge-i və xəritə çipini yeniləyir;
 *   • cəmi bal / maksimum, irəliləyiş zolağı və «yadda saxlanmamış dəyişiklik: N»
 *     sayğacını (ilkin dəyərlərlə müqayisə — geri qaytarılan dəyişiklik sayılmır) hesablayır;
 *   • bal sahəsində Enter → növbəti, Shift+Enter → əvvəlki sual; «0» / «Tam bal» düymələri;
 *   • xəritə çipi → həmin sualın bal sahəsinə fokus.
 * API: window.TCAGrading (dialoq və saxlama məntiqi teacher_check_attempt.js-dədir).
 * AJAX-safe: hadisələr EMSDelegate ilə, init kök elementdə bayraqla bir dəfə.
 */
(function () {
    "use strict";

    var t = {};
    var initial = Object.create(null);
    var listeners = [];

    function root() {
        return document.querySelector("[data-tca-root]");
    }

    function cards() {
        var r = root();
        return r ? Array.prototype.slice.call(r.querySelectorAll("[data-tca-q]")) : [];
    }

    function card(qId) {
        return document.getElementById("tca-q-" + qId);
    }

    function scoreInput(qId) {
        return document.getElementById("hidden_score_" + qId);
    }

    function feedbackInput(qId) {
        return document.getElementById("hidden_feedback_" + qId);
    }

    function maxPoints(qId) {
        var el = document.getElementById("hidden_max_points_" + qId);
        var value = parseInt(el ? el.value : "", 10);
        return Number.isFinite(value) && value > 0 ? value : 1;
    }

    function format(template, values) {
        return String(template || "").replace(/\{(\w+)\}/g, function (match, key) {
            return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : match;
        });
    }

    /* Bal mətni → tam ədəd və ya null (boş). Mənfi → 0; kəsr/vergül → tam hissə. */
    function parseScore(raw) {
        var normalized = String(raw == null ? "" : raw).trim().replace(",", ".");
        if (!normalized) {
            return null;
        }
        var match = normalized.match(/^-?\d+/);
        if (!match) {
            return null;
        }
        var value = parseInt(match[0], 10);
        return Number.isFinite(value) ? Math.max(0, value) : null;
    }

    /* Brauzer oxuya bilmədiyi mətn (Firefox/Safari: «4,5», «5 bal») → `value === ""` +
     * `validity.badInput`. Bunu BOŞ kimi qəbul etmək saxlanmış balı səssizcə silirdi
     * (review 2026-10-17, MEDIUM) — sahə etibarsız işarələnir, toxunulmur. */
    function isBadInput(input) {
        return Boolean(input && input.validity && input.validity.badInput);
    }

    function setInvalid(input, invalid) {
        if (!input) {
            return;
        }
        input.classList.toggle("is-invalid", invalid);
        input.setAttribute("aria-invalid", invalid ? "true" : "false");
        var hint = input.id ? document.querySelector('[data-tca-score-error="' + input.id + '"]') : null;
        if (hint) {
            hint.hidden = !invalid;
        }
    }

    /* Sahəni normallaşdırır: tam ədəd, [0, max] aralığı. Boş qalırsa boş.
     * Oxunmayan mətn (badInput) olduqda heç nə dəyişmir və `undefined` qaytarır. */
    function normalizeScoreField(input, max) {
        if (!input) {
            return null;
        }
        if (isBadInput(input)) {
            setInvalid(input, true);
            return undefined;
        }
        var value = parseScore(input.value);
        if (value === null) {
            input.value = "";
            return null;
        }
        if (Number.isFinite(max) && value > max) {
            value = max;
        }
        input.value = String(value);
        return value;
    }

    function scoreKey(raw) {
        var value = parseScore(raw);
        return value === null ? "" : String(value);
    }

    function stateOf(qId) {
        var c = card(qId);
        var value = parseScore(scoreInput(qId) ? scoreInput(qId).value : "");
        if (value !== null) {
            return "scored";
        }
        return c && c.getAttribute("data-has-answer") === "1" ? "pending" : "empty";
    }

    var BADGE_TONE = { scored: "ems-badge--success", pending: "ems-badge--warning", empty: "ems-badge--muted" };

    function refreshCard(qId) {
        var c = card(qId);
        if (!c) {
            return;
        }
        var state = stateOf(qId);
        var input = scoreInput(qId);
        var value = parseScore(input ? input.value : "");
        var max = maxPoints(qId);
        c.setAttribute("data-state", state);

        var badge = document.getElementById("badge_" + qId);
        if (badge) {
            badge.className = "ems-badge " + BADGE_TONE[state];
            if (state === "scored") {
                badge.textContent = value + " " + (t.pointsUnit || "");
            } else if (state === "pending") {
                badge.textContent = t.statusNotChecked || "";
            } else {
                // Serverin mətni («Cavab yoxdur» / «Boş cavab») saxlanılır.
                badge.textContent = badge.getAttribute("data-empty-label") || t.noAnswer || "";
            }
        }

        if (input) {
            setInvalid(input, isBadInput(input) || (value !== null && value > max));
        }

        var chip = document.querySelector('[data-tca-jump="' + qId + '"]');
        if (chip) {
            var stateLabel = { scored: t.mapScored, pending: t.mapPending, empty: t.mapEmpty }[state] || "";
            chip.setAttribute("data-state", state);
            chip.setAttribute(
                "aria-label",
                format(String(t.questionN || "").replace("%(n)s", "{n}"), { n: c.getAttribute("data-index") }) +
                    (stateLabel ? ": " + stateLabel : "")
            );
        }
    }

    function changedCount() {
        var count = 0;
        cards().forEach(function (c) {
            var qId = c.getAttribute("data-question-id");
            var base = initial[qId];
            if (!base) {
                return;
            }
            var score = scoreInput(qId) ? scoreKey(scoreInput(qId).value) : "";
            var feedback = feedbackInput(qId) ? feedbackInput(qId).value.trim() : "";
            if (score !== base.score || feedback !== base.feedback) {
                count += 1;
            }
        });
        return count;
    }

    function setText(selector, text) {
        document.querySelectorAll(selector).forEach(function (el) {
            el.textContent = text;
        });
    }

    function refreshSummary() {
        var total = 0;
        var max = 0;
        var done = 0;
        var list = cards();
        list.forEach(function (c) {
            var qId = c.getAttribute("data-question-id");
            var value = parseScore(scoreInput(qId) ? scoreInput(qId).value : "");
            var qMax = maxPoints(qId);
            max += qMax;
            if (value !== null) {
                total += Math.min(value, qMax);
                done += 1;
            }
        });
        setText("[data-tca-total]", String(total));
        setText("[data-tca-max]", String(max));
        var progress = document.querySelector("[data-tca-progress]");
        if (progress) {
            progress.textContent =
                list.length && done === list.length
                    ? t.allGraded || ""
                    : format(t.progress, { done: done, total: list.length });
        }
        var bar = document.querySelector("[data-tca-progress-bar]");
        if (bar) {
            var pct = list.length ? Math.round((done * 100) / list.length) : 0;
            bar.style.setProperty("--ems-bar-pct", pct + "%");
            bar.classList.toggle("ems-bar__fill--success", list.length > 0 && done === list.length);
        }

        var changed = changedCount();
        var stateEl = document.querySelector("[data-tca-state]");
        if (stateEl && stateEl.getAttribute("data-state") !== "saving") {
            stateEl.setAttribute("data-state", changed ? "dirty" : "clean");
            stateEl.textContent = changed ? format(t.stateDirty, { n: changed }) : t.stateClean || "";
        }
        var save = document.getElementById("mainSaveBtn");
        if (save) {
            save.disabled = !changed;
        }
        listeners.forEach(function (fn) {
            fn(changed);
        });
    }

    function refreshAll() {
        cards().forEach(function (c) {
            refreshCard(c.getAttribute("data-question-id"));
        });
        refreshSummary();
    }

    function orderedIds() {
        return cards().map(function (c) {
            return c.getAttribute("data-question-id");
        });
    }

    function focusQuestion(qId, options) {
        var c = card(qId);
        var input = scoreInput(qId);
        if (!c) {
            return;
        }
        var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        c.scrollIntoView({ block: (options && options.block) || "center", behavior: reduce ? "auto" : "smooth" });
        if (input) {
            input.focus({ preventScroll: true });
            if (typeof input.select === "function") {
                input.select();
            }
        }
    }

    function neighbour(qId, step) {
        var ids = orderedIds();
        var index = ids.indexOf(String(qId));
        var next = index + step;
        return index === -1 || next < 0 || next >= ids.length ? null : ids[next];
    }

    function nextUngraded(fromId) {
        var ids = orderedIds();
        var start = fromId ? ids.indexOf(String(fromId)) + 1 : 0;
        for (var i = 0; i < ids.length; i += 1) {
            var id = ids[(start + i) % ids.length];
            if (stateOf(id) !== "scored") {
                return id;
            }
        }
        return null;
    }

    function setValues(qId, score, feedback) {
        var input = scoreInput(qId);
        var fb = feedbackInput(qId);
        if (input) {
            input.value = score === null || score === undefined ? "" : String(score);
            normalizeScoreField(input, maxPoints(qId));
        }
        if (fb && typeof feedback === "string") {
            fb.value = feedback;
        }
        refreshCard(qId);
        refreshSummary();
    }

    function snapshot() {
        cards().forEach(function (c) {
            var qId = c.getAttribute("data-question-id");
            initial[qId] = {
                score: scoreInput(qId) ? scoreKey(scoreInput(qId).value) : "",
                feedback: feedbackInput(qId) ? feedbackInput(qId).value.trim() : "",
            };
        });
    }

    /* Dialoq fokus tələsi (Tab / Shift+Tab dialoqdan çıxmır) — teacher_check_attempt.js işlədir. */
    var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

    function trapFocus(event, container) {
        var items = Array.prototype.filter.call(container.querySelectorAll(FOCUSABLE), function (el) {
            return el.offsetWidth || el.offsetHeight || el.getClientRects().length;
        });
        if (!items.length) {
            event.preventDefault();
            return;
        }
        var first = items[0];
        var last = items[items.length - 1];
        if (event.shiftKey && (document.activeElement === first || !container.contains(document.activeElement))) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }

    function qIdOf(el) {
        var c = el && el.closest ? el.closest("[data-tca-q]") : null;
        return c ? c.getAttribute("data-question-id") : null;
    }

    /* ---- hadisələr (document səviyyəsində, bir dəfə) ------------------------ */
    window.EMSDelegate.on("input", "[data-tca-score], [data-tca-feedback]", function (event, el) {
        var qId = qIdOf(el);
        if (qId) {
            refreshCard(qId);
            refreshSummary();
        }
    });

    window.EMSDelegate.on("change", "[data-tca-score]", function (event, el) {
        var qId = qIdOf(el);
        if (qId && isBadInput(el)) {
            setInvalid(el, true);
            refreshSummary();
            return;
        }
        if (qId) {
            normalizeScoreField(el, maxPoints(qId));
            refreshCard(qId);
            refreshSummary();
        }
    });

    window.EMSDelegate.on("keydown", "[data-tca-score]", function (event, el) {
        if (event.key !== "Enter" || event.isComposing) {
            return;
        }
        // Enter formanı GÖNDƏRMƏMƏLİDİR — sual-sual irəliləyir.
        event.preventDefault();
        var qId = qIdOf(el);
        if (isBadInput(el)) {
            setInvalid(el, true);
            el.focus();
            return; // oxunmayan bal — fokus sahədə qalır
        }
        normalizeScoreField(el, maxPoints(qId));
        refreshCard(qId);
        refreshSummary();
        var target = neighbour(qId, event.shiftKey ? -1 : 1);
        if (target) {
            focusQuestion(target);
        } else if (!event.shiftKey) {
            var save = document.getElementById("mainSaveBtn");
            if (save && !save.disabled) {
                save.focus();
            }
        }
    });

    window.EMSDelegate.on("click", "[data-tca-quick]", function (event, btn) {
        var qId = qIdOf(btn);
        if (!qId) {
            return;
        }
        var kind = btn.getAttribute("data-tca-quick");
        setValues(qId, kind === "max" ? maxPoints(qId) : 0);
        var target = neighbour(qId, 1);
        if (target) {
            focusQuestion(target);
        }
    });

    window.EMSDelegate.on("click", "[data-tca-jump]", function (event, chip) {
        event.preventDefault();
        focusQuestion(chip.getAttribute("data-tca-jump"), { block: "start" });
    });

    window.EMSDelegate.on("click", "[data-tca-next-ungraded]", function (event) {
        event.preventDefault();
        var active = document.activeElement;
        var target = nextUngraded(qIdOf(active));
        if (target) {
            focusQuestion(target);
        }
    });

    window.TCAGrading = {
        init: function (i18n) {
            var r = root();
            if (!r || r.getAttribute("data-tca-ready") === "1") {
                return false;
            }
            r.setAttribute("data-tca-ready", "1");
            t = i18n || {};
            snapshot();
            refreshAll();
            return true;
        },
        onChange: function (fn) {
            if (typeof fn === "function") {
                listeners.push(fn);
            }
        },
        changedCount: changedCount,
        refreshAll: refreshAll,
        orderedIds: orderedIds,
        neighbour: neighbour,
        focusQuestion: focusQuestion,
        setValues: setValues,
        maxPoints: maxPoints,
        parseScore: parseScore,
        normalizeScoreField: normalizeScoreField,
        scoreInput: scoreInput,
        feedbackInput: feedbackInput,
        markSaving: function (label) {
            var stateEl = document.querySelector("[data-tca-state]");
            if (stateEl) {
                stateEl.setAttribute("data-state", "saving");
                stateEl.textContent = label || "";
            }
        },
        trapFocus: trapFocus,
        isBadInput: isBadInput,
        setInvalid: setInvalid,
        /* Göndərmədən əvvəl: hamısını normallaşdırır, oxunmayan sahələrin ID-lərini qaytarır
         * (boş deyilsə təsdiq dialoqu AÇILMIR, fokus ilk etibarsız sahəyə gedir). */
        normalizeAll: function () {
            var invalid = [];
            orderedIds().forEach(function (qId) {
                if (normalizeScoreField(scoreInput(qId), maxPoints(qId)) === undefined) {
                    invalid.push(qId);
                }
            });
            refreshAll();
            return invalid;
        },
    };
})();
