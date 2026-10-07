/* =========================================================================
   ems_datetime_picker.js — EMSDateTime seçici dialoqu (ay şəbəkəsi + saat/dəqiqə).

   static/js/ems_datetime.js-dən SONRA yüklənir (parse/format/i18n oradadır).
   Klaviatura: oxlar (gün/həftə), Home/End, PageUp/PageDown (ay; Shift — il),
   Enter/Space (seç), Esc (bağla, fokus düyməyə qayıdır).
   AJAX-safe: dinləyicilər `document`-ə bir dəfə bağlanır — modal-a sonradan
   inject olunan forma da işləyir.
   ========================================================================= */
(function (window, document) {
    "use strict";

    var api = window.EMSDateTime;
    if (!api || !api._internal || api.open) {
        return;
    }
    var parse = api.parse;
    var pad = api._internal.pad;
    var daysInMonth = api._internal.daysInMonth;
    var texts = api._internal.texts;
    var wrapperOf = api._internal.wrapperOf;
    var writeValue = api._internal.writeValue;
    var DEFAULT_HOUR = api._internal.defaultHour;

    /* ── seçici dialoqu ── */
    var openState = null; // { wrapper, input, toggle, pop, view: {year, month}, focus: {y,m,d} }
    var uid = 0;

    function el(tag, className, attrs) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        Object.keys(attrs || {}).forEach(function (key) {
            node.setAttribute(key, attrs[key]);
        });
        return node;
    }

    function currentParts(state) {
        var res = parse(state.input.value);
        return res.ok ? res.parts : null;
    }

    function timeFromFields(state) {
        var h = parseInt(state.hourInput.value, 10);
        var mi = parseInt(state.minuteInput.value, 10);
        return {
            hour: isNaN(h) ? DEFAULT_HOUR : Math.min(23, Math.max(0, h)),
            minute: isNaN(mi) ? 0 : Math.min(59, Math.max(0, mi))
        };
    }

    function buildPopup(state) {
        var t = texts(state.wrapper);
        uid += 1;
        var popId = "ems-dt-pop-" + uid;
        var titleId = popId + "-title";
        var pop = el("div", "ems-dt__pop", {
            id: popId,
            role: "dialog",
            "aria-modal": "false",
            "aria-label": t.dialog
        });

        var head = el("div", "ems-dt__head");
        var prev = el("button", "ems-dt__nav", { type: "button", "data-ems-dt-nav": "-1", "aria-label": t.prevMonth });
        prev.innerHTML = '<i class="fas fa-chevron-left" aria-hidden="true"></i>';
        var title = el("span", "ems-dt__title", { id: titleId, "aria-live": "polite" });
        var next = el("button", "ems-dt__nav", { type: "button", "data-ems-dt-nav": "1", "aria-label": t.nextMonth });
        next.innerHTML = '<i class="fas fa-chevron-right" aria-hidden="true"></i>';
        head.appendChild(prev);
        head.appendChild(title);
        head.appendChild(next);

        var grid = el("table", "ems-dt__grid", { role: "grid", "aria-labelledby": titleId });
        var thead = el("thead");
        var hr = el("tr");
        t.weekdays.forEach(function (name, i) {
            var th = el("th", "", { scope: "col", abbr: t.weekdaysLong[i] || name });
            th.textContent = name;
            hr.appendChild(th);
        });
        thead.appendChild(hr);
        grid.appendChild(thead);
        grid.appendChild(el("tbody"));

        var time = el("div", "ems-dt__time");
        var hourId = popId + "-h";
        var minuteId = popId + "-m";
        var clock = el("i", "fas fa-clock ems-dt__clock", { "aria-hidden": "true" });
        var hourInput = el("input", "ems-dt__tinput", {
            id: hourId, type: "text", inputmode: "numeric", maxlength: "2", autocomplete: "off",
            "data-ems-dt-hour": "", "aria-label": t.hour
        });
        var colon = el("span", "ems-dt__colon", { "aria-hidden": "true" });
        colon.textContent = ":";
        var minuteInput = el("input", "ems-dt__tinput", {
            id: minuteId, type: "text", inputmode: "numeric", maxlength: "2", autocomplete: "off",
            "data-ems-dt-minute": "", "aria-label": t.minute
        });
        time.appendChild(clock);
        time.appendChild(hourInput);
        time.appendChild(colon);
        time.appendChild(minuteInput);

        var foot = el("div", "ems-dt__foot");
        var today = el("button", "ems-dt__btn", { type: "button", "data-ems-dt-today": "" });
        today.textContent = t.today;
        var done = el("button", "ems-dt__btn ems-dt__btn--primary", { type: "button", "data-ems-dt-done": "" });
        done.textContent = t.done;
        foot.appendChild(today);
        foot.appendChild(done);

        pop.appendChild(head);
        pop.appendChild(grid);
        pop.appendChild(time);
        pop.appendChild(foot);

        state.pop = pop;
        state.title = title;
        state.tbody = grid.querySelector("tbody");
        state.hourInput = hourInput;
        state.minuteInput = minuteInput;
        return pop;
    }

    function sameDay(a, y, m, d) {
        return !!a && a.year === y && a.month === m && a.day === d;
    }

    function renderGrid(state) {
        var t = texts(state.wrapper);
        var year = state.view.year;
        var month = state.view.month;
        state.title.textContent = t.months[month - 1] + " " + year;
        var selected = currentParts(state);
        var now = new Date();
        var first = new Date(year, month - 1, 1);
        var offset = (first.getDay() + 6) % 7; // bazar ertəsi = 0
        var total = daysInMonth(year, month);
        var tbody = state.tbody;
        tbody.innerHTML = "";
        var dayNum = 1 - offset;
        for (var row = 0; row < 6; row += 1) {
            var tr = el("tr");
            for (var col = 0; col < 7; col += 1, dayNum += 1) {
                var td = el("td", "", { role: "gridcell" });
                if (dayNum >= 1 && dayNum <= total) {
                    var isFocus = state.focus.day === dayNum;
                    var btn = el("button", "ems-dt__day", {
                        type: "button",
                        "data-ems-dt-day": String(dayNum),
                        tabindex: isFocus ? "0" : "-1",
                        "aria-label": dayNum + " " + t.months[month - 1] + " " + year + ", " + t.weekdaysLong[col]
                    });
                    btn.textContent = String(dayNum);
                    if (sameDay(selected, year, month, dayNum)) {
                        btn.classList.add("is-selected");
                        btn.setAttribute("aria-pressed", "true");
                    } else {
                        btn.setAttribute("aria-pressed", "false");
                    }
                    if (now.getFullYear() === year && now.getMonth() + 1 === month && now.getDate() === dayNum) {
                        btn.classList.add("is-today");
                        btn.setAttribute("aria-current", "date");
                    }
                    td.appendChild(btn);
                }
                tr.appendChild(td);
            }
            tbody.appendChild(tr);
            if (dayNum > total) {
                break;
            }
        }
    }

    function focusDay(state) {
        var btn = state.tbody.querySelector('[data-ems-dt-day="' + state.focus.day + '"]');
        if (btn) {
            btn.focus();
        }
    }

    function moveFocus(state, deltaDays, deltaMonths) {
        var base = new Date(state.view.year, state.view.month - 1, state.focus.day);
        if (deltaMonths) {
            var targetMonth = new Date(state.view.year, state.view.month - 1 + deltaMonths, 1);
            var maxDay = daysInMonth(targetMonth.getFullYear(), targetMonth.getMonth() + 1);
            base = new Date(targetMonth.getFullYear(), targetMonth.getMonth(), Math.min(state.focus.day, maxDay));
        }
        if (deltaDays) {
            base.setDate(base.getDate() + deltaDays);
        }
        state.view = { year: base.getFullYear(), month: base.getMonth() + 1 };
        state.focus = { day: base.getDate() };
        renderGrid(state);
        focusDay(state);
    }

    function pickDay(state, day) {
        var time = timeFromFields(state);
        state.focus = { day: day };
        writeValue(state.input, {
            year: state.view.year, month: state.view.month, day: day, hour: time.hour, minute: time.minute
        });
        renderGrid(state);
    }

    function syncTimeFields(state) {
        var parts = currentParts(state);
        state.hourInput.value = pad(parts ? parts.hour : DEFAULT_HOUR);
        state.minuteInput.value = pad(parts ? parts.minute : 0);
    }

    function commitTime(state) {
        var parts = currentParts(state);
        var time = timeFromFields(state);
        state.hourInput.value = pad(time.hour);
        state.minuteInput.value = pad(time.minute);
        if (parts && (parts.hour !== time.hour || parts.minute !== time.minute)) {
            parts.hour = time.hour;
            parts.minute = time.minute;
            writeValue(state.input, parts);
        }
    }

    function placePopup(state) {
        state.pop.classList.remove("ems-dt__pop--up");
        var rect = state.pop.getBoundingClientRect();
        var wrapRect = state.wrapper.getBoundingClientRect();
        var viewport = window.innerHeight || document.documentElement.clientHeight || 0;
        if (rect.bottom > viewport && wrapRect.top - rect.height > 0) {
            state.pop.classList.add("ems-dt__pop--up");
        }
    }

    function close(returnFocus) {
        var state = openState;
        if (!state) {
            return;
        }
        openState = null;
        if (state.pop && state.pop.parentNode) {
            state.pop.parentNode.removeChild(state.pop);
        }
        state.wrapper.classList.remove("is-open");
        state.toggle.setAttribute("aria-expanded", "false");
        state.toggle.removeAttribute("aria-controls");
        if (returnFocus && state.toggle.focus) {
            state.toggle.focus();
        }
    }

    function open(wrapper) {
        if (!wrapper) {
            return;
        }
        var input = wrapper.querySelector("[data-ems-dt-input]");
        var toggle = wrapper.querySelector("[data-ems-dt-toggle]");
        if (!input || !toggle || input.disabled || input.readOnly) {
            return;
        }
        close(false);
        var state = { wrapper: wrapper, input: input, toggle: toggle };
        var parts = currentParts(state);
        var now = new Date();
        state.view = parts ? { year: parts.year, month: parts.month } :
            { year: now.getFullYear(), month: now.getMonth() + 1 };
        state.focus = { day: parts ? parts.day : now.getDate() };
        var pop = buildPopup(state);
        wrapper.appendChild(pop);
        wrapper.classList.add("is-open");
        toggle.setAttribute("aria-expanded", "true");
        toggle.setAttribute("aria-controls", pop.id);
        openState = state;
        syncTimeFields(state);
        renderGrid(state);
        placePopup(state);
        focusDay(state);
    }

    /* ── hadisələr (document-ə delegasiya; bir dəfə) ── */
    function stateFor(target) {
        return openState && openState.pop && openState.pop.contains(target) ? openState : null;
    }

    function onClick(event) {
        var target = event.target;
        if (!target || !target.closest) {
            return;
        }
        var toggle = target.closest("[data-ems-dt-toggle]");
        if (toggle) {
            event.preventDefault();
            var wrapper = wrapperOf(toggle);
            if (openState && openState.wrapper === wrapper) {
                close(true);
            } else {
                open(wrapper);
            }
            return;
        }
        var state = stateFor(target);
        if (!state) {
            if (openState && !openState.wrapper.contains(target)) {
                close(false);
            }
            return;
        }
        var nav = target.closest("[data-ems-dt-nav]");
        if (nav) {
            moveFocus(state, 0, parseInt(nav.getAttribute("data-ems-dt-nav"), 10) || 0);
            return;
        }
        var dayBtn = target.closest("[data-ems-dt-day]");
        if (dayBtn) {
            pickDay(state, parseInt(dayBtn.getAttribute("data-ems-dt-day"), 10));
            dayBtn = state.tbody.querySelector('[data-ems-dt-day="' + state.focus.day + '"]');
            if (dayBtn) {
                dayBtn.focus();
            }
            return;
        }
        if (target.closest("[data-ems-dt-today]")) {
            var now = new Date();
            state.view = { year: now.getFullYear(), month: now.getMonth() + 1 };
            pickDay(state, now.getDate());
            focusDay(state);
            return;
        }
        if (target.closest("[data-ems-dt-done]")) {
            commitTime(state);
            close(true);
        }
    }

    var KEY_DAYS = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };

    function onKeydown(event) {
        var state = openState;
        if (!state) {
            return;
        }
        var target = event.target;
        var inPop = state.pop.contains(target);
        if (event.key === "Escape" && (inPop || state.wrapper.contains(target))) {
            event.preventDefault();
            event.stopPropagation(); // modal-ın özünü bağlamasın
            close(true);
            return;
        }
        if (!inPop) {
            return;
        }
        if (target.hasAttribute("data-ems-dt-hour") || target.hasAttribute("data-ems-dt-minute")) {
            var isHour = target.hasAttribute("data-ems-dt-hour");
            if (event.key === "ArrowUp" || event.key === "ArrowDown") {
                event.preventDefault();
                var max = isHour ? 23 : 59;
                var cur = parseInt(target.value, 10);
                cur = isNaN(cur) ? 0 : cur + (event.key === "ArrowUp" ? 1 : -1);
                target.value = pad(cur < 0 ? max : (cur > max ? 0 : cur));
                commitTime(state);
            } else if (event.key === "Enter") {
                event.preventDefault();
                commitTime(state);
                close(true);
            }
            return;
        }
        if (!target.hasAttribute("data-ems-dt-day")) {
            return;
        }
        var handled = true;
        if (KEY_DAYS[event.key] !== undefined) {
            moveFocus(state, KEY_DAYS[event.key], 0);
        } else if (event.key === "Home" || event.key === "End") {
            var d = new Date(state.view.year, state.view.month - 1, state.focus.day);
            var dow = (d.getDay() + 6) % 7;
            moveFocus(state, event.key === "Home" ? -dow : 6 - dow, 0);
        } else if (event.key === "PageUp" || event.key === "PageDown") {
            var step = event.key === "PageUp" ? -1 : 1;
            moveFocus(state, 0, event.shiftKey ? step * 12 : step);
        } else if (event.key === "Enter" || event.key === " ") {
            pickDay(state, state.focus.day);
            focusDay(state);
        } else {
            handled = false;
        }
        if (handled) {
            event.preventDefault();
        }
    }

    function onTimeChange(event) {
        var target = event.target;
        var state = target && target.hasAttribute ? stateFor(target) : null;
        if (state && (target.hasAttribute("data-ems-dt-hour") || target.hasAttribute("data-ems-dt-minute"))) {
            commitTime(state);
        }
    }

    function onFocusOut(event) {
        var state = openState;
        if (!state) {
            return;
        }
        var next = event.relatedTarget;
        if (next && !state.wrapper.contains(next)) {
            commitTime(state);
            close(false);
        }
    }

    if (!window.__emsDateTimePickerBound) {
        window.__emsDateTimePickerBound = true;
        document.addEventListener("click", onClick);
        document.addEventListener("keydown", onKeydown, true);
        document.addEventListener("change", onTimeChange);
        document.addEventListener("focusout", onFocusOut);
    }

    api.open = open;
    api.close = close;
})(window, document);
