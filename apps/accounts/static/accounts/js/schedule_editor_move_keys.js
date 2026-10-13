/* «Cədvəl idarəetməsi» — sürüklə-buraxın KLAVİATURA qarşılığı («M» köçürmə rejimi).
 *
 * Redaktə edilə bilən kart fokusdadırsa «M»: kartın xanası seçilir, oxlar xananı
 * dəyişir (cədvəl lazım olsa özü sürüşür), Enter — həmin xanaya köçürmə dialoqunu
 * açır (quru yoxlama + təsdiq — siçanla eyni axın), Esc / Tab — ləğv. Hər addım
 * `aria-live` ilə elan olunur (gün, saat).
 *
 * `schedule_editor_move.js`-dən SONRA yüklənir və onun `window.EMSScheduleMove`
 * səthini işlədir (ölçü büdcəsi — 600 sətir). Inline JS yoxdur; dinləyici document
 * səviyyəsindədir və bir dəfə bağlanır (AJAX swap-a davamlı).
 */
(function (window, document) {
    "use strict";

    var M = window.EMSScheduleMove;   // köçürmə modulu bu fayldan ƏVVƏL yüklənir
    if (!M || window.__emsScheduleMoveKeysBound) {
        return;
    }
    window.__emsScheduleMoveKeysBound = true;

    var pick = null;

    function grid() {
        var host = M.root();
        var rows = [];
        if (!host) {
            return rows;
        }
        host.querySelectorAll(".smtx__table tbody tr").forEach(function (tr) {
            var cells = Array.prototype.filter.call(tr.children, function (td) {
                return td.matches(M.CELL);
            });
            if (cells.length) {
                rows.push(cells);
            }
        });
        return rows;
    }

    function setPick(cell) {
        if (pick.cell) {
            pick.cell.classList.remove("is-pick-target");
        }
        pick.cell = cell;
        cell.classList.add("is-pick-target");
        if (cell.scrollIntoView) {
            cell.scrollIntoView({ block: "nearest", inline: "nearest" });
        }
        M.announce([M.dayLabel(cell), M.timeLabel(cell)].filter(Boolean).join(", "));
    }

    function stopPick(message) {
        if (pick && pick.cell) {
            pick.cell.classList.remove("is-pick-target");
        }
        if (pick) {
            pick.card.classList.remove("is-picked");
        }
        pick = null;
        if (message) {
            M.announce(message);
        }
    }

    function stepPick(dr, dc) {
        var rows = grid();
        var r = -1;
        var c = -1;
        rows.some(function (cells, index) {
            var at = cells.indexOf(pick.cell);
            if (at >= 0) {
                r = index;
                c = at;
                return true;
            }
            return false;
        });
        if (r < 0) {
            return;
        }
        var nr = Math.max(0, Math.min(rows.length - 1, r + dr));
        var nc = Math.max(0, Math.min(rows[nr].length - 1, c + dc));
        setPick(rows[nr][nc]);
    }

    document.addEventListener("keydown", function (event) {
        if (pick) {
            var keys = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] };
            if (keys[event.key]) {
                event.preventDefault();
                stepPick(keys[event.key][0], keys[event.key][1]);
            } else if (event.key === "Enter") {
                event.preventDefault();
                var card = pick.card;
                var cell = pick.cell;
                stopPick("");
                if (M.sameCell(card, cell)) {
                    M.announce(M.texts().pickCancel || "");
                } else {
                    M.beginMove(card, cell);
                }
            } else if (event.key === "Escape" || event.key === "Tab") {
                if (event.key === "Escape") {
                    event.preventDefault();
                }
                stopPick(M.texts().pickCancel || "");
            }
            return;
        }
        if ((event.key === "m" || event.key === "M") && !event.ctrlKey && !event.metaKey && !event.altKey) {
            var target = event.target.closest && event.target.closest(M.CARD);
            if (!target || !M.editable() || !M.root().contains(target)) {
                return;
            }
            var origin = M.cellOf(target);
            if (!origin) {
                return;
            }
            event.preventDefault();
            pick = { card: target, cell: null };
            target.classList.add("is-picked");
            setPick(origin);
            M.announce(M.texts().pickMode || "");
        }
    });
})(window, document);
