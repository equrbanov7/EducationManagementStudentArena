/* Cədvəl redaktoru — «Uyğun vaxtlar» şəbəkəsi + otaq tövsiyəsi (sahib 2026-10-17).
 *
 * NƏ EDİR
 *   · dialoq açılanda və sahə dəyişəndə `action=plan` sorğusu göndərir (gecikmə ilə birləşdirilir);
 *   · server qaytardığı gün × dərs saatı şəbəkəsini çəkir: ortaq boş / otaq problemi / müəllim
 *     məşğul / qrup məşğul / hər ikisi; rejim düymələri (hər ikisi / müəllim / qrup üçün) hansı
 *     xanaların TƏKLİF olunduğunu dəyişir — hesablamanı SERVER edir (`registrar/schedule_suggest.py`);
 *   · təklif olunan xanaya və ya qısa siyahıdakı sətrə klik → «Gün» + «Dərs saatı» dolur;
 *   · seçilmiş vaxt üçün boş otaqlar (tutum + korpus + laboratoriya sırası) — klik → «Otaq» dolur;
 *     sıralama dialoqda SEÇİLMİŞ korpusa görədir (`room_building`), başqa korpusun otağına klik korpus
 *     seçicisini də keçirir (`schedule_editor_room.js` → `EMSScheduleRoom.pick`).
 *   Sahə doldurulanda `change` göndərilir ki, əsas skriptin (`schedule_editor.js`) `runCheck`-i
 *   adi toqquşma yoxlamasını etsin.
 *
 * QAYDALAR: inline JS/CSS yoxdur; `EMSDelegate` ilə document səviyyəsində delegasiya (AJAX-safe);
 * kök / panel yoxdursa heç nə etmir; mətnlər panelin `data-t-*` atributlarındadır.
 */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE || !window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") {
        return;
    }

    var DIALOG_ID = "seditCell";
    var DELAY_MS = 120;
    var FIELDS = ["slot_id", "subject_id", "instructor_id", "slot_instructor_id", "slot_kind", "week_type",
        "weekday", "time_slot", "room", "room_building"];
    var state = { mode: "both", ticket: 0, timer: null, last: null };

    function root() {
        return document.querySelector("[data-sedit-root]");
    }

    function dialog() {
        return document.getElementById(DIALOG_ID);
    }

    function panel() {
        var box = dialog();
        return box ? box.querySelector("[data-sedit-plan]") : null;
    }

    function part(name) {
        var host = panel();
        return host ? host.querySelector("[data-sedit-" + name + "]") : null;
    }

    function t(key, values) {
        var host = panel();
        var text = (host && host.dataset[key]) || "";
        Object.keys(values || {}).forEach(function (name) {
            text = text.split("{" + name + "}").join(String(values[name]));
        });
        return text;
    }

    function field(name) {
        var box = dialog();
        return box ? box.querySelector('[data-sedit-field="' + name + '"]') : null;
    }

    function getField(name) {
        var el = field(name);
        return el ? el.value : "";
    }

    function setField(name, value, notify) {
        var el = field(name);
        if (!el) {
            return;
        }
        el.value = value === undefined || value === null ? "" : String(value);
        if (el.tagName === "SELECT" && window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.sync === "function") {
            window.EMSBootstrapSelect.sync(el);
        }
        if (notify) {
            el.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null && text !== "") {
            node.textContent = text;
        }
        return node;
    }

    function groupId(host) {
        var picked = field("group_id");
        return picked ? picked.value || "" : host.getAttribute("data-group-id") || "";
    }

    function payload(host) {
        var body = { action: "plan", mode: state.mode, group_id: groupId(host), period_id: host.getAttribute("data-period-id") || "" };
        FIELDS.forEach(function (name) {
            body[name] = getField(name);
        });
        return body;
    }

    function status(text) {
        var node = part("plan-status");
        if (node) {
            node.textContent = text || "";
        }
    }

    /* ── Sorğu ──────────────────────────────────────────────────────────── */

    function refresh() {
        var host = root();
        if (!host || !panel()) {
            return;
        }
        window.clearTimeout(state.timer);
        state.timer = window.setTimeout(function () {
            load(host);
        }, DELAY_MS);
    }

    function load(host) {
        var body = payload(host);
        if (!body.group_id) {
            clear();
            status(t("tPickGroup"));
            return;
        }
        var ticket = (state.ticket += 1);
        status(t("tLoading"));
        window.EMSCore.fetchJSON(host.getAttribute("data-editor-url"), { method: "POST", data: body })
            .then(function (data) {
                if (ticket !== state.ticket) {
                    return;                 /* köhnə cavab — daha yeni sorğu gedib */
                }
                if (!data || !data.ok) {
                    status((data && data.message) || t("tError"));
                    return;
                }
                state.last = data;
                render(data);
                if (window.EMSScheduleRoom) {
                    window.EMSScheduleRoom.applyDefault(data.campus || "");   /* yeni xana: qrupun korpusu */
                }
            })
            .catch(function (err) {
                if (ticket === state.ticket) {
                    clear();
                    status((err && err.payload && err.payload.message) || t("tError"));
                }
            });
    }

    function clear() {
        ["plan-top", "plan-grid", "rooms-list", "rooms-meta"].forEach(function (name) {
            var node = part(name);
            if (node) {
                node.textContent = "";
            }
        });
        var warn = part("rooms-warn");
        if (warn) {
            warn.hidden = true;
        }
    }

    /* ── Şəbəkə ─────────────────────────────────────────────────────────── */

    var STATUS_KEY = { free: "tFree", room: "tRoom", teacher: "tTeacher", group: "tGroup", both: "tBoth" };

    function cellTitle(cell) {
        var lines = [t(STATUS_KEY[cell.status] || "tFree")];
        (cell.reasons || []).forEach(function (line) {
            lines.push(line);
        });
        if (cell.status === "free" && cell.free_rooms) {
            lines.push(t("tFreeRooms", { n: cell.free_rooms }));
        }
        return lines.join("\n");
    }

    function renderGrid(data) {
        var table = part("plan-grid");
        if (!table) {
            return;
        }
        table.textContent = "";
        var byKey = {};
        (data.cells || []).forEach(function (cell) {
            byKey[cell.weekday + "|" + cell.time_slot] = cell;
        });
        var picked = getField("weekday") + "|" + getField("time_slot");
        var head = el("thead");
        var headRow = el("tr");
        headRow.appendChild(el("th", "sedit-plan__corner"));
        (data.days || []).forEach(function (day) {
            var th = el("th", "sedit-plan__day", day.short || day.label);
            th.title = day.label;
            th.scope = "col";
            headRow.appendChild(th);
        });
        head.appendChild(headRow);
        table.appendChild(head);
        var bodyEl = el("tbody");
        (data.periods || []).forEach(function (period) {
            var row = el("tr");
            var th = el("th", "sedit-plan__time");
            th.scope = "row";
            th.appendChild(el("b", "", String(period.no)));
            th.appendChild(el("small", "", period.start_time));
            row.appendChild(th);
            (data.days || []).forEach(function (day) {
                var cell = byKey[day.weekday + "|" + period.key];
                var td = el("td", "sedit-plan__cell");
                if (cell) {
                    td.appendChild(cellNode(cell, day, period, picked === day.weekday + "|" + period.key));
                }
                row.appendChild(td);
            });
            bodyEl.appendChild(row);
        });
        table.appendChild(bodyEl);
    }

    function cellNode(cell, day, period, selected) {
        var tag = cell.suggested ? "button" : "span";
        var node = el(tag, "sedit-plan__slot is-" + cell.status);
        if (cell.suggested) {
            node.type = "button";
            node.classList.add("is-suggested");
            node.setAttribute("data-sedit-plan-pick", "1");
            node.dataset.weekday = String(cell.weekday);
            node.dataset.timeSlot = cell.time_slot;
        }
        if (selected) {
            node.classList.add("is-selected");
        }
        if (cell.rank) {
            node.appendChild(el("span", "sedit-plan__rank", String(cell.rank)));
        }
        var label = day.label + " " + period.start_time + "–" + period.end_time + ". " + cellTitle(cell);
        node.title = label;
        node.setAttribute("aria-label", label);
        return node;
    }

    function renderTop(data) {
        var host = part("plan-top");
        if (!host) {
            return;
        }
        host.textContent = "";
        if (!data.top || !data.top.length) {
            host.appendChild(el("p", "sedit-plan__empty", t("tNoTop")));
            return;
        }
        data.top.forEach(function (row, index) {
            var btn = el("button", "sedit-plan__pick" + (row.status === "room" ? " is-room" : ""));
            btn.type = "button";
            btn.setAttribute("data-sedit-plan-pick", "1");
            btn.dataset.weekday = String(row.weekday);
            btn.dataset.timeSlot = row.time_slot;
            btn.appendChild(el("span", "sedit-plan__rank", String(index + 1)));
            var text = el("span", "sedit-plan__pick-text");
            text.appendChild(el("b", "", row.weekday_label + " · " + row.start_time + "–" + row.end_time));
            text.appendChild(el("small", "", row.note || row.shift_label || ""));
            btn.appendChild(text);
            host.appendChild(btn);
        });
    }

    /* ── Otaqlar ────────────────────────────────────────────────────────── */

    function roomsMeta(data, rooms) {
        var parts = [];
        if (rooms && rooms.joint_groups && rooms.joint_groups.length) {
            parts.push(t("tJoint", { groups: rooms.joint_groups.join(", "), n: rooms.size }));
        } else if (data.group_size) {
            parts.push(t("tSize", { n: data.group_size }));
        } else {
            parts.push(t("tSizeUnknown"));
        }
        parts.push(data.campus ? t("tCampus", { campus: data.campus }) : t("tNoCampus"));
        if (data.campus_selected && data.campus_selected !== data.campus) {
            parts.push(t("tCampusSelected", { campus: data.campus_selected }));
        }
        return parts.join(" · ");
    }

    function roomWarning(rooms) {
        if (!rooms) {
            return t("tPickTime");
        }
        if (rooms.registry_empty) {
            return t("tRegistryEmpty");
        }
        var lines = [];
        if (rooms.current_busy) {
            lines.push(t("tCurrentBusy"));
        }
        if (rooms.stream_room) {
            lines.push(t("tStreamRoom", { room: rooms.stream_room }));
        }
        if (!rooms.capacity_known) {
            lines.push(t("tCapacityUnknown"));
        } else if (!rooms.fitting && rooms.free_total) {
            lines.push(t("tNoFit"));
        }
        if (!rooms.free_total) {
            lines.push(t("tNoRooms"));
        }
        return lines.join(" ");
    }

    function roomButton(row) {
        var btn = el("button", "sedit-rooms__btn");
        btn.type = "button";
        btn.setAttribute("data-sedit-room-pick", row.label);
        btn.setAttribute("data-sedit-room-building", row.building || "");
        if (row.fits === false) {
            btn.classList.add("is-small");
        }
        if (row.is_current) {
            btn.classList.add("is-current");
            btn.setAttribute("aria-pressed", "true");
        }
        btn.appendChild(el("b", "sedit-rooms__name", row.label));
        var meta = el("span", "sedit-rooms__info");
        meta.appendChild(el("span", "", row.capacity ? t("tSeats", { n: row.capacity }) : t("tSeatsUnknown")));
        if (row.building) {
            meta.appendChild(el("span", "", row.building));
        }
        btn.appendChild(meta);
        var badges = el("span", "sedit-rooms__badges");
        if (row.fits === false) {
            badges.appendChild(el("span", "sedit-rooms__badge is-warn", t("tSmall")));
        }
        if (!row.same_campus && row.building) {
            badges.appendChild(el("span", "sedit-rooms__badge is-other", t("tOtherCampus")));
        }
        if (row.is_lab) {
            badges.appendChild(el("span", "sedit-rooms__badge", t("tLab")));
        }
        if (row.is_current) {
            badges.appendChild(el("span", "sedit-rooms__badge is-ok", t("tCurrent")));
        }
        if (badges.childNodes.length) {
            btn.appendChild(badges);
        }
        return btn;
    }

    function renderRooms(data) {
        var rooms = data.rooms;
        var meta = part("rooms-meta");
        if (meta) {
            meta.textContent = roomsMeta(data, rooms);
        }
        var warn = part("rooms-warn");
        if (warn) {
            var text = roomWarning(rooms);
            warn.textContent = text;
            warn.hidden = !text;
        }
        var list = part("rooms-list");
        if (!list) {
            return;
        }
        list.textContent = "";
        ((rooms && rooms.rows) || []).forEach(function (row) {
            list.appendChild(roomButton(row));
        });
    }

    function render(data) {
        status(data.has_teacher ? "" : t("tNoTeacher"));
        renderTop(data);
        renderGrid(data);
        renderRooms(data);
    }

    function setMode(mode) {
        state.mode = mode;
        var host = panel();
        if (!host) {
            return;
        }
        host.querySelectorAll("[data-sedit-plan-mode]").forEach(function (btn) {
            var on = btn.getAttribute("data-sedit-plan-mode") === mode;
            btn.classList.toggle("is-active", on);
            btn.setAttribute("aria-pressed", on ? "true" : "false");
        });
    }

    /* ── Delegated hadisələr ────────────────────────────────────────────── */

    /* ⚠️ `EMSDelegate.on` açarı «hadisə|selektor»dur — eyni açar əvvəlki işləyicini ƏVƏZ edir.
       `schedule_editor.js` (`[data-sedit-field]`) və `schedule_editor_subjects.js` (`#seditCell`)
       eyni hadisələri dinləyir, ona görə burada eyni elementlərə FƏRQLİ yazılışlı selektor var. */
    DELEGATE.on("ems:overlay:open", "[id='" + DIALOG_ID + "']", function () {
        setMode(state.mode);
        clear();
        refresh();
    });

    DELEGATE.on("change", "[id='" + DIALOG_ID + "'] [data-sedit-field]", function (event, target) {
        if (root() && panel() && target && target.getAttribute("data-sedit-field") !== "reason") {
            refresh();
        }
    });

    DELEGATE.on("click", "[data-sedit-plan-mode]", function (event, button) {
        event.preventDefault();
        setMode(button.getAttribute("data-sedit-plan-mode") || "both");
        refresh();
    });

    DELEGATE.on("click", "[data-sedit-plan-pick]", function (event, button) {
        event.preventDefault();
        setField("weekday", button.dataset.weekday, false);
        setField("time_slot", button.dataset.timeSlot, true);
    });

    DELEGATE.on("click", "[data-sedit-room-pick]", function (event, button) {
        event.preventDefault();
        var label = button.getAttribute("data-sedit-room-pick");
        /* Korpus → Otaq seçiciləri (`schedule_editor_room.js`): başqa korpusun otağı korpusu da keçirir. */
        var api = window.EMSScheduleRoom;
        if (!api || !api.pick(label, button.getAttribute("data-sedit-room-building") || "")) {
            setField("room", label, true);
        }
    });

    window.EMSSchedulePlanner = { refresh: refresh, setMode: setMode };
})(window, document);
