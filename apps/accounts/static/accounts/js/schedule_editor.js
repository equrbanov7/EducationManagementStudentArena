/* «Cədvəl idarəetməsi» redaktoru — AJAX-safe panel məntiqi.
 *
 * NƏ EDİR
 *   1) boş xanaya klik  → hüceyrə dialoqu (yeni dərs);
 *   2) dərs kartına klik → eyni dialoq (redaktə + silmə);
 *   3) sürüklə-burax     → təsdiq dialoqu, sonra köçürmə (POST);
 *   4) toqquşmalar SERVERDƏN gəlir və olduğu kimi göstərilir — klient heç nə
 *      hesablamır (mühərrik: apps/registrar/schedule_conflicts.py);
 *   5) məcburi dəyişiklik səbəblə göndərilir; toqquşan dərs SİLİNMİR, parklanır;
 *   6) «boş yer təklif et» — serverin qaytardığı hüceyrələr bir klikə qoyulur.
 *
 * QAYDALAR (CLAUDE.md + docs/frontend/AJAX_SAFE_JS_PATTERN.md)
 *   · inline JS/CSS yoxdur — dinamik dəyərlər `data-*` atributlarındadır;
 *   · `EMSDelegate.on` ilə document səviyyəsində delegasiya (swap-safe);
 *   · kök element (`[data-sedit-root]`) yoxdursa heç nə etmir (null-safe);
 *   · seçimlər SERVER-render-lidir; dialoq doldurulanda dəyər
 *     `EMSBootstrapSelect.sync(select)` ilə görünüşə köçürülür (siyahı JS-dən
 *     yenidən doldurulsaydı `refresh` lazım olardı).
 *
 * ƏLÇATANLIQ: sürüklə-buraxın klaviatura qarşılığı dialoqdakı «Gün» + «Dərs
 * saatı» seçiciləridir — kart Enter/Space ilə açılır, yeni yer orada seçilir.
 */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE || !window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") {
        return;
    }

    var DIALOG_ID = "seditCell";
    var MOVE_ID = "seditMove";
    var pendingMove = null;

    function root() {
        return document.querySelector("[data-sedit-root]");
    }

    function texts() {
        var host = root();
        var node = host && host.querySelector("[data-sedit-i18n]");
        return node ? node.dataset : {};
    }

    function dialog() {
        return document.getElementById(DIALOG_ID);
    }

    function field(name) {
        var box = dialog();
        return box ? box.querySelector('[data-sedit-field="' + name + '"]') : null;
    }

    function setField(name, value) {
        var el = field(name);
        if (!el) {
            return;
        }
        el.value = value === undefined || value === null ? "" : String(value);
        if (el.tagName === "SELECT" && window.EMSBootstrapSelect) {
            window.EMSBootstrapSelect.sync(el);
        }
    }

    function getField(name) {
        var el = field(name);
        return el ? el.value : "";
    }

    function overlayOpen(id) {
        if (window.EMSOverlay) {
            window.EMSOverlay.open(id);
        }
    }

    function overlayClose(id) {
        if (window.EMSOverlay) {
            window.EMSOverlay.close(id);
        }
    }

    /* Paneli SERVERDƏN yenidən yükləyir — cari filtrləri (`sm_*`) və həftə
     * offsetini (`w`) İTİRMƏDƏN. Filtr dəyərləri ünvan sətrindən yox, render
     * olunmuş filtr panelindən oxunur: bölmə AJAX ilə açılanda ünvan sətri
     * həmişə sinxron olmur. */
    function reload() {
        var host = root();
        if (!host) {
            return;
        }
        var url = host.getAttribute("data-reload-url") || "";
        var params = new URLSearchParams();
        var form = document.querySelector('[data-ems-filters][data-section="schedule-manage"]');
        if (form) {
            form.querySelectorAll("[data-ems-filter]").forEach(function (fieldEl) {
                if (fieldEl.name && fieldEl.value) {
                    params.set(fieldEl.name, fieldEl.value);
                }
            });
        }
        var week = new URLSearchParams(window.location.search).get("w");
        if (week) {
            params.set("w", week);
        }
        var query = params.toString();
        var target = query ? url + query : url.replace(/[?&]$/, "");
        if (typeof window.EMSProfileLoadSection === "function") {
            window.EMSProfileLoadSection("schedule-manage", target);
        } else {
            window.location.href = target;
        }
    }

    /* ── Payload ────────────────────────────────────────────────────────── */

    function basePayload() {
        var host = root();
        return {
            group_id: host ? host.getAttribute("data-group-id") : "",
            period_id: host ? host.getAttribute("data-period-id") : "",
        };
    }

    function cellPayload(action) {
        var payload = basePayload();
        payload.action = action;
        ["slot_id", "subject_id", "instructor_id", "slot_kind", "week_type", "weekday", "time_slot", "room"].forEach(
            function (name) {
                payload[name] = getField(name);
            }
        );
        return payload;
    }

    function post(payload) {
        var host = root();
        return window.EMSCore.fetchJSON(host.getAttribute("data-editor-url"), { method: "POST", data: payload });
    }

    /* ── Nəticə göstərilməsi ────────────────────────────────────────────── */

    function verdict(state, message) {
        var box = dialog() && dialog().querySelector("[data-sedit-verdict]");
        if (!box) {
            return;
        }
        box.classList.remove("is-clean", "is-clash", "is-busy");
        if (!state) {
            box.hidden = true;
            box.textContent = "";
            return;
        }
        box.classList.add(state);
        box.textContent = message || "";
        box.hidden = false;
    }

    function renderConflicts(list, target) {
        if (!target) {
            return;
        }
        target.textContent = "";
        (list || []).forEach(function (row) {
            var li = document.createElement("li");
            li.className = "sedit-conflicts__item";
            var kind = document.createElement("span");
            kind.className = "sedit-conflicts__kind";
            kind.textContent = row.kind_label || row.kind || "";
            li.appendChild(kind);
            li.appendChild(document.createTextNode(row.message || ""));
            target.appendChild(li);
        });
        target.hidden = !(list && list.length);
    }

    function renderSuggestions(list, host, onPick) {
        if (!host) {
            return;
        }
        host.textContent = "";
        if (!list || !list.length) {
            var empty = document.createElement("p");
            empty.className = "sedit-suggest__empty";
            empty.textContent = texts().noSuggestions || "";
            host.appendChild(empty);
            return;
        }
        list.forEach(function (row) {
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "sedit-suggest__btn";
            btn.setAttribute("data-sedit-pick", "1");
            btn.dataset.weekday = row.weekday;
            btn.dataset.timeSlot = row.time_slot;
            var when = document.createElement("span");
            when.className = "sedit-suggest__when";
            when.textContent = row.weekday_label + " · " + row.start_time + "–" + row.end_time;
            var shift = document.createElement("span");
            shift.className = "sedit-suggest__shift";
            shift.textContent = row.shift_label || "";
            btn.appendChild(when);
            btn.appendChild(shift);
            btn.addEventListener("click", function () {
                onPick(row);
            });
            host.appendChild(btn);
        });
    }

    function showForce(show) {
        var box = dialog() && dialog().querySelector("[data-sedit-force]");
        if (box) {
            box.hidden = !show;
        }
        if (!show) {
            setField("force", "");
        }
    }

    /* ── Dialoq ─────────────────────────────────────────────────────────── */

    function resetDialog() {
        setField("slot_id", "");
        setField("force", "");
        setField("reason", "");
        setField("room", "");
        verdict(null);
        renderConflicts([], dialog() && dialog().querySelector("[data-sedit-conflicts]"));
        var suggest = dialog() && dialog().querySelector("[data-sedit-suggest]");
        if (suggest) {
            suggest.hidden = true;
        }
        showForce(false);
        var del = dialog() && dialog().querySelector("[data-sedit-delete]");
        if (del) {
            del.hidden = true;
        }
    }

    function title(text) {
        var node = document.getElementById(DIALOG_ID + "-title");
        if (node && text) {
            node.textContent = text;
        }
    }

    function openNew(button) {
        resetDialog();
        setField("weekday", button.getAttribute("data-weekday"));
        setField("time_slot", button.getAttribute("data-time-slot"));
        title(texts().newTitle);
        overlayOpen(DIALOG_ID);
        runCheck();
    }

    function openEdit(card) {
        resetDialog();
        var d = card.dataset;
        setField("slot_id", d.seditSlot);
        setField("subject_id", d.subjectId);
        setField("instructor_id", d.instructorId);
        setField("slot_kind", d.slotKind);
        setField("week_type", d.weekType);
        setField("weekday", d.weekday);
        setField("time_slot", d.timeSlot);
        setField("room", d.room);
        title(texts().editTitle);
        var del = dialog() && dialog().querySelector("[data-sedit-delete]");
        if (del) {
            del.hidden = false;
        }
        overlayOpen(DIALOG_ID);
        runCheck();
    }


    /* ── Ümumi təsdiq dialoqu ───────────────────────────────────────────── */

    /* Sahibin tələbi (2026-09-09): xanaya dərs yazanda, düzəldəndə və siləndə
       HƏMİŞƏ kiçik təsdiq dialoqu çıxsın — toqquşma olmasa belə. Sürüklə-buraxın
       öz təsdiqi «seditMove»-dadır, ona görə o axın buradan keçmir. */
    function confirmTexts() {
        return window.EMSScheduleConfirm ? window.EMSScheduleConfirm.texts() : {};
    }

    function cellSummary() {
        return window.EMSScheduleConfirm ? window.EMSScheduleConfirm.cellSummary(dialog()) : "";
    }

    function askConfirm(summary, note, onOk) {
        if (window.EMSScheduleConfirm) {
            window.EMSScheduleConfirm.ask(summary, note, onOk);
            return;
        }
        onOk();                        // sarğı yüklənməyibsə axını bloklama
    }

    /* ── Server çağırışları ─────────────────────────────────────────────── */

    function applyVerdict(result) {
        var box = dialog();
        renderConflicts(result.conflicts, box && box.querySelector("[data-sedit-conflicts]"));
        var suggest = box && box.querySelector("[data-sedit-suggest]");
        if (suggest) {
            suggest.hidden = !(result.suggestions && result.suggestions.length);
            renderSuggestions(result.suggestions, suggest.querySelector("[data-sedit-suggest-list]"), pickCell);
        }
        var hasConflict = Boolean(result.conflicts && result.conflicts.length);
        showForce(hasConflict);
        if (hasConflict) {
            verdict("is-clash", result.conflicts[0].message || "");
        } else if (result.errors && Object.keys(result.errors).length) {
            verdict("is-clash", firstError(result.errors));
        } else {
            verdict("is-clean", texts().clean || "");
        }
    }

    function firstError(errors) {
        var keys = Object.keys(errors || {});
        for (var i = 0; i < keys.length; i += 1) {
            if (typeof errors[keys[i]] === "string") {
                return errors[keys[i]];
            }
        }
        return "";
    }

    function runCheck() {
        if (!getField("subject_id") || !getField("time_slot")) {
            return;
        }
        verdict("is-busy", texts().checking || "");
        post(cellPayload("check"))
            .then(applyVerdict)
            .catch(function (err) {
                var body = err && err.payload;
                verdict("is-clash", (body && body.message) || texts().error || "");
            });
    }

    function pickCell(row) {
        setField("weekday", row.weekday);
        setField("time_slot", row.time_slot);
        runCheck();
    }

    function save(force) {
        askConfirm(cellSummary(), confirmTexts().tSave, function () {
            postSave(force);
        });
    }

    function postSave(force) {
        var payload = cellPayload("save");
        payload.force = force ? "1" : "";
        payload.reason = getField("reason");
        post(payload)
            .then(function () {
                overlayClose(DIALOG_ID);
                reload();
            })
            .catch(function (err) {
                var body = err && err.payload;
                if (body && body.conflicts) {
                    applyVerdict(body);
                    return;
                }
                verdict("is-clash", firstError(body && body.errors) || (body && body.message) || texts().error || "");
            });
    }

    /* ── Sürüklə-burax ──────────────────────────────────────────────────── */

    function moveSummary(card, cell) {
        var name = card.getAttribute("data-name") || card.getAttribute("data-code") || "";
        var day = cell.closest("tr");
        var time = day ? (day.querySelector(".smtx__hours b") || {}).textContent || "" : "";
        return (texts().moveSummary || "") + " " + name + " → " + time;
    }

    function openMove(card, cell) {
        pendingMove = {
            slot_id: card.getAttribute("data-sedit-slot"),
            weekday: cell.getAttribute("data-weekday"),
            time_slot: cell.getAttribute("data-time-slot"),
        };
        var box = document.getElementById(MOVE_ID);
        if (!box) {
            return;
        }
        var summary = box.querySelector("[data-sedit-move-summary]");
        if (summary) {
            summary.textContent = moveSummary(card, cell);
        }
        renderConflicts([], box.querySelector("[data-sedit-move-conflicts]"));
        var force = box.querySelector("[data-sedit-move-force]");
        if (force) {
            force.hidden = true;
        }
        var reason = box.querySelector("[data-sedit-move-reason]");
        if (reason) {
            reason.value = "";
        }
        var error = box.querySelector("[data-sedit-move-error]");
        if (error) {
            error.hidden = true;
            error.textContent = "";
        }
        overlayOpen(MOVE_ID);
    }

    function confirmMove() {
        if (!pendingMove) {
            return;
        }
        var box = document.getElementById(MOVE_ID);
        var reason = box && box.querySelector("[data-sedit-move-reason]");
        var forceBox = box && box.querySelector("[data-sedit-move-force]");
        var payload = basePayload();
        payload.action = "move";
        payload.slot_id = pendingMove.slot_id;
        payload.weekday = pendingMove.weekday;
        payload.time_slot = pendingMove.time_slot;
        payload.force = forceBox && !forceBox.hidden ? "1" : "";
        payload.reason = reason ? reason.value : "";
        post(payload)
            .then(function () {
                pendingMove = null;
                overlayClose(MOVE_ID);
                reload();
            })
            .catch(function (err) {
                var body = err && err.payload;
                renderConflicts(body && body.conflicts, box && box.querySelector("[data-sedit-move-conflicts]"));
                if (forceBox && body && body.conflicts && body.conflicts.length) {
                    forceBox.hidden = false;
                }
                var error = box && box.querySelector("[data-sedit-move-error]");
                if (error) {
                    error.textContent = (body && body.message) || texts().error || "";
                    error.hidden = false;
                }
            });
    }

    /* ── Parklanmış slotlar ─────────────────────────────────────────────── */

    function parkedSuggest(button) {
        var slotId = button.getAttribute("data-sedit-place");
        var host = document.querySelector('[data-sedit-parked-suggest="' + slotId + '"]');
        if (!host) {
            return;
        }
        host.hidden = false;
        var payload = basePayload();
        payload.action = "suggest";
        payload.slot_id = slotId;
        post(payload).then(function (result) {
            renderSuggestions(result.suggestions, host.querySelector("[data-sedit-suggest-list]"), function (row) {
                var body = basePayload();
                body.action = "place";
                body.slot_id = slotId;
                body.weekday = row.weekday;
                body.time_slot = row.time_slot;
                post(body).then(reload);
            });
        });
    }

    /* ── Delegated hadisələr (açarlar YALNIZ bu faylda) ─────────────────── */

    DELEGATE.on("click", "[data-sedit-new]", function (event, button) {
        event.preventDefault();
        if (root()) {
            openNew(button);
        }
    });

    DELEGATE.on("click", "[data-sedit-slot]", function (event, card) {
        event.preventDefault();
        if (root()) {
            openEdit(card);
        }
    });

    DELEGATE.on("change", "[data-sedit-field]", function () {
        if (root() && dialog() && !dialog().hidden) {
            runCheck();
        }
    });

    DELEGATE.on("submit", "[data-sedit-form]", function (event) {
        event.preventDefault();
        save(false);
    });

    DELEGATE.on("click", "[data-sedit-force-save]", function (event) {
        event.preventDefault();
        save(true);
    });

    DELEGATE.on("click", "[data-sedit-delete]", function (event) {
        event.preventDefault();
        var payload = basePayload();
        payload.action = "delete";
        payload.slot_id = getField("slot_id");
        if (!payload.slot_id) {
            return;
        }
        askConfirm(cellSummary(), confirmTexts().tDelete, function () {
            postDelete(payload);
        });
    });

    function postDelete(payload) {
        post(payload)
            .then(function () {
                overlayClose(DIALOG_ID);
                reload();
            })
            .catch(function (err) {
                var body = err && err.payload;
                verdict("is-clash", (body && body.message) || texts().error || "");
            });
    }

    DELEGATE.on("click", "[data-sedit-suggest-open]", function (event) {
        event.preventDefault();
        var payload = basePayload();
        payload.action = "suggest";
        payload.slot_id = getField("slot_id");
        payload.instructor_id = getField("instructor_id");
        payload.week_type = getField("week_type");
        post(payload).then(function (result) {
            var suggest = dialog() && dialog().querySelector("[data-sedit-suggest]");
            if (suggest) {
                suggest.hidden = false;
                renderSuggestions(result.suggestions, suggest.querySelector("[data-sedit-suggest-list]"), pickCell);
            }
        });
    });

    DELEGATE.on("click", "[data-sedit-move-confirm]", function (event) {
        event.preventDefault();
        confirmMove();
    });

    DELEGATE.on("click", "[data-sedit-place]", function (event, button) {
        event.preventDefault();
        parkedSuggest(button);
    });

    DELEGATE.on("dragstart", "[data-sedit-slot]", function (event, card) {
        card.classList.add("is-dragging");
        if (event.dataTransfer) {
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/plain", card.getAttribute("data-sedit-slot") || "");
        }
    });

    DELEGATE.on("dragend", "[data-sedit-slot]", function (event, card) {
        card.classList.remove("is-dragging");
    });

    DELEGATE.on("dragover", "[data-sedit-drop]", function (event, cell) {
        event.preventDefault();
        if (event.dataTransfer) {
            event.dataTransfer.dropEffect = "move";
        }
        cell.classList.add("is-drop-target");
    });

    DELEGATE.on("dragleave", "[data-sedit-drop]", function (event, cell) {
        cell.classList.remove("is-drop-target");
    });

    DELEGATE.on("drop", "[data-sedit-drop]", function (event, cell) {
        event.preventDefault();
        cell.classList.remove("is-drop-target");
        var slotId = event.dataTransfer ? event.dataTransfer.getData("text/plain") : "";
        var card = slotId ? document.querySelector('[data-sedit-slot="' + slotId + '"]') : null;
        if (!card || !root()) {
            return;
        }
        if (card.getAttribute("data-weekday") === cell.getAttribute("data-weekday")
            && card.getAttribute("data-time-slot") === cell.getAttribute("data-time-slot")) {
            return;
        }
        openMove(card, cell);
    });
})(window, document);
