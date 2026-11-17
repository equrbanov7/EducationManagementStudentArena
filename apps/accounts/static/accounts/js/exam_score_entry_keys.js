/*
 * exam_score_entry_keys.js — «İmtahan balının daxil edilməsi»: KLAVİATURA (sütun üzrə sətir keçidi + rəqəmlə yazma).
 * `exam_score_entry.js`-dən ayrılıb (sahib 2026-11-18: «Apellyasiya balı» da seçimdir — modul-ölçü büdcəsi); ortaq API
 * `window.EMSExamScoreEntry`. Enter/↓ növbəti sətrin eyni sütununa, ↑ əvvəlkinə; rəqəm düyməsi seçimi birbaşa yazır
 * (S-xanaları və «Apellyasiya balı», maks — `data-appeal-max`).
 *
 * CSP: inline yoxdur. AJAX-safe: `EMSDelegate` (açarlar `keydown|[data-ese-qwrap] .bootstrap-single-select__toggle`,
 * `keydown|[data-ese-score]` — yalnız burada).
 */
(function (window) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    function api() {
        return window.EMSExamScoreEntry;
    }

    /* ---- Klaviatura: sütun üzrə sətir keçidi + rəqəmlə yazma ----------------- */

    function focusTargetOf(row, column) {
        if (column) {
            var select = column === "appeal" ? row.querySelector("[data-ese-appeal]") : row.querySelector('[data-ese-q="' + column + '"]');
            if (!select || select.disabled) {
                return null;
            }
            var wrap = select.closest("[data-ese-qwrap]");
            return wrap ? wrap.querySelector(".bootstrap-single-select__toggle") : null;
        }
        var total = api().scoreInput(row);
        return total && !total.readOnly ? total : null;
    }

    function moveFocus(current, column, delta) {
        var all = api().rows(api().root()).map(function (row) {
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

    function wrapSelect(element) {
        var wrap = element.closest("[data-ese-qwrap]");
        return wrap ? wrap.querySelector("[data-ese-q], [data-ese-appeal]") : null;
    }

    function columnOf(element) {
        var select = wrapSelect(element);
        if (!select) {
            return "";
        }
        return select.hasAttribute("data-ese-appeal") ? "appeal" : select.getAttribute("data-ese-q");
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
        var appealMax = Number(select.getAttribute("data-appeal-max") || 0);
        var max = select.hasAttribute("data-ese-appeal") ? appealMax : api().questionMax(host, select.getAttribute("data-ese-q"));
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
        var host = api().root();
        var select = wrapSelect(toggle);
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
})(window);
