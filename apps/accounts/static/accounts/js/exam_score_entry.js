/*
 * exam_score_entry.js — İmtahan Mərkəzi: kağız (yazılı / praktiki) imtahan
 * ballarının köçürülməsi (siyahı forması; 2026-09-12 yazıldı, 2026-09-14 W2
 * `w2paper` + sahibin rəyi ilə yenidən quruldu).
 *
 * CSP: bu bölmədə inline <script> YOXDUR — bütün davranış buradadır. Dinamik
 * dəyərlər DOM-dan oxunur: i18n `#eseI18n` data-atributları, sətrin vəziyyəti
 * `[data-ese-row]` data-* atributları, hərf şkalası `#ese-confirm-config`
 * (json_script — server `grading_scale.bands_for` + sxem hədləri).
 *
 * Nə edir:
 *   1. SUAL BALLARI seçimdir (S1..S10, hər biri 0..question_max) — project
 *      select komponenti, yığcam variant. Tənbəl gücləndirmə: server hazır
 *      toggle render edir (`data-ese-qtoggle`), ilk klik/fokusda
 *      `EMSBootstrapSelect.enhance` çağırılır və menyu açılır (60 × 10 seçimdə
 *      ilk render ağırlaşmır; native görünüş heç vaxt yoxdur). Rəqəm düyməsi
 *      dəyəri birbaşa yazır («1» + «0» = 10), Enter/↓/↑ sütun üzrə sətir dəyişir;
 *   2. «İmtahan balı» sual rejimində yalnız-oxunan CANLI CƏMDİR, «Yekun» =
 *      giriş + cəm (+ bonus), «Hərf» server şkalası ilə (F qırmızı) — server
 *      hamısını yenidən hesablayır, bu yalnız UX;
 *   3. «Sual sayı» sütunları açıb-bağlayır (artıq sahələr `disabled` → POST-a
 *      düşmür), «Bir sualın maksimumu» seçim variantlarını yenidən qurur;
 *   4. hər sətrin VƏZİYYƏT nişanı (boş / yazılıb / dəyişdirilib / dəyişiklik ·
 *      səbəb / xəta) + «Dəyişdirilib» KPI kartı;
 *   5. «Balları yadda saxla» → TƏSDİQ dialoqu — qardaş faylda
 *      (`exam_score_entry_confirm.js`, `window.EMSExamScoreEntry` API-si ilə;
 *      modul-ölçü büdcəsi SOFT_CAP=600);
 *   6. tarixçə çekmecəsi, görünüş / sıra / çip linkləri (SPA), «İmtahan növü»
 *      çipi və «Sıfırla» — qardaş faylda (`exam_score_entry_nav.js`).
 *
 * Qaydalar (CLAUDE.md + docs/frontend/AJAX_SAFE_JS_PATTERN.md): `EMSDelegate.on`
 * (swap-safe), `EMSReady` (idempotent), null-safe. ⚠️ DELEQAT AÇARLARI
 * (`evt|selector`) qlobaldır — `data-ese-*` seçiciləri YALNIZ bu faylda.
 */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    function root() {
        return document.querySelector("[data-ese-root]");
    }

    function t(key) {
        var el = document.getElementById("eseI18n");
        return el ? el.getAttribute("data-" + key) || "" : "";
    }

    function rows(host) {
        return Array.prototype.slice.call((host || document).querySelectorAll("[data-ese-row]"));
    }

    function scoreInput(row) {
        return row.querySelector("[data-ese-score]");
    }

    function config() {
        var el = document.getElementById("ese-confirm-config");
        if (!el) {
            return null;
        }
        try {
            return JSON.parse(el.textContent || "{}");
        } catch (err) {
            return null;
        }
    }

    /* ---- Sual şəbəkəsi (S1..Sn) --------------------------------------------- */

    function questionCount(host) {
        var select = host.querySelector("[data-ese-question-count]");
        var raw = select ? select.value : host.getAttribute("data-question-count");
        var n = parseInt(raw || "0", 10);
        return isNaN(n) || n < 0 ? 0 : n;
    }

    function questionMax(host) {
        var input = host.querySelector("[data-ese-question-max]");
        var raw = input ? input.value : host.getAttribute("data-question-max");
        var n = parseInt(raw || "10", 10);
        return isNaN(n) || n < 1 ? 10 : Math.min(100, n);
    }

    function questionSelects(row) {
        return Array.prototype.slice.call(row.querySelectorAll("[data-ese-q]")).filter(function (select) {
            return !select.disabled;
        });
    }

    function isInt(value) {
        var num = Number(value);
        return value !== "" && !isNaN(num) && Math.floor(num) === num;
    }

    /* Hazır (server) toggle-un etiketi seçimlə sinxron — gücləndirilməmiş xanalar üçün. */
    function syncPlaceholderToggle(select) {
        var wrap = select.closest("[data-ese-qwrap]");
        var toggle = wrap ? wrap.querySelector("[data-ese-qtoggle]") : null;
        if (!toggle) {
            return;
        }
        var label = toggle.querySelector(".bootstrap-single-select__label-text");
        if (label) {
            label.textContent = select.value === "" ? "—" : select.value;
        }
        toggle.classList.toggle("is-placeholder", select.value === "");
    }

    /* Seçim variantlarını 0..max yenidən qur (maksimum dəyişəndə); dəyər max-dan böyükdürsə boşalır. */
    function rebuildOptions(select, max) {
        var current = select.value;
        var keep = current !== "" && Number(current) <= max ? current : "";
        select.textContent = "";
        var blank = document.createElement("option");
        blank.value = "";
        blank.textContent = "—";
        select.appendChild(blank);
        for (var i = 0; i <= max; i += 1) {
            var option = document.createElement("option");
            option.value = String(i);
            option.textContent = String(i);
            select.appendChild(option);
        }
        select.value = keep;
        select.setAttribute("data-max", String(max));
        if (select.dataset.bootstrapSelectReady === "true" && window.EMSBootstrapSelect) {
            window.EMSBootstrapSelect.refresh(select);
        }
        syncPlaceholderToggle(select);
    }

    /* Tənbəl gücləndirmə: hazır toggle → komponent (`EMSBootstrapSelect.enhance`) → menyu açılır. */
    function enhanceQuestionSelect(select, open) {
        var wrap = select.closest("[data-ese-qwrap]");
        if (!wrap) {
            return null;
        }
        var placeholder = wrap.querySelector("[data-ese-qtoggle]");
        var hadFocus = !!placeholder && document.activeElement === placeholder;
        var api = window.EMSBootstrapSelect ? window.EMSBootstrapSelect.enhance(select) : null;
        var toggle = wrap.querySelector(".bootstrap-single-select__dropdown .bootstrap-single-select__toggle");
        if (!api || !toggle) {
            return null; // komponent yoxdursa hazır toggle qalır (native görünüş yoxdur)
        }
        if (placeholder) {
            placeholder.remove();
        }
        toggle.setAttribute("aria-label", select.getAttribute("aria-label") || "");
        if (open || hadFocus) {
            toggle.focus(); // Tab ilə gələn fokus itməsin (hazır toggle silinir)
            if (window.bootstrap && window.bootstrap.Dropdown) {
                window.bootstrap.Dropdown.getOrCreateInstance(toggle).show();
            }
        }
        return toggle;
    }

    /* Sual balları → {sum, filled, invalid, dirty}. Boş sual = 0 (server ilə eyni). */
    function questionState(row, host) {
        var selects = questionSelects(row);
        var state = { count: selects.length, sum: 0, filled: 0, invalid: false, dirty: false };
        var max = questionMax(host);
        selects.forEach(function (select) {
            var value = (select.value || "").trim();
            var initial = (select.getAttribute("data-initial") || "").trim();
            if (value !== initial) {
                state.dirty = true;
            }
            if (value === "") {
                return;
            }
            state.filled += 1;
            if (!isInt(value) || Number(value) < 0 || Number(value) > max) {
                state.invalid = true;
                return;
            }
            state.sum += Number(value);
        });
        return state;
    }

    /* Sual sayı / maksimumu dəyişəndə: sütunlar, `disabled`, variantlar, yekun sahəsinin rejimi. */
    function applyQuestionGrid(host) {
        var count = questionCount(host);
        var max = questionMax(host);
        host.querySelectorAll("[data-ese-qcol]").forEach(function (th) {
            th.hidden = Number(th.getAttribute("data-ese-qcol")) > count;
        });
        host.querySelectorAll("[data-ese-qmax-label]").forEach(function (el) {
            el.textContent = String(max);
        });
        host.querySelectorAll("[data-ese-qcell]").forEach(function (td) {
            var off = Number(td.getAttribute("data-ese-qcell")) > count;
            td.hidden = off;
            var select = td.querySelector("[data-ese-q]");
            if (select) {
                // Bitmiş dövrdə yazılmış bal olan sətir (2026-09-26) — `data-locked`.
                select.disabled = off || td.parentNode.getAttribute("data-locked") === "1";
                if (String(select.getAttribute("data-max") || "") !== String(max)) {
                    rebuildOptions(select, max);
                }
            }
        });
        rows(host).forEach(function (row) {
            var total = scoreInput(row);
            if (total) {
                total.readOnly = count > 0;
                total.tabIndex = count > 0 ? -1 : 0;
                total.classList.toggle("is-readonly", count > 0);
            }
        });
    }

    /* ---- Hərf qiyməti (server şkalası) --------------------------------------- */

    function roundHalfUp(value) {
        return Math.floor(value + 0.5);
    }

    /* {total, letter, failed} — `finals.compute_final_result` ilə eyni qayda (UX üçün). */
    function grade(row, examScore, cfg) {
        var entry = Number(row.querySelector("[data-ese-entry]") ? row.querySelector("[data-ese-entry]").getAttribute("data-ese-entry") : 0) || 0;
        var bonus = Number(row.getAttribute("data-bonus") || 0) || 0;
        var total = roundHalfUp(Math.max(0, Math.min(100, entry + examScore + bonus)));
        var bands = (cfg && cfg.letter_bands) || [];
        var letter = "";
        for (var i = 0; i < bands.length; i += 1) {
            if (total >= Number(bands[i][0])) {
                letter = bands[i][1];
                break;
            }
        }
        var failLetter = bands.length ? bands[bands.length - 1][1] : "F";
        var barred = row.getAttribute("data-barred") === "1";
        var examOk = examScore >= Number(cfg ? cfg.min_final_exam_score : 0);
        var passed = !barred && examOk && total >= Number(cfg ? cfg.pass_threshold : 0);
        return { entry: entry, total: total, letter: passed ? letter || failLetter : failLetter, failed: !passed };
    }

    function syncLetter(row, examValue, cfg) {
        var badge = row.querySelector("[data-ese-letter]");
        var totalCell = row.querySelector("[data-ese-total]");
        if (!badge) {
            return;
        }
        if (examValue === "" || examValue === null) {
            var initial = badge.getAttribute("data-initial") || "";
            badge.textContent = initial || "—";
            badge.className = "ems-badge ese-letter-badge " + (badge.getAttribute("data-initial-tone") || "ems-badge--muted");
            if (totalCell) {
                totalCell.textContent = totalCell.getAttribute("data-initial") || "—";
            }
            return;
        }
        var result = grade(row, Number(examValue), cfg);
        badge.textContent = result.letter;
        badge.className = "ems-badge ese-letter-badge " + (result.failed ? "ems-badge--danger" : "ems-badge--success");
        if (totalCell) {
            totalCell.textContent = String(result.total);
        }
    }

    /* ---- Sətir vəziyyəti ------------------------------------------------------ */

    /* Sual rejimində yekun sahəsinə canlı cəm yazılır (hamısı boşdursa sahə də boş
       qalır — server «toxunma» kimi oxuyur). */
    function syncQuestionTotal(row, host) {
        var total = scoreInput(row);
        if (!total || questionCount(host) === 0) {
            return null;
        }
        var state = questionState(row, host);
        if (state.filled === 0 && !state.dirty) {
            return state;
        }
        total.value = state.filled === 0 ? total.getAttribute("data-initial") || "" : String(state.sum);
        return state;
    }

    function rowState(row) {
        var input = scoreInput(row);
        if (!input) {
            return { dirty: false, invalid: false, change: false, value: "" };
        }
        var host = root();
        var q = host ? syncQuestionTotal(row, host) : null;
        var initial = (input.getAttribute("data-initial") || "").trim();
        var value = (input.value || "").trim();
        var dirty = value !== "" && value !== initial;
        var max = Number(input.getAttribute("max") || 0);
        var num = value === "" ? null : Number(value);
        var invalid = value !== "" && (isNaN(num) || num < 0 || num > max || Math.floor(num) !== num);
        var overCap = false;
        if (q) {
            // Sual bölgüsü dəyişibsə cəm eyni qalsa da DƏYİŞİKLİKDİR (server eyni qaydanı tətbiq edir).
            dirty = dirty || (q.filled > 0 && q.dirty);
            overCap = q.filled > 0 && q.sum > max;
            invalid = invalid || q.invalid || overCap;
        }
        // Sonrakı dəyişiklik = təqdimatlı (sahibin qaydası E7).
        var change = dirty && row.getAttribute("data-has-score") === "1";
        return { dirty: dirty, invalid: invalid, overCap: overCap, change: change, value: value, questions: q };
    }

    var BADGE = "ems-badge";

    function setBadge(badge, tone, text) {
        badge.className = BADGE + " " + BADGE + "--" + tone;
        badge.textContent = text;
    }

    function syncRow(row, cfg) {
        var input = scoreInput(row);
        var badge = row.querySelector("[data-ese-status]");
        var state = rowState(row);
        if (input) {
            input.classList.toggle("is-dirty", state.dirty && !state.invalid);
            input.classList.toggle("is-invalid", state.invalid);
            input.setAttribute("aria-invalid", state.invalid ? "true" : "false");
        }
        row.classList.toggle("is-dirty", state.dirty);
        row.classList.toggle("is-invalid", state.invalid);
        if (state.dirty && !state.invalid) {
            syncLetter(row, state.value, cfg || config());
        } else {
            syncLetter(row, "", cfg || config()); // toxunulmamış və ya xətalı sətir: server dəyəri / «—»
        }
        if (!badge) {
            return state;
        }
        if (state.invalid) {
            setBadge(badge, "danger", t("status-error"));
        } else if (state.change) {
            setBadge(badge, "warning", t("status-change"));
        } else if (state.dirty) {
            setBadge(badge, "warning", t("status-dirty"));
        } else if (row.getAttribute("data-is-changed") === "1") {
            setBadge(badge, "warning", t("status-dirty"));
        } else if (row.getAttribute("data-has-score") === "1") {
            setBadge(badge, "success", t("status-recorded"));
        } else {
            setBadge(badge, "muted", t("status-empty"));
        }
        return state;
    }

    function summarize(host) {
        var all = rows(host);
        var total = { students: all.length, writes: 0, changes: 0, invalid: 0, overCap: false };
        all.forEach(function (row) {
            var state = rowState(row);
            if (state.invalid) {
                total.invalid += 1;
                total.overCap = total.overCap || !!state.overCap;
            } else if (state.dirty) {
                total.writes += 1;
                if (state.change) {
                    total.changes += 1;
                }
            }
        });
        total.untouched = total.students - total.writes - total.invalid;
        return total;
    }

    function syncSummary(host) {
        var summary = summarize(host);
        var line = host.querySelector("[data-ese-summary]");
        if (line) {
            var parts = [summary.students + " " + t("summary-students"), summary.writes + " " + t("summary-writes")];
            if (summary.changes) {
                parts.push(summary.changes + " " + t("summary-changes"));
            }
            parts.push(summary.untouched + " " + t("summary-untouched"));
            line.textContent = parts.join(" · ");
            line.classList.toggle("is-dirty", summary.writes > 0 || summary.invalid > 0);
        }
        var tile = host.querySelector('[data-ems-kpi-key="dirty"] .ems-kpi__value');
        if (tile) {
            tile.textContent = String(summary.writes);
        }
        var card = host.querySelector('[data-ems-kpi-key="dirty"]');
        if (card) {
            card.classList.toggle("ems-kpi--accent-warning", summary.writes > 0);
        }
        return summary;
    }

    function syncAll(host) {
        var cfg = config();
        rows(host).forEach(function (row) {
            syncRow(row, cfg);
        });
        return syncSummary(host);
    }

    function onRowInput(target) {
        var row = target.closest("[data-ese-row]");
        var host = root();
        if (row) {
            syncRow(row);
        }
        if (host) {
            syncSummary(host);
        }
    }

    /* ---- Klaviatura: sütun üzrə sətir keçidi + rəqəmlə yazma ----------------- */

    function focusTargetOf(row, column) {
        if (column) {
            var select = row.querySelector('[data-ese-q="' + column + '"]');
            if (!select || select.disabled) {
                return null;
            }
            var wrap = select.closest("[data-ese-qwrap]");
            return wrap ? wrap.querySelector(".bootstrap-single-select__toggle") : null;
        }
        var total = scoreInput(row);
        return total && !total.readOnly ? total : null;
    }

    function moveFocus(current, column, delta) {
        var all = rows(root()).map(function (row) {
            return focusTargetOf(row, column);
        }).filter(Boolean);
        var index = all.indexOf(current);
        if (index < 0) {
            return;
        }
        var target = all[index + delta];
        if (target) {
            target.focus();
            if (typeof target.select === "function" && target.tagName === "INPUT") {
                target.select();
            }
        }
    }

    function columnOf(element) {
        var wrap = element.closest("[data-ese-qwrap]");
        var select = wrap ? wrap.querySelector("[data-ese-q]") : null;
        return select ? select.getAttribute("data-ese-q") : "";
    }

    function handleRowKey(event, element) {
        if (event.key === "Enter" || event.key === "ArrowDown") {
            event.preventDefault(); // Enter formanı göndərməsin; ↓ dəyəri azaltmasın.
            moveFocus(element, columnOf(element), 1);
        } else if (event.key === "ArrowUp") {
            event.preventDefault();
            moveFocus(element, columnOf(element), -1);
        }
    }

    var digitBuffer = { select: null, text: "", at: 0 };

    /* Rəqəm düyməsi seçimi birbaşa yazır: «7» → 7; «1» + «0» (400 ms) → 10. */
    function typeDigit(select, key, host) {
        var now = Date.now();
        var text = digitBuffer.select === select && now - digitBuffer.at < 400 ? digitBuffer.text + key : key;
        var max = questionMax(host);
        var value = Number(text);
        if (value > max) {
            text = key;
            value = Number(key);
        }
        if (value > max) {
            return;
        }
        digitBuffer = { select: select, text: text, at: now };
        select.value = String(value);
        select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    DELEGATE.on("keydown", "[data-ese-qwrap] .bootstrap-single-select__toggle", function (event, toggle) {
        var host = root();
        var wrap = toggle.closest("[data-ese-qwrap]");
        var select = wrap ? wrap.querySelector("[data-ese-q]") : null;
        if (!host || !select) {
            return;
        }
        if (/^[0-9]$/.test(event.key)) {
            event.preventDefault();
            typeDigit(select, event.key, host);
            return;
        }
        if (event.key === "Backspace" || event.key === "Delete") {
            event.preventDefault();
            select.value = "";
            select.dispatchEvent(new Event("change", { bubbles: true }));
            return;
        }
        handleRowKey(event, toggle);
    });

    DELEGATE.on("keydown", "[data-ese-score]", function (event, input) {
        handleRowKey(event, input);
    });

    /* Tənbəl gücləndirmə — hazır toggle-a ilk klik (mousedown: fokus hadisəsindən
       ƏVVƏL, əks halda focusin hazır toggle-u silir və click boşa gedir) / fokus (Tab). */
    DELEGATE.on("mousedown", "[data-ese-qtoggle]", function (event, toggle) {
        if (event.button !== 0) {
            return;
        }
        event.preventDefault();
        var wrap = toggle.closest("[data-ese-qwrap]");
        var select = wrap ? wrap.querySelector("[data-ese-q]") : null;
        if (select) {
            enhanceQuestionSelect(select, true);
        }
    });

    DELEGATE.on("focusin", "[data-ese-qtoggle]", function (event, toggle) {
        var wrap = toggle.closest("[data-ese-qwrap]");
        var select = wrap ? wrap.querySelector("[data-ese-q]") : null;
        if (select) {
            enhanceQuestionSelect(select, false);
        }
    });

    DELEGATE.on("change", "[data-ese-q]", function (event, select) {
        syncPlaceholderToggle(select);
        onRowInput(select);
    });

    DELEGATE.on("input", "[data-ese-score]", function (event, input) {
        onRowInput(input);
    });

    DELEGATE.on("change", "[data-ese-question-count]", function () {
        var host = root();
        if (host) {
            applyQuestionGrid(host);
            syncAll(host);
        }
    });

    DELEGATE.on("input", "[data-ese-question-max]", function () {
        var host = root();
        if (host) {
            applyQuestionGrid(host);
            syncAll(host);
        }
    });

    /* ---- Qardaş modul üçün ortaq API (`exam_score_entry_confirm.js`) ---------- */

    window.EMSExamScoreEntry = {
        root: root,
        t: t,
        rows: rows,
        scoreInput: scoreInput,
        rowState: rowState,
        summarize: summarize,
        syncAll: syncAll,
        syncPlaceholderToggle: syncPlaceholderToggle,
        questionCount: questionCount,
        grade: grade,
        config: config,
    };

    /* ---- İlk render + hər swap ------------------------------------------------ */

    window.EMSReady(function () {
        var host = root();
        if (!host) {
            return;
        }
        applyQuestionGrid(host);
        syncAll(host);
    });
})(window, document);
