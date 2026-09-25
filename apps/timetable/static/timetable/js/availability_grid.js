/**
 * Müəllim əlçatanlığı şəbəkəsi — klik/klaviatura ilə səviyyə, fırça, yadda saxlama.
 * ─────────────────────────────────────────────────────────────────────
 * Səviyyələr: n (neytral) → p (üstünlük) → d (dəyişdirilə bilən) → u (gələ bilmir).
 * Klaviatura: oxlar — xanalar arasında (roving tabindex), 1–4 — səviyyə birbaşa,
 * Boşluq/Enter — düymənin öz klik hadisəsi (dövr və ya fırça).
 * AJAX-safe: yalnız EMSDelegate; vəziyyət DOM-dadır (data-level).
 */
(function (window, document) {
    "use strict";

    var TT = window.EMSTimetable;
    var ORDER = ["n", "p", "d", "u"];
    var state = { brush: "" };

    function root() {
        return document.querySelector("[data-tt-avail]");
    }

    function cells(scope) {
        return Array.prototype.slice.call(scope.querySelectorAll("[data-tt-cell]"));
    }

    function levelLabel(scope, level) {
        return scope.getAttribute("data-label-" + level) || level;
    }

    function setLevel(scope, cell, level) {
        if (ORDER.indexOf(level) < 0) {
            return;
        }
        cell.setAttribute("data-level", level);
        cell.className = "tt-lvl tt-lvl--" + level;
        cell.setAttribute(
            "aria-label",
            cell.getAttribute("data-day-label") + ", " + cell.getAttribute("data-pair") + ": " + levelLabel(scope, level)
        );
        scope.setAttribute("data-dirty", "1");
    }

    function nextLevel(level) {
        return ORDER[(ORDER.indexOf(level) + 1) % ORDER.length];
    }

    window.EMSDelegate.on("click", "[data-tt-cell]", function (event, cell) {
        var scope = root();
        if (scope) {
            setLevel(scope, cell, state.brush || nextLevel(cell.getAttribute("data-level") || "n"));
        }
    });

    window.EMSDelegate.on("click", "[data-tt-brush]", function (event, button) {
        state.brush = button.getAttribute("data-tt-brush") || "";
        document.querySelectorAll("[data-tt-brush]").forEach(function (other) {
            other.setAttribute("aria-pressed", other === button ? "true" : "false");
        });
    });

    // Gün başlığı: bütün gün «gələ bilmir» ⇄ «neytral».
    window.EMSDelegate.on("click", "[data-tt-day]", function (event, button) {
        var scope = root();
        if (!scope) {
            return;
        }
        var day = button.getAttribute("data-tt-day");
        var dayCells = cells(scope).filter(function (cell) {
            return cell.getAttribute("data-weekday") === day;
        });
        var allOff = dayCells.every(function (cell) {
            return cell.getAttribute("data-level") === "u";
        });
        dayCells.forEach(function (cell) {
            setLevel(scope, cell, allOff ? "n" : "u");
        });
    });

    function focusCell(list, index) {
        if (index < 0 || index >= list.length) {
            return;
        }
        list.forEach(function (cell) {
            cell.setAttribute("tabindex", "-1");
        });
        list[index].setAttribute("tabindex", "0");
        list[index].focus();
    }

    window.EMSDelegate.on("keydown", "[data-tt-cell]", function (event, cell) {
        var scope = root();
        if (!scope) {
            return;
        }
        var list = cells(scope);
        var index = list.indexOf(cell);
        var width = scope.querySelectorAll("[data-tt-day]").length || 1;
        var key = event.key;
        if (key >= "1" && key <= "4") {
            event.preventDefault();
            setLevel(scope, cell, ORDER[Number(key) - 1]);
            return;
        }
        var target = {
            ArrowRight: index + 1,
            ArrowLeft: index - 1,
            ArrowDown: index + width,
            ArrowUp: index - width,
            Home: index - (index % width),
            End: index - (index % width) + width - 1,
        }[key];
        if (target !== undefined) {
            event.preventDefault();
            focusCell(list, target);
        }
    });

    function collect(scope) {
        var grid = {};
        var pairs = 0;
        cells(scope).forEach(function (cell) {
            pairs = Math.max(pairs, Number(cell.getAttribute("data-pair")) || 0);
        });
        cells(scope).forEach(function (cell) {
            var day = cell.getAttribute("data-weekday");
            if (!grid[day]) {
                grid[day] = new Array(pairs).fill("n");
            }
            grid[day][Number(cell.getAttribute("data-pair")) - 1] = cell.getAttribute("data-level") || "n";
        });
        Object.keys(grid).forEach(function (day) {
            grid[day] = grid[day].join("");
        });
        var data = {
            period: scope.getAttribute("data-period"),
            teacher: scope.getAttribute("data-teacher"),
            grid: grid,
            subject_priorities: {},
        };
        scope.querySelectorAll("[data-tt-field]").forEach(function (field) {
            data[field.name] = field.value;
        });
        scope.querySelectorAll("[data-tt-subject]").forEach(function (row) {
            var select = row.querySelector("[data-tt-subject-select]");
            if (select && select.value) {
                data.subject_priorities[row.getAttribute("data-tt-subject")] = select.value;
            }
        });
        return data;
    }

    window.EMSDelegate.on("click", "[data-tt-avail-save]", function (event, button) {
        var scope = root();
        if (!scope) {
            return;
        }
        TT.setBusy(button, true);
        TT.post(scope.getAttribute("data-save-url"), collect(scope))
            .then(function (payload) {
                scope.removeAttribute("data-dirty");
                TT.toast(payload && payload.message, "success");
            })
            .catch(function (error) {
                TT.toast(TT.errorText(error, scope.getAttribute("data-msg-error")), "error");
            })
            .then(function () {
                TT.setBusy(button, false);
            });
    });

    window.EMSReady.once("tt-avail-unsaved", function () {
        window.addEventListener("beforeunload", function (event) {
            var scope = root();
            if (scope && scope.getAttribute("data-dirty") === "1") {
                event.preventDefault();
                event.returnValue = "";
            }
        });
    });
})(window, document);
