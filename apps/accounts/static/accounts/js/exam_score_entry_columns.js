/*
 * exam_score_entry_columns.js — «İmtahan balının daxil edilməsi»: SÜTUN REDAKTORU və DƏYİŞİKLİK REJİMİ
 * (sahib 2026-10-25). `exam_score_entry.js`-in QARDAŞIDIR; ortaq API `window.EMSExamScoreEntry`.
 *
 *   · Sütunlar (suallar): əlavə / sil, hər sütunun maksimumu redaktə olunur; CƏM HƏMİŞƏ imtahanın tavanına
 *     (midterm 30 / final 50 — `data-cap`) bərabər olmalıdır. Uyğun gəlməsə aydın xəbərdarlıq və
 *     «Yadda saxla» bloklanır (`data-columns-invalid`). «Bərabər böl» — tam ədədlər, qalıq SONUNCU sütuna
 *     (30 / 4 → 7, 7, 7, 9). Server eyni qaydanı yenidən tətbiq edir (`clean_column_maxes`).
 *   · Gizli sahələr: `question_maxes` ("7,7,7,9"), köhnə `question_count` / `question_max` (geriyə uyğunluq).
 *   · Rejim: «Apellyasiya ilə dəyiş» / «RİM təqdimatı ilə düzəliş» — «Yekun» sətirləri açır, formaya `kind`
 *     qoşur; «Rejimdən çıx» həmin sətirləri server dəyərinə qaytarır.
 *
 * CSP: inline yoxdur; i18n `#eseI18n`. AJAX-safe: `EMSDelegate` (açarlar `data-ese-col-*`, `data-ese-mode*`).
 */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    function api() {
        return window.EMSExamScoreEntry || null;
    }

    function root() {
        return document.querySelector("[data-ese-root]");
    }

    function t(key) {
        var el = document.getElementById("eseI18n");
        return el ? el.getAttribute("data-" + key) || "" : "";
    }

    function editor(host) {
        return host ? host.querySelector("[data-ese-columns]") : null;
    }

    function intAttr(el, name, fallback) {
        var n = parseInt(el.getAttribute(name) || "", 10);
        return isNaN(n) ? fallback : n;
    }

    function items(ed) {
        return Array.prototype.slice.call(ed.querySelectorAll("[data-ese-col]"));
    }

    function valueOf(item) {
        var input = item.querySelector("[data-ese-col-max]");
        var raw = input ? String(input.value || "").trim() : "";
        var num = Number(raw);
        return raw !== "" && Math.floor(num) === num ? num : NaN;
    }

    /* «Bərabər böl»: tam ədədlər, qalıq sonuncu sütuna (server `equal_split` ilə eyni). */
    function equalSplit(cap, count) {
        count = Math.max(1, count);
        var base = Math.floor(cap / count);
        var out = [];
        for (var i = 0; i < count - 1; i += 1) {
            out.push(base);
        }
        out.push(base + (cap - base * count));
        return out;
    }

    function setHidden(host, selector, value) {
        var input = host.querySelector(selector);
        if (input) {
            input.value = value;
        }
    }

    function showWarn(ed, text) {
        var warn = ed.querySelector("[data-ese-cols-warn]");
        if (warn) {
            warn.textContent = text || "";
            warn.hidden = !text;
        }
    }

    /* Redaktor → gizli sahələr + cədvəl şəbəkəsi; qayda pozulubsa `data-columns-invalid="1"`. */
    function sync(host) {
        var ed = editor(host);
        if (!ed) {
            return true;
        }
        var cap = intAttr(ed, "data-cap", 0);
        var limit = intAttr(ed, "data-max-count", 10);
        var list = items(ed);
        var values = list.map(valueOf);
        var total = 0;
        var badValue = false;
        list.forEach(function (item, index) {
            var label = "S" + (index + 1);
            var name = item.querySelector("[data-ese-col-name]");
            if (name) {
                name.textContent = label;
            }
            var input = item.querySelector("[data-ese-col-max]");
            var value = values[index];
            var bad = isNaN(value) || value < 1 || value > cap;
            badValue = badValue || bad;
            if (input) {
                input.classList.toggle("is-invalid", bad);
                input.setAttribute("aria-invalid", bad ? "true" : "false");
                input.setAttribute("aria-label", t("col-max") + " " + label);
            }
            var remove = item.querySelector("[data-ese-col-remove]");
            if (remove) {
                remove.disabled = list.length <= 1;
                remove.setAttribute("aria-label", t("col-remove") + " " + label);
            }
            total += bad ? 0 : value;
        });
        var ok = !badValue && list.length >= 1 && list.length <= limit && total === cap;
        var safe = values.map(function (value) {
            return isNaN(value) || value < 1 ? 1 : value;
        });
        setHidden(host, "[data-ese-question-maxes]", safe.join(","));
        setHidden(host, "[data-ese-question-count]", String(safe.length));
        setHidden(host, "[data-ese-question-max]", String(safe.length ? Math.max.apply(null, safe) : 1));
        var sum = ed.querySelector("[data-ese-cols-total]");
        if (sum) {
            sum.textContent = String(total);
        }
        var sumBox = ed.querySelector("[data-ese-cols-sum]");
        if (sumBox) {
            sumBox.classList.toggle("is-bad", !ok);
            sumBox.classList.toggle("is-ok", ok);
        }
        var add = ed.querySelector("[data-ese-col-add]");
        if (add) {
            add.disabled = list.length >= limit;
        }
        if (badValue) {
            showWarn(ed, t("cols-bad-value"));
        } else if (!ok) {
            showWarn(ed, t("cols-sum-bad") + " " + total + " / " + cap + ".");
        } else {
            showWarn(ed, "");
        }
        host.setAttribute("data-columns-invalid", ok ? "0" : "1");
        if (api()) {
            api().applyQuestionGrid(host);
            api().syncAll(host);
        }
        return ok;
    }

    function makeItem(ed, value) {
        var item = document.createElement("div");
        item.className = "ese-cols__item";
        item.setAttribute("data-ese-col", "");
        var name = document.createElement("span");
        name.className = "ese-cols__name";
        name.setAttribute("data-ese-col-name", "");
        var input = document.createElement("input");
        input.type = "number";
        input.className = "ems-input ese-cols__input";
        input.min = "1";
        input.max = ed.getAttribute("data-cap") || "";
        input.step = "1";
        input.inputMode = "numeric";
        input.value = value === null ? "" : String(value);
        input.setAttribute("data-ese-col-max", "");
        var remove = document.createElement("button");
        remove.type = "button";
        remove.className = "ese-cols__remove";
        remove.setAttribute("data-ese-col-remove", "");
        var icon = document.createElement("i");
        icon.className = "fas fa-xmark";
        icon.setAttribute("aria-hidden", "true");
        remove.appendChild(icon);
        item.appendChild(name);
        item.appendChild(input);
        item.appendChild(remove);
        return item;
    }

    DELEGATE.on("input", "[data-ese-col-max]", function () {
        sync(root());
    });

    DELEGATE.on("click", "[data-ese-col-add]", function (event) {
        event.preventDefault();
        var host = root();
        var ed = editor(host);
        if (!ed) {
            return;
        }
        var list = items(ed);
        if (list.length >= intAttr(ed, "data-max-count", 10)) {
            showWarn(ed, t("cols-limit"));
            return;
        }
        var used = list.map(valueOf).reduce(function (acc, value) {
            return acc + (isNaN(value) ? 0 : value);
        }, 0);
        var rest = intAttr(ed, "data-cap", 0) - used;
        var item = makeItem(ed, rest >= 1 ? rest : null);
        ed.querySelector("[data-ese-cols-list]").appendChild(item);
        sync(host);
        item.querySelector("[data-ese-col-max]").focus();
    });

    DELEGATE.on("click", "[data-ese-col-remove]", function (event, btn) {
        event.preventDefault();
        var host = root();
        var ed = editor(host);
        if (!ed || items(ed).length <= 1) {
            if (ed) {
                showWarn(ed, t("cols-min"));
            }
            return;
        }
        var item = btn.closest("[data-ese-col]");
        if (item) {
            item.remove();
        }
        sync(host);
    });

    DELEGATE.on("click", "[data-ese-col-split]", function (event) {
        event.preventDefault();
        var host = root();
        var ed = editor(host);
        if (!ed) {
            return;
        }
        var list = items(ed);
        var values = equalSplit(intAttr(ed, "data-cap", 0), list.length);
        list.forEach(function (item, index) {
            var input = item.querySelector("[data-ese-col-max]");
            if (input) {
                input.value = String(values[index]);
            }
        });
        sync(host);
    });

    /* ---- Dəyişiklik rejimi: apellyasiya / RİM təqdimatı ---------------------- */

    function resetFinalRows(host) {
        api().rows(host).forEach(function (row) {
            if (row.getAttribute("data-final") !== "1") {
                return;
            }
            var input = api().scoreInput(row);
            if (input) {
                input.value = input.getAttribute("data-initial") || "";
            }
            row.querySelectorAll("[data-ese-q]").forEach(function (select) {
                select.value = select.getAttribute("data-initial") || "";
                api().syncPlaceholderToggle(select);
                if (window.EMSBootstrapSelect && select.dataset.bootstrapSelectReady === "true") {
                    window.EMSBootstrapSelect.sync(select);
                }
            });
        });
    }

    function setMode(host, mode) {
        if (!host || !api()) {
            return;
        }
        if (mode) {
            host.setAttribute("data-change-mode", mode);
        } else {
            host.removeAttribute("data-change-mode");
            resetFinalRows(host);
        }
        var kind = host.querySelector("[data-ese-kind-field]");
        if (kind) {
            kind.value = mode || "";
            kind.disabled = !mode;
        }
        host.querySelectorAll("[data-ese-mode]").forEach(function (btn) {
            var on = btn.getAttribute("data-ese-mode") === mode;
            btn.setAttribute("aria-pressed", on ? "true" : "false");
            btn.classList.toggle("ems-btn--primary", on);
        });
        var off = host.querySelector("[data-ese-mode-off]");
        if (off) {
            off.hidden = !mode;
        }
        var note = host.querySelector("[data-ese-mode-note]");
        if (note) {
            note.textContent = mode ? t("mode-" + mode) : "";
            note.hidden = !mode;
        }
        var bar = host.querySelector("[data-ese-modebar]");
        if (bar) {
            bar.classList.toggle("is-active", !!mode);
        }
        api().applyQuestionGrid(host);
        api().syncAll(host);
    }

    DELEGATE.on("click", "[data-ese-mode]", function (event, btn) {
        event.preventDefault();
        var host = root();
        var mode = btn.getAttribute("data-ese-mode");
        setMode(host, host && host.getAttribute("data-change-mode") === mode ? "" : mode);
    });

    DELEGATE.on("click", "[data-ese-mode-off]", function (event) {
        event.preventDefault();
        setMode(root(), "");
    });

    /* Qaralamanın bərpası (`exam_score_entry_draft.js`): redaktoru verilmiş sütunlarla yenidən qur. */
    function setColumns(host, values) {
        var ed = editor(host);
        var list = ed ? ed.querySelector("[data-ese-cols-list]") : null;
        if (!list || !values || !values.length) {
            return;
        }
        list.textContent = "";
        values.forEach(function (value) {
            list.appendChild(makeItem(ed, value));
        });
        sync(host);
    }

    window.EMSExamScoreEntryColumns = {
        sync: sync,
        setColumns: setColumns,
        setMode: setMode,
        equalSplit: equalSplit,
        mode: function (host) {
            return host ? host.getAttribute("data-change-mode") || "" : "";
        },
        invalid: function (host) {
            return !!host && host.getAttribute("data-columns-invalid") === "1";
        },
    };

    window.EMSReady(function () {
        var host = root();
        if (host && api()) {
            sync(host);
        }
    });
})(window, document);
