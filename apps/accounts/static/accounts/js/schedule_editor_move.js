/* «Cədvəl idarəetməsi» — dərsin YERİNİ DƏYİŞMƏK (sürüklə-burax + klaviatura).
 *
 * NİYƏ AYRI MODUL (2026-10-14, sahib: «sürüşdürüb dəyişməkdə olmur yerini»):
 *   köhnə axın HTML5 `draggable` idi — `<button>` kart Firefox-da ümumiyyətlə
 *   sürüklənmirdi, planşet/telefonda (toxunma) HTML5 DnD işləmir, müəllim
 *   görünüşündə isə kartlar sürüklənə bilən deyildi. İndi:
 *
 *   · POINTER hadisələri — siçan/qələm: 5 px hərəkətdən sonra sürükləmə başlayır;
 *     toxunma: kartı ~350 ms BASIB SAXLAYIN (adi sürüşdürmə cədvəli scroll edir);
 *   · KLAVİATURA: redaktə edilə bilən kartda «M» — köçürmə rejimi; oxlar xananı
 *     seçir, Enter — burax, Esc — ləğv (ekran oxuyucuya `aria-live` elanı) —
 *     `schedule_editor_move_keys.js` (bu faylın `window.EMSScheduleMove` səthi ilə);
 *   · buraxanda ƏVVƏLCƏ quru yoxlama (`action=check_move`) — təsdiq dialoqu
 *     toqquşmanı (müəllim / qrup / auditoriya) yazmadan ƏVVƏL göstərir; qrup və ya
 *     əhatədən kənar toqquşmada «Köçür» bağlanır, müəllim/auditoriya toqquşmasında
 *     səbəb yazıb məcburi köçürmək olar (server qaydanı yenidən tətbiq edir);
 *   · OPTİMİST UI: təsdiqdən sonra kart dərhal yeni xanaya keçir, server rədd
 *     etsə əvvəlki yerinə QAYIDIR və dialoq səbəblə yenidən açılır; uğurda panel
 *     serverdən yenilənir (KPI, park siyahısı).
 *
 * QAYDALAR: inline JS/CSS yoxdur (CSP) — mövqe yalnız CSSOM (`el.style.transform`)
 * ilə; mətnlər `[data-sedit-i18n]` `data-*`-larından; hadisələr document səviyyəsində
 * (AJAX swap-a davamlı), kök `[data-sedit-root]` yoxdursa heç nə etmir. Ortaq
 * köməkçilər `window.EMSScheduleEditor`-dədir (`schedule_editor.js`).
 */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE || window.__emsScheduleMoveBound) {
        return;                     // idempotent: document dinləyiciləri bir dəfə bağlanır
    }
    window.__emsScheduleMoveBound = true;

    var MOVE_ID = "seditMove";
    var CARD = "[data-sedit-slot]";
    var CELL = "[data-sedit-drop]";
    var LONG_PRESS_MS = 350;
    var MOUSE_SLOP = 5;
    var TOUCH_SLOP = 8;
    var MIN_REASON = 10;   // = schedule_editor_actions.MIN_REASON

    var press = null;      // pointerdown → sürükləmə başlayana qədər
    var drag = null;       // aktiv sürükləmə
    var pending = null;    // təsdiq gözləyən köçürmə
    var suppressClickUntil = 0;

    function api() {
        return window.EMSScheduleEditor || null;
    }

    function root() {
        return api() ? api().root() : null;
    }

    function texts() {
        return api() ? api().texts() : {};
    }

    function editable() {
        var host = root();
        return Boolean(host && host.getAttribute("data-can-edit") === "1");
    }

    function announce(message) {
        var host = root();
        var live = host && host.querySelector("[data-sedit-live]");
        if (live) {
            live.textContent = "";
            live.textContent = message || "";
        }
    }

    function cellOf(card) {
        return card ? card.closest(CELL) : null;
    }

    function sameCell(card, cell) {
        return card.getAttribute("data-weekday") === cell.getAttribute("data-weekday")
            && card.getAttribute("data-time-slot") === cell.getAttribute("data-time-slot");
    }

    function clearTargets() {
        document.querySelectorAll(".is-drop-target, .is-pick-target").forEach(function (el) {
            el.classList.remove("is-drop-target", "is-pick-target");
        });
    }

    /* ── Xülasə mətni: «Fənn → Bazar ertəsi, 10:10–11:40» ─────────────────── */

    function dayLabel(cell) {
        var row = cell.closest("tr");
        var table = cell.closest("table");
        if (!row || !table) {
            return "";
        }
        var index = Array.prototype.indexOf.call(row.children, cell);
        var head = table.querySelectorAll("thead th")[index];
        var name = head && head.querySelector(".smtx__day-name");
        return name ? name.textContent.trim() : "";
    }

    function timeLabel(cell) {
        var row = cell.closest("tr");
        var hours = row && row.querySelector(".smtx__hours");
        if (!hours) {
            return "";
        }
        var start = hours.querySelector("b");
        var end = hours.querySelector("small");
        return (start ? start.textContent.trim() : "") + (end ? "–" + end.textContent.trim() : "");
    }

    function summary(card, cell) {
        var name = card.getAttribute("data-name") || card.getAttribute("data-code") || "";
        var where = [dayLabel(cell), timeLabel(cell)].filter(Boolean).join(", ");
        return (texts().moveSummary || "") + " " + name + " → " + where;
    }

    /* ── Təsdiq dialoqu ───────────────────────────────────────────────────── */

    function box() {
        return document.getElementById(MOVE_ID);
    }

    function part(selector) {
        var el = box();
        return el ? el.querySelector(selector) : null;
    }

    function setError(message) {
        var error = part("[data-sedit-move-error]");
        if (error) {
            error.textContent = message || "";
            error.hidden = !message;
        }
    }

    function setVerdict(state, message) {
        var node = part("[data-sedit-move-verdict]");
        if (!node) {
            return;
        }
        node.classList.remove("is-clean", "is-clash", "is-busy");
        node.hidden = !state;
        if (state) {
            node.classList.add(state);
        }
        node.textContent = message || "";
    }

    function setConfirmEnabled(enabled) {
        var button = part("[data-sedit-move-confirm]");
        if (button) {
            button.disabled = !enabled;
        }
    }

    function showForce(show) {
        var force = part("[data-sedit-move-force]");
        if (force) {
            force.hidden = !show;
        }
    }

    /* Serverin hökmü (check_move və ya 409 gövdəsi) → dialoq vəziyyəti. */
    function applyVerdict(result) {
        var editor = api();
        var conflicts = (result && result.conflicts) || [];
        editor.renderConflicts(conflicts, part("[data-sedit-move-conflicts]"));
        var errors = (result && result.errors) || {};
        var firstError = Object.keys(errors).map(function (key) {
            return errors[key];
        }).filter(function (text) {
            return typeof text === "string";
        })[0];
        if (firstError) {
            setVerdict("is-clash", firstError);
            showForce(false);
            setConfirmEnabled(false);
            return;
        }
        if (!conflicts.length) {
            setVerdict("is-clean", texts().clean || "");
            showForce(false);
            setConfirmEnabled(true);
            return;
        }
        var allowed = editor.forceAllowed(result);
        setVerdict("is-clash", allowed ? texts().moveForceHint || "" : texts().moveBlocked || "");
        showForce(allowed);
        setConfirmEnabled(allowed);
    }

    function beginMove(card, cell) {
        var editor = api();
        if (!editor || !card || !cell || sameCell(card, cell)) {
            return;
        }
        pending = {
            card: card,
            cell: cell,
            slot_id: card.getAttribute("data-sedit-slot"),
            weekday: cell.getAttribute("data-weekday"),
            time_slot: cell.getAttribute("data-time-slot"),
        };
        var summaryNode = part("[data-sedit-move-summary]");
        if (summaryNode) {
            summaryNode.textContent = summary(card, cell);
        }
        editor.renderConflicts([], part("[data-sedit-move-conflicts]"));
        var reason = part("[data-sedit-move-reason]");
        if (reason) {
            reason.value = "";
        }
        showForce(false);
        setError("");
        setConfirmEnabled(false);
        setVerdict("is-busy", texts().checking || "");
        if (window.EMSOverlay) {
            window.EMSOverlay.open(MOVE_ID);
        }
        var ticket = pending;
        var payload = editor.basePayload();
        payload.action = "check_move";
        payload.slot_id = pending.slot_id;
        payload.weekday = pending.weekday;
        payload.time_slot = pending.time_slot;
        editor.post(payload)
            .then(function (result) {
                if (pending === ticket) {
                    applyVerdict(result);
                }
            })
            .catch(function (err) {
                if (pending !== ticket) {
                    return;
                }
                var body = err && err.payload;
                setVerdict(null);
                setError((body && body.message) || texts().error || "");
            });
    }

    /* Optimist yerləşdirmə: kart dərhal yeni xanaya; xəta olsa geri. */
    function placeCard(card, cell) {
        var origin = { parent: card.parentNode, next: card.nextSibling };
        var add = cell.querySelector(".smtx__add");
        cell.insertBefore(card, add || null);
        cell.classList.remove("is-empty");
        card.classList.add("is-pending");
        card.setAttribute("aria-busy", "true");
        return function rollback() {
            card.classList.remove("is-pending");
            card.removeAttribute("aria-busy");
            if (origin.parent) {
                origin.parent.insertBefore(card, origin.next && origin.next.parentNode === origin.parent ? origin.next : null);
            }
            if (!cell.querySelector(CARD + ", [data-sgx-slot]")) {
                cell.classList.add("is-empty");
            }
        };
    }

    function confirmMove() {
        var editor = api();
        var move = pending;
        if (!editor || !move) {
            return;
        }
        var force = part("[data-sedit-move-force]");
        var reason = part("[data-sedit-move-reason]");
        if (force && !force.hidden && reason && reason.value.trim().length < MIN_REASON) {
            setError(texts().reasonShort || "");    // server da yoxlayır; burada boş yerə geri qaytarma olmasın
            reason.focus();
            return;
        }
        var payload = editor.basePayload();
        payload.action = "move";
        payload.slot_id = move.slot_id;
        payload.weekday = move.weekday;
        payload.time_slot = move.time_slot;
        payload.force = force && !force.hidden ? "1" : "";
        payload.reason = reason ? reason.value : "";
        if (window.EMSOverlay) {
            window.EMSOverlay.close(MOVE_ID);
        }
        var rollback = placeCard(move.card, move.cell);
        announce(texts().moving || "");
        editor.post(payload)
            .then(function () {
                pending = null;
                announce(texts().moved || "");
                editor.reload();
            })
            .catch(function (err) {
                rollback();
                announce(texts().moveFailed || "");
                var body = (err && err.payload) || {};
                if (window.EMSOverlay) {
                    window.EMSOverlay.open(MOVE_ID);
                }
                pending = move;                     // «Köçür» yenidən işləsin
                applyVerdict(body);
                if (force && !force.hidden && reason) {
                    reason.value = payload.reason;   // yazılmış səbəb itməsin
                }
                setError(body.message || texts().moveFailed || texts().error || "");
                move.card.focus();
            });
    }

    DELEGATE.on("click", "[data-sedit-move-confirm]", function (event) {
        event.preventDefault();
        if (root()) {
            confirmMove();
        }
    });

    document.addEventListener("ems:overlay:close", function (event) {
        if (event.target && event.target.id === MOVE_ID && pending && !pending.card.classList.contains("is-pending")) {
            pending = null;
        }
    });

    /* ── Pointer sürükləmə ────────────────────────────────────────────────── */

    function startDrag(event) {
        var card = press.card;
        var rect = card.getBoundingClientRect();
        var ghost = card.cloneNode(true);
        ghost.removeAttribute("data-sedit-slot");
        ghost.removeAttribute("id");
        ghost.setAttribute("aria-hidden", "true");
        ghost.classList.add("smtx-card--ghost");
        ghost.style.width = rect.width + "px";
        document.body.appendChild(ghost);
        drag = {
            card: card,
            ghost: ghost,
            dx: press.x - rect.left,
            dy: press.y - rect.top,
            target: null,
            pointerId: press.pointerId,
        };
        press = null;
        card.classList.add("is-dragging");
        document.documentElement.classList.add("sedit-dragging");
        moveGhost(event.clientX, event.clientY);
    }

    function moveGhost(x, y) {
        drag.ghost.style.transform = "translate(" + (x - drag.dx) + "px, " + (y - drag.dy) + "px)";
        var under = document.elementFromPoint(x, y);
        var cell = under && under.closest ? under.closest(CELL) : null;
        if (cell && !root().contains(cell)) {
            cell = null;
        }
        if (cell !== drag.target) {
            if (drag.target) {
                drag.target.classList.remove("is-drop-target");
            }
            drag.target = cell;
            if (cell && !sameCell(drag.card, cell)) {
                cell.classList.add("is-drop-target");
            }
        }
        autoScroll(x, y);
    }

    /* Kənara yaxınlaşanda cədvəl (üfüqi) və səhifə (şaquli) özü sürüşür. */
    function autoScroll(x, y) {
        var edge = 40;
        var scroller = root().querySelector(".smtx__scroll");
        if (scroller) {
            var box2 = scroller.getBoundingClientRect();
            if (x > box2.right - edge) {
                scroller.scrollLeft += 12;
            } else if (x < box2.left + edge) {
                scroller.scrollLeft -= 12;
            }
        }
        if (y > window.innerHeight - edge) {
            window.scrollBy(0, 12);
        } else if (y < edge) {
            window.scrollBy(0, -12);
        }
    }

    function endDrag(drop) {
        if (!drag) {
            return;
        }
        var card = drag.card;
        var target = drag.target;
        drag.ghost.remove();
        card.classList.remove("is-dragging");
        document.documentElement.classList.remove("sedit-dragging");
        clearTargets();
        drag = null;
        suppressClickUntil = Date.now() + 400;   // buraxmadan sonrakı «klik» dialoq açmasın
        if (drop && target && !sameCell(card, target)) {
            beginMove(card, target);
        }
    }

    function cancelPress() {
        if (press && press.timer) {
            window.clearTimeout(press.timer);
        }
        if (press && press.card) {
            press.card.classList.remove("is-pressing");
        }
        press = null;
    }

    document.addEventListener("pointerdown", function (event) {
        var card = event.target.closest && event.target.closest(CARD);
        if (!card || !editable() || !root().contains(card) || drag) {
            return;
        }
        if (event.pointerType === "mouse" && event.button !== 0) {
            return;
        }
        cancelPress();
        press = {
            card: card,
            x: event.clientX,
            y: event.clientY,
            pointerId: event.pointerId,
            touch: event.pointerType === "touch",
            ready: event.pointerType !== "touch",
            timer: null,
        };
        if (press.touch) {
            card.classList.add("is-pressing");
            press.timer = window.setTimeout(function () {
                if (press) {
                    press.ready = true;
                    card.classList.remove("is-pressing");
                    if (navigator.vibrate) {
                        navigator.vibrate(15);
                    }
                }
            }, LONG_PRESS_MS);
        }
    });

    document.addEventListener("pointermove", function (event) {
        if (drag) {
            if (event.pointerId === drag.pointerId) {
                event.preventDefault();
                moveGhost(event.clientX, event.clientY);
            }
            return;
        }
        if (!press || event.pointerId !== press.pointerId) {
            return;
        }
        var distance = Math.abs(event.clientX - press.x) + Math.abs(event.clientY - press.y);
        if (!press.ready) {
            if (distance > TOUCH_SLOP) {
                cancelPress();             // toxunub sürüşdürür — bu scroll-dur, sürükləmə yox
            }
            return;
        }
        if (distance > (press.touch ? 0 : MOUSE_SLOP)) {
            startDrag(event);
        }
    });

    document.addEventListener("pointerup", function (event) {
        if (drag && event.pointerId === drag.pointerId) {
            endDrag(true);
            return;
        }
        if (press && press.touch && press.ready) {
            suppressClickUntil = Date.now() + 400;   // uzun basıb buraxdı — redaktə açılmasın
        }
        cancelPress();
    });

    document.addEventListener("pointercancel", function () {
        endDrag(false);
        cancelPress();
    });

    /* Sürükləmə zamanı toxunma ekranında səhifə sürüşməsin (passive: false). */
    document.addEventListener("touchmove", function (event) {
        if (drag || (press && press.ready && press.touch)) {
            event.preventDefault();
        }
    }, { passive: false });

    document.addEventListener("contextmenu", function (event) {
        if (drag || (press && press.touch)) {
            event.preventDefault();
        }
    });

    document.addEventListener("click", function (event) {
        if (Date.now() < suppressClickUntil && event.target.closest && event.target.closest(CARD + ", " + CELL)) {
            event.preventDefault();
            event.stopPropagation();
            suppressClickUntil = 0;
        }
    }, true);

    /* Klaviatura «M» rejimi AYRI moduldadır (`schedule_editor_move_keys.js`, ölçü büdcəsi). */
    window.EMSScheduleMove = {
        beginMove: beginMove,
        announce: announce,
        dayLabel: dayLabel,
        timeLabel: timeLabel,
        sameCell: sameCell,
        editable: editable,
        root: root,
        texts: texts,
        cellOf: cellOf,
        CARD: CARD,
        CELL: CELL,
    };
})(window, document);
