/*
 * teacher_exam_results.js — «İmtahan nəticələri» səhifəsi (2026-10-10 redizayn).
 *
 *  - Sətir geri sayımları (`tr[data-seconds-remaining] .timer-display`); 0-da səhifə yenilənir.
 *  - Sınaq cəhdlərinin toplu silinməsi — ortaq `results_bulk_actions.js` (id/class qarmaqları eyni).
 *  - Tarix filtri «gg.aa.iiii» (brauzer dilindən asılı native date input əvəzinə): dəyər
 *    kanonik formaya salınır (6.10.26 → 06.10.2026), səhv dəyər göndərilmir və sahənin
 *    altında aydın mesaj görünür. Server də həm gün-əvvəl, həm ISO qəbul edir.
 *
 * AJAX-safe: EMSReady (null-safe, idempotent — sətir/kök bayraqları ilə) + document
 * səviyyəli dinləyicilər EMSReady.once ilə bir dəfə.
 */
(function () {
    "use strict";

    var DAY_FIRST = /^(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})$/;
    var ISO = /^(\d{4})-(\d{1,2})-(\d{1,2})$/;
    var DATE_SELECTOR = "[data-etr-date]";

    function pad(n) {
        return (n < 10 ? "0" : "") + n;
    }

    /* core/datetime_input.parse_datetime_text(require_time=False) ilə eyni qəbul qaydası. */
    function parseDate(text) {
        var value = String(text || "").trim();
        if (!value) {
            return { ok: true, empty: true };
        }
        var match = DAY_FIRST.exec(value);
        var day;
        var month;
        var year;
        if (match) {
            day = +match[1];
            month = +match[2];
            year = match[3].length === 2 ? 2000 + (+match[3]) : +match[3];
        } else {
            match = ISO.exec(value);
            if (!match) {
                return { ok: false };
            }
            year = +match[1];
            month = +match[2];
            day = +match[3];
        }
        var probe = new Date(year, month - 1, day);
        if (month < 1 || month > 12 || probe.getFullYear() !== year || probe.getMonth() !== month - 1 ||
            probe.getDate() !== day) {
            return { ok: false };
        }
        return { ok: true, empty: false, text: pad(day) + "." + pad(month) + "." + year };
    }

    function errorId(input) {
        return (input.id || input.name) + "Error";
    }

    function clearError(input) {
        input.removeAttribute("aria-invalid");
        var node = document.getElementById(errorId(input));
        if (node) {
            node.hidden = true;
            node.textContent = "";
        }
    }

    function showError(input) {
        input.setAttribute("aria-invalid", "true");
        var node = document.getElementById(errorId(input));
        if (!node) {
            node = document.createElement("p");
            node.id = errorId(input);
            node.className = "etr-date__error";
            node.setAttribute("role", "alert");
            var wrap = input.closest(".etr-date__wrap") || input;
            wrap.parentNode.insertBefore(node, wrap.nextSibling);
            var described = (input.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
            if (described.indexOf(node.id) === -1) {
                described.push(node.id);
                input.setAttribute("aria-describedby", described.join(" "));
            }
        }
        node.textContent = input.getAttribute("data-error") || "";
        node.hidden = false;
    }

    function normalize(input) {
        var result = parseDate(input.value);
        if (!result.ok) {
            showError(input);
            return false;
        }
        clearError(input);
        if (!result.empty && input.value !== result.text) {
            input.value = result.text;
        }
        return true;
    }

    function bindDocumentListeners() {
        // Capture fazası: səhv tarix ortaq avto-filtrə (results_filter_ui.js) çatmır.
        document.addEventListener("change", function (event) {
            var input = event.target;
            if (input && input.matches && input.matches(DATE_SELECTOR) && !normalize(input)) {
                event.stopPropagation();
            }
        }, true);

        document.addEventListener("input", function (event) {
            var input = event.target;
            if (input && input.matches && input.matches(DATE_SELECTOR) && input.getAttribute("aria-invalid") === "true") {
                clearError(input);
            }
        }, true);

        // Göndəriş: fokus səhv tarixdədirsə dayan (istifadəçi mesajı görür); başqa filtr
        // dəyişibsə səhv tarix sorğuya qoşulmur — skelet ilişib qalmır.
        document.addEventListener("submit", function (event) {
            var form = event.target;
            if (!form || form.id !== "resultsFiltersForm") {
                return;
            }
            var inputs = Array.prototype.slice.call(form.querySelectorAll(DATE_SELECTOR));
            for (var i = 0; i < inputs.length; i += 1) {
                var input = inputs[i];
                if (normalize(input)) {
                    continue;
                }
                if (document.activeElement === input) {
                    event.preventDefault();
                    event.stopPropagation();
                    return;
                }
                input.disabled = true;
            }
        }, true);
    }

    function initCountdowns(root) {
        root.querySelectorAll("tr[data-seconds-remaining]").forEach(function (row) {
            var secondsLeft = parseInt(row.getAttribute("data-seconds-remaining"), 10) || 0;
            var display = row.querySelector(".timer-display");
            if (secondsLeft <= 0 || !display || row.getAttribute("data-etr-timer") === "1") {
                return;
            }
            row.setAttribute("data-etr-timer", "1");
            var timer = null;
            var tick = function () {
                if (secondsLeft <= 0) {
                    window.clearInterval(timer);
                    window.location.reload();
                    return;
                }
                display.textContent = Math.floor(secondsLeft / 60) + ":" + pad(secondsLeft % 60);
                secondsLeft -= 1;
            };
            timer = window.setInterval(tick, 1000);
            tick();
        });
    }

    function initBulkActions(root) {
        if (root.getAttribute("data-can-delete") !== "1" || root.getAttribute("data-etr-bulk") === "1" ||
            typeof window.initResultsBulkActions !== "function") {
            return;
        }
        root.setAttribute("data-etr-bulk", "1");
        window.initResultsBulkActions({
            checkboxSelector: ".js-attempt-checkbox",
            selectedCountSelector: "#selectedAttemptCount",
            selectAllSelector: "#selectAllAttemptsBtn",
            clearSelector: "#clearAttemptsBtn",
            deleteSelectedSelector: "#deleteSelectedAttemptsBtn",
            singleDeleteSelector: ".js-single-delete-attempt",
            deleteFormSelector: "#deleteAttemptsForm",
            deleteInputsSelector: "#deleteAttemptsInputs",
            confirmButtonSelector: "#confirmDeleteAttemptsBtn",
            confirmModalSelector: "#deleteAttemptsConfirmModal",
            inputName: "attempt_ids",
            singleDeleteDataAttribute: "attemptId"
        });
    }

    function init() {
        var root = document.querySelector("[data-etr-root]");
        if (!root) {
            return;
        }
        window.EMSReady.once("etr-document-listeners", bindDocumentListeners);
        initCountdowns(root);
        initBulkActions(root);
    }

    if (window.EMSReady) {
        window.EMSReady(init);
    }

    // jsdom testləri üçün (tests/js) — səhifə davranışına təsiri yoxdur.
    window.EMSExamResultsDate = { parse: parseDate };
})();
