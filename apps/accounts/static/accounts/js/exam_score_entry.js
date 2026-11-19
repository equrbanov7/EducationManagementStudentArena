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
 *   3. sütunlar (2026-10-25: hər sütunun öz maksimumu, `[data-ese-question-maxes]`) açılıb-bağlanır
 *      (artıq sahələr `disabled` → POST-a düşmür); «Yekun» sətir yalnız rejimdə açılır;
 *   4. hər sətrin VƏZİYYƏT nişanı (boş / yazılıb / Yekun / 15 dəq / dəyişdirilib / xəta) + KPI;
 *   5. qardaş fayllar (`window.EMSExamScoreEntry` API-si): təsdiq dialoqu `_confirm.js`, naviqasiya
 *      `_nav.js`, sütun redaktoru + rejimlər `_columns.js`, qaralama + geri sayım `_draft.js`.
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

    /* 2026-10-25: hər SÜTUNUN öz maksimumu — `[data-ese-question-maxes]` gizli sahəsi ("10,10,10"),
       sütun redaktoru (`exam_score_entry_columns.js`) yeniləyir; cəmi imtahanın tavanıdır. */
    function columnMaxes(host) {
        var input = host.querySelector("[data-ese-question-maxes]");
        var raw = input ? input.value : "";
        return String(raw || "").split(",").map(function (part) {
            return parseInt(part, 10);
        }).filter(function (n) {
            return !isNaN(n) && n > 0;
        });
    }

    function questionCount(host) {
        return columnMaxes(host).length;
    }

    /* Bir sütunun maksimumu (1-dən); naməlum sütun → ən böyük sütun. */
    function questionMax(host, column) {
        var maxes = columnMaxes(host);
        var index = Number(column || 0) - 1;
        if (index >= 0 && index < maxes.length) {
            return maxes[index];
        }
        return maxes.length ? Math.max.apply(null, maxes) : 10;
    }

    /* «Yekun» sətir (təsdiqdən 15 dəq keçib) yalnız apellyasiya / RİM rejimində açılır. */
    function rowLocked(row, host) {
        if (row.getAttribute("data-locked") === "1") {
            return true;
        }
        return row.getAttribute("data-final") === "1" && !(host && host.getAttribute("data-change-mode"));
    }

    /* S-xanaları: testdən gələn bal (`data-q-locked`, 2026-11-18) yalnız «RİM təqdimatı» rejimində açılır
       (sahib 2026-11-19: rejim «ballar açıldı» deyirdi, amma test balı kilidli qalırdı — heç nə dəyişmirdi). */
    function questionsLocked(row, host) {
        if (rowLocked(row, host)) {
            return true;
        }
        return row.getAttribute("data-q-locked") === "1" && !(host && host.getAttribute("data-change-mode") === "correction");
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
        selects.forEach(function (select) {
            var max = questionMax(host, select.getAttribute("data-ese-q"));
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

    /* Sual sayı / maksimumu dəyişəndə: sütunlar, `disabled`, variantlar, yekun sahəsinin rejimi.
       2026-10-08 (tutum): server xanada YALNIZ «—» + seçilmiş dəyəri render edir və `data-max=""`
       qoyur — ilk render-də (EMSReady) bu funksiya hər xananın 0..max variantlarını qurur. */
    function applyQuestionGrid(host) {
        var count = questionCount(host);
        host.querySelectorAll("[data-ese-qcol]").forEach(function (th) {
            var column = Number(th.getAttribute("data-ese-qcol"));
            th.hidden = column > count;
            var label = th.querySelector("[data-ese-qmax-label]");
            if (label) {
                label.textContent = String(questionMax(host, column));
            }
        });
        host.querySelectorAll("[data-ese-qcell]").forEach(function (td) {
            var column = Number(td.getAttribute("data-ese-qcell"));
            var off = column > count;
            var max = questionMax(host, column);
            td.hidden = off;
            var select = td.querySelector("[data-ese-q]");
            if (select) {
                // Bitmiş dövr (2026-09-26, `data-locked`) və «Yekun» sətir (2026-10-25, `data-final`).
                // 2026-11-18: testdən gələn bal (`data-q-locked`) — apellyasiya ilə; 2026-11-19: RİM rejimində də açılır.
                var locked = questionsLocked(td.parentNode, host);
                select.disabled = off || locked;
                var toggle = td.querySelector("[data-ese-qtoggle], .bootstrap-single-select__toggle");
                if (toggle) {
                    toggle.disabled = locked;
                }
                if (String(select.getAttribute("data-max") || "") !== String(max)) {
                    rebuildOptions(select, max);
                }
            }
        });
        // Sahib 2026-11-18: «Apellyasiya balı» da S-xanaları kimi seçimdir — 0..maks (midterm 30, final imtahan maks).
        host.querySelectorAll("[data-ese-appeal]").forEach(function (select) {
            if (String(select.getAttribute("data-max") || "") !== String(appealMax(select))) {
                rebuildOptions(select, appealMax(select));
            }
        });
        rows(host).forEach(function (row) {
            var total = scoreInput(row);
            if (total) {
                total.disabled = rowLocked(row, host);
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
        // Sahib 2026-11-18: S-xanası silinəndə yekun da DƏRHAL sinxron dəyişir (əvvəl toxunulmamış kimi qalırdı).
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

    /* ---- Apellyasiya xanası → yekun (sahib 2026-11-18) ------------------------- */

    function appealMax(select) {
        return Number(select.getAttribute("data-appeal-max") || 0);
    }

    /* Yekun xana (`[data-ese-final-cell]`) apellyasiya balını göstərir: yeni seçim, yoxdursa serverdəki
       (boş xana = toxunma) → {value, dirty}. */
    function syncAppeal(row) {
        var select = row.querySelector("[data-ese-appeal]");
        var raw = select ? (select.value || "").trim() : "";
        var initial = select ? (select.getAttribute("data-initial") || "").trim() : "";
        var value = isInt(raw) && Number(raw) >= 0 && Number(raw) <= appealMax(select) ? raw : initial;
        var cell = row.querySelector("[data-ese-final-cell]");
        var output = row.querySelector("[data-ese-effective]");
        if (cell) {
            cell.classList.toggle("has-appeal", value !== "");
        }
        if (output) {
            output.textContent = value;
        }
        return { value: value, dirty: value !== "" && value !== initial };
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
        var appeal = syncAppeal(row); // 2026-11-18: yekun xana apellyasiya balını göstərir
        var appealDirty = appeal.dirty;
        if (appealDirty) {
            syncLetter(row, appeal.value, cfg || config()); // apellyasiya balı yekundur — hərf / cəm ondan
        } else if (state.dirty && !state.invalid) {
            syncLetter(row, state.value, cfg || config());
        } else {
            syncLetter(row, "", cfg || config()); // toxunulmamış və ya xətalı sətir: server dəyəri / «—»
        }
        if (!badge) {
            return state;
        }
        if (state.invalid) {
            setBadge(badge, "danger", t("status-error"));
        } else if (appealDirty) {
            setBadge(badge, "warning", t("status-dirty")); // 2026-11-18: yeni apellyasiya balı — «dəyişdirilib»
        } else if (state.change) {
            setBadge(badge, "warning", t("status-change"));
        } else if (state.dirty) {
            setBadge(badge, "warning", t("status-dirty"));
        } else if (row.getAttribute("data-final") === "1") {
            setBadge(badge, "success", t("status-final"));
        } else if (row.getAttribute("data-edit-until")) {
            setBadge(badge, "info", t("status-window"));
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

    function wrapSelect(element) {
        var wrap = element.closest("[data-ese-qwrap]");
        return wrap ? wrap.querySelector("[data-ese-q], [data-ese-appeal]") : null;
    }

    /* Tənbəl gücləndirmə — hazır toggle-a ilk klik (mousedown: fokus hadisəsindən
       ƏVVƏL, əks halda focusin hazır toggle-u silir və click boşa gedir) / fokus (Tab). */
    DELEGATE.on("mousedown", "[data-ese-qtoggle]", function (event, toggle) {
        if (event.button !== 0) {
            return;
        }
        event.preventDefault();
        var select = wrapSelect(toggle);
        if (select) {
            enhanceQuestionSelect(select, true);
        }
    });

    DELEGATE.on("focusin", "[data-ese-qtoggle]", function (event, toggle) {
        var select = wrapSelect(toggle);
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
        columnMaxes: columnMaxes,
        applyQuestionGrid: applyQuestionGrid,
        rowLocked: rowLocked,
        questionsLocked: questionsLocked,
        grade: grade,
        config: config,
        onRowInput: onRowInput,
        questionMax: questionMax,
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
