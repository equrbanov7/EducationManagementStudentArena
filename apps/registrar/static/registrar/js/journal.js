// Elektron jurnal — canlı sətir yekunu (progressive enhancement).
// Server həqiqətin mənbəyidir; bu skript yalnız müəllim yazarkən sətrin
// yekun balını + hərfini dərhal yeniləyir və maksimumu aşan xanaları işarələyir.
(function () {
    "use strict";

    var BANDS = [
        [91, "A"], [81, "B"], [71, "C"], [61, "D"], [51, "E"], [0, "F"],
    ];

    function letterFor(total) {
        for (var i = 0; i < BANDS.length; i++) {
            if (total >= BANDS[i][0]) return BANDS[i][1];
        }
        return "F";
    }

    function clampInput(input) {
        var max = parseFloat(input.getAttribute("data-max"));
        var val = parseFloat(input.value);
        if (isNaN(val)) {
            input.classList.remove("is-invalid");
            return 0;
        }
        input.classList.toggle("is-invalid", val < 0 || (!isNaN(max) && val > max));
        return val;
    }

    function recomputeRow(row) {
        var scores = row.querySelectorAll(".journal-score");
        var total = 0;
        scores.forEach(function (input) {
            var val = clampInput(input);
            if (!isNaN(val) && val >= 0) total += val;
        });
        total = Math.round(total * 100) / 100;

        var totalCell = row.querySelector(".cell-total");
        if (totalCell) totalCell.textContent = total;

        var letterCell = row.querySelector(".cell-letter");
        if (letterCell) {
            var letter = letterFor(total);
            letterCell.textContent = letter;
            letterCell.className = "cell-letter grade-" + letter;
        }
    }

    function init() {
        var rows = document.querySelectorAll(".journal-row");
        rows.forEach(function (row) {
            row.addEventListener("input", function (e) {
                if (e.target && e.target.classList.contains("journal-score")) {
                    recomputeRow(row);
                }
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
