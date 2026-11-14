/* =========================================================================
   ems_datetime.js — EMSDateTime: locale-dən asılı OLMAYAN tarix-saat sahəsi.

   Server tərəfi: core/datetime_input.py (DayFirstDateTimeInput / Field).
   Format HƏMİŞƏ «gg.aa.iiii ss:dd» (gün əvvəl, 24 saat). Native
   datetime-local brauzerin dilinə tabe idi (en-US: mm/dd/yyyy + AM/PM; «06/10»
   iyun 10 oxunurdu; yarımçıq yazı boş göndərilirdi).

   • Yazmaq: istənilən ayırıcı (. / -), saatda «:» və ya «.»; blur-da dəyər
     kanonik formaya salınır, xətalı dəyər aydın mesajla işarələnir.
   • Seçici: təqvim düyməsi → kiçik dialoq (ay şəbəkəsi + saat/dəqiqə).
     Klaviatura: oxlar (gün/həftə), Home/End, PageUp/PageDown (ay; Shift — il),
     Enter/Space (seç), Esc (bağla).
   • AJAX-safe: hər şey `document`-ə delegasiya ilə bağlanır (EMSDelegate və ya
     bir dəfəlik öz dinləyiciləri) — modal-a sonradan inject olunan forma da işləyir.
   • Mətnlər `data-ems-dt-i18n` JSON-undan (server tərcüməsi); AZ ehtiyat.

   YALNIZ-TARİX rejimi (2026-11-14, sahib: «Azərbaycanda standart tarix gün ay il»):
   wrapper `data-ems-dt-mode="date"` → sahə «gg.aa.iiii», seçicidə saat yoxdur;
   `data-ems-dt-min` / `data-ems-dt-max` (ISO) aralığı — kənar günlər seçicidə
   bağlıdır, yazılanda aydın mesaj (aralıq gg.aa.iiii ilə). Server forması dəyişmir:
   gizli `[data-ems-dt-iso]` sahəsi (name="…") ISO «iiii-aa-gg» daşıyır; köhnə JS-lər
   onun `.value`-sunu oxuyub-yazır — proqram yazısı görünən sahəyə əks olunur
   (instance `value` setter-i), istifadəçi dəyişikliyi isə gizli sahədə `input` +
   `change` hadisəsi göndərir. Server: core/datetime_input.py
   (render_day_first_date_input), şablon teqi `{% ems_date_input %}`.

   Seçici dialoqu ayrı fayldadır: static/js/ems_datetime_picker.js (bu fayldan
   SONRA yüklənir; 600 sətir modul limiti).

   API: EMSDateTime.parse(text, {requireTime}) → {ok, parts|code}
        EMSDateTime.format(parts) → "gg.aa.iiii ss:dd"
        EMSDateTime.formatDate(parts) → "gg.aa.iiii"; toIso(parts) → "iiii-aa-gg"
        EMSDateTime.validate(input) → {ok, empty, code, message, parts}
        EMSDateTime.toDate(parts) → Date (brauzerin yerli vaxtı)
        EMSDateTime.display(isoOrText) → "gg.aa.iiii ss:dd" (modal prefill-i)
        EMSDateTime.bindDates(root) → yalnız-tarix sahələrini bağla (AJAX swap-dan sonra)
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSDateTime && window.EMSDateTime.__ready) {
        return;
    }

    var TIME = "(?:(?:\\s+|\\s*[T,]\\s*)(\\d{1,2})[:.](\\d{2})(?::(\\d{2})(?:\\.\\d+)?)?)?";
    var DAY_FIRST_RE = new RegExp("^(\\d{1,2})[./-](\\d{1,2})[./-](\\d{4}|\\d{2})" + TIME + "$");
    var ISO_RE = new RegExp("^(\\d{4})-(\\d{1,2})-(\\d{1,2})" + TIME + "$");
    var ISO_DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

    var FALLBACK = {
        months: ["Yanvar", "Fevral", "Mart", "Aprel", "May", "İyun", "İyul", "Avqust",
            "Sentyabr", "Oktyabr", "Noyabr", "Dekabr"],
        weekdays: ["B.e", "Ç.a", "Çrş", "C.a", "Cüm", "Şnb", "Bzr"],
        weekdaysLong: ["Bazar ertəsi", "Çərşənbə axşamı", "Çərşənbə", "Cümə axşamı", "Cümə", "Şənbə", "Bazar"],
        dialog: "Tarix və saatı seçin",
        prevMonth: "Əvvəlki ay",
        nextMonth: "Növbəti ay",
        hour: "Saatı seçin",
        minute: "Dəqiqəni seçin",
        today: "Bu gün",
        done: "Hazırdır",
        errors: {
            invalid: "Tarixi və saatı gg.aa.iiii ss:dd formatında yazın (məsələn, 06.10.2026 09:30).",
            invalid_date: "Belə tarix yoxdur. Günü, ayı və ili yoxlayın (gg.aa.iiii).",
            invalid_time: "Saat 00:00 ilə 23:59 arasında olmalıdır (24 saat formatı).",
            missing_time: "Saatı da yazın (ss:dd, 24 saat formatı)."
        }
    };
    /* Yalnız-tarix rejiminin ehtiyat mətnləri (server `data-ems-dt-i18n`-də tərcüməsini verir). */
    var FALLBACK_DATE = {
        dialog: "Tarixi seçin",
        errors: {
            invalid: "Tarixi gg.aa.iiii formatında yazın (məsələn, 06.10.2026).",
            invalid_date: FALLBACK.errors.invalid_date,
            out_of_range: "Tarix {min} ilə {max} arasında olmalıdır.",
            before_min: "Tarix {min} və ya daha sonra olmalıdır.",
            after_max: "Tarix {max} və ya daha əvvəl olmalıdır."
        }
    };
    var DEFAULT_HOUR = 9;

    function pad(n) {
        return (n < 10 ? "0" : "") + n;
    }

    function daysInMonth(year, month) { // month: 1..12
        return new Date(year, month, 0).getDate();
    }

    /* core/datetime_input.py::parse_datetime_text-in əkizi (paritet testi var). */
    function parse(text, options) {
        var requireTime = !options || options.requireTime !== false;
        var value = String(text == null ? "" : text).trim();
        if (!value) {
            return { ok: false, code: "empty" };
        }
        var m = DAY_FIRST_RE.exec(value);
        var year;
        var month;
        var day;
        if (m) {
            day = +m[1];
            month = +m[2];
            year = m[3].length === 2 ? 2000 + (+m[3]) : +m[3];
        } else {
            m = ISO_RE.exec(value);
            if (!m) {
                return { ok: false, code: "invalid" };
            }
            year = +m[1];
            month = +m[2];
            day = +m[3];
        }
        if (year < 1 || month < 1 || month > 12 || day < 1 || day > daysInMonth(year, month)) {
            return { ok: false, code: "invalid_date" };
        }
        if (m[4] === undefined) {
            if (requireTime) {
                return { ok: false, code: "missing_time" };
            }
            return { ok: true, parts: { year: year, month: month, day: day, hour: 0, minute: 0 } };
        }
        var hour = +m[4];
        var minute = +m[5];
        var second = m[6] === undefined ? 0 : +m[6];
        if (hour > 23 || minute > 59 || second > 59) {
            return { ok: false, code: "invalid_time" };
        }
        return { ok: true, parts: { year: year, month: month, day: day, hour: hour, minute: minute } };
    }

    function format(parts) {
        return pad(parts.day) + "." + pad(parts.month) + "." + parts.year + " " +
            pad(parts.hour) + ":" + pad(parts.minute);
    }

    function formatDate(parts) {
        return pad(parts.day) + "." + pad(parts.month) + "." + parts.year;
    }

    function toIso(parts) {
        var year = String(parts.year);
        while (year.length < 4) {
            year = "0" + year;
        }
        return year + "-" + pad(parts.month) + "-" + pad(parts.day);
    }

    /* Ciddi ISO «iiii-aa-gg» → parts (yoxsa null). */
    function isoParts(value) {
        var text = String(value == null ? "" : value).trim();
        if (!ISO_DATE_RE.test(text)) {
            return null;
        }
        var res = parse(text, { requireTime: false });
        return res.ok ? res.parts : null;
    }

    function dayKey(parts) {
        return parts.year * 10000 + parts.month * 100 + parts.day;
    }

    /* Aralıqdan kənardırsa kod («out_of_range» / «before_min» / «after_max»), yoxsa "". */
    function rangeCode(parts, range) {
        if (!parts || !range) {
            return "";
        }
        var key = dayKey(parts);
        var low = !!range.min && key < dayKey(range.min);
        var high = !!range.max && key > dayKey(range.max);
        if (!low && !high) {
            return "";
        }
        if (range.min && range.max) {
            return "out_of_range";
        }
        return low ? "before_min" : "after_max";
    }

    function toDate(parts) {
        return new Date(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, 0, 0);
    }

    /* Server JSON-undakı yerli ISO («2026-10-06T09:30») → sahə dəyəri «06.10.2026 09:30»
       (redaktə modallarının prefill-i üçün); boş → "", oxunmayan → olduğu kimi. */
    function display(value) {
        if (value === null || value === undefined || value === "") {
            return "";
        }
        var res = parse(value);
        return res.ok ? format(res.parts) : String(value);
    }

    /* ── i18n: vidjetin data-ems-dt-i18n JSON-u ── */
    function wrapperOf(el) {
        return el && el.closest ? el.closest("[data-ems-dt]") : null;
    }

    function isDateMode(wrapper) {
        return !!wrapper && wrapper.getAttribute("data-ems-dt-mode") === "date";
    }

    function rangeOf(wrapper) {
        if (!wrapper) {
            return null;
        }
        return {
            min: isoParts(wrapper.getAttribute("data-ems-dt-min")),
            max: isoParts(wrapper.getAttribute("data-ems-dt-max"))
        };
    }

    function texts(wrapper) {
        if (!wrapper) {
            return FALLBACK;
        }
        if (wrapper.__emsDtI18n) {
            return wrapper.__emsDtI18n;
        }
        var base = FALLBACK;
        if (isDateMode(wrapper)) {
            base = {};
            Object.keys(FALLBACK).forEach(function (key) {
                base[key] = FALLBACK_DATE[key] || FALLBACK[key];
            });
        }
        var parsed = null;
        try {
            parsed = JSON.parse(wrapper.getAttribute("data-ems-dt-i18n") || "null");
        } catch (err) {
            parsed = null;
        }
        var merged = {};
        Object.keys(base).forEach(function (key) {
            merged[key] = parsed && parsed[key] ? parsed[key] : base[key];
        });
        wrapper.__emsDtI18n = merged;
        return merged;
    }

    function messageFor(input, code, range) {
        var wrapper = wrapperOf(input);
        var t = texts(wrapper);
        var fallback = isDateMode(wrapper) ? FALLBACK_DATE.errors : FALLBACK.errors;
        var text = (t.errors && t.errors[code]) || fallback[code] || fallback.invalid;
        if (range) {
            text = text.replace("{min}", range.min ? formatDate(range.min) : "")
                .replace("{max}", range.max ? formatDate(range.max) : "");
        }
        return text;
    }

    function validate(input) {
        var wrapper = wrapperOf(input);
        var dateMode = isDateMode(wrapper);
        var result = parse(input ? input.value : "", { requireTime: !dateMode });
        if (dateMode && !result.ok && result.code === "invalid_time") {
            result = { ok: false, code: "invalid" };
        }
        if (result.ok && dateMode) {
            var range = rangeOf(wrapper);
            var outside = rangeCode(result.parts, range);
            if (outside) {
                return {
                    ok: false, empty: false, code: outside, parts: result.parts,
                    message: messageFor(input, outside, range)
                };
            }
        }
        if (result.ok) {
            return { ok: true, empty: false, parts: result.parts, message: "" };
        }
        if (result.code === "empty") {
            return { ok: false, empty: true, code: "empty", message: "" };
        }
        return { ok: false, empty: false, code: result.code, message: messageFor(input, result.code) };
    }

    /* ── sahənin öz xəta mesajı (vidjetin dərhal altında) ──
       `field-error` + `data-ew-transient`: imtahan sehrbazı (exam_wizard.js) bu
       mesajı öz keçici xətası kimi tanıyır — eyni mətn iki dəfə göstərilmir.
       Sahə yan-yana sıradadırsa (`data-ems-dt-row`, məs. tarix + paritet nişanı)
       mesaj sıranın altına düşür. */
    function anchorOf(wrapper) {
        var row = wrapper.parentNode && wrapper.parentNode.closest ?
            wrapper.parentNode.closest("[data-ems-dt-row]") : null;
        return row || wrapper;
    }

    function errorNode(input) {
        var wrapper = wrapperOf(input);
        var anchor = wrapper ? anchorOf(wrapper) : null;
        if (!anchor || !anchor.parentNode) {
            return null;
        }
        return anchor.parentNode.querySelector("[data-ems-dt-error='" + (input.id || input.name) + "']");
    }

    function clearError(input) {
        input.removeAttribute("aria-invalid");
        var wrapper = wrapperOf(input);
        if (wrapper) {
            wrapper.classList.remove("is-invalid");
        }
        var node = errorNode(input);
        if (node && node.parentNode) {
            node.parentNode.removeChild(node);
        }
    }

    function showError(input, message) {
        var wrapper = wrapperOf(input);
        input.setAttribute("aria-invalid", "true");
        if (!wrapper) {
            return;
        }
        wrapper.classList.add("is-invalid");
        var node = errorNode(input);
        if (!node) {
            node = document.createElement("div");
            node.className = "field-error ems-dt__error";
            node.setAttribute("data-ems-dt-error", input.id || input.name);
            node.setAttribute("data-ew-transient", "1");
            node.setAttribute("role", "alert");
            var base = anchorOf(wrapper);
            var hint = base.nextElementSibling;
            var anchor = hint && hint.classList.contains("ems-dt__hint") ? hint : base;
            anchor.parentNode.insertBefore(node, anchor.nextSibling);
        }
        node.textContent = message;
    }

    /* ── yalnız-tarix: gizli ISO sahəsi ilə sinxron ── */
    var nativeDesc = null;

    function nativeValue() {
        if (nativeDesc === null) {
            var proto = window.HTMLInputElement && window.HTMLInputElement.prototype;
            nativeDesc = (proto && Object.getOwnPropertyDescriptor(proto, "value")) || false;
        }
        return nativeDesc;
    }

    function isoField(wrapper) {
        return wrapper ? wrapper.querySelector("[data-ems-dt-iso]") : null;
    }

    function setValidity(input, message) {
        if (input.setCustomValidity) {
            input.setCustomValidity(message || "");
        }
    }

    /* İstifadəçi dəyişikliyi → gizli ISO (dəyişibsə köhnə JS-lər üçün input + change). Native date kimi:
       oxunmayan mətn → "", aralıqdan kənar tarix dəyərini saxlayır (göndərişi customValidity saxlayır). */
    function pushIso(input, res) {
        var iso = isoField(wrapperOf(input));
        setValidity(input, res.ok || res.empty ? "" : res.message);
        if (!iso) {
            return;
        }
        var next = res.parts ? toIso(res.parts) : "";
        var desc = nativeValue();
        var current = desc ? desc.get.call(iso) : iso.value;
        if (current === next) {
            return;
        }
        if (desc) {
            desc.set.call(iso, next);
        } else {
            iso.value = next;
        }
        iso.dispatchEvent(new Event("input", { bubbles: true }));
        iso.dispatchEvent(new Event("change", { bubbles: true }));
    }

    /* Proqram yazısı (gizli sahəyə) → görünən «gg.aa.iiii»; aralıq xətası səssizcə customValidity-yə
       (native date-in min/max davranışı: mesaj göndərişdə — `invalid` hadisəsi). */
    function showFromIso(wrapper) {
        var input = wrapper.querySelector("[data-ems-dt-input]");
        var iso = isoField(wrapper);
        if (!input || !iso) {
            return;
        }
        var parts = isoParts(iso.value);
        input.value = parts ? formatDate(parts) : "";
        clearError(input);
        var res = validate(input);
        setValidity(input, res.ok || res.empty ? "" : res.message);
    }

    function bindDate(wrapper) {
        if (!wrapper || wrapper.__emsDtIsoBound || !isDateMode(wrapper)) {
            return;
        }
        var iso = isoField(wrapper);
        var desc = nativeValue();
        if (!iso || !desc || !desc.set) {
            return;
        }
        wrapper.__emsDtIsoBound = true;
        Object.defineProperty(iso, "value", {
            configurable: true,
            enumerable: true,
            get: function () {
                return desc.get.call(this);
            },
            set: function (value) {
                desc.set.call(this, value);
                showFromIso(wrapper);
            }
        });
        showFromIso(wrapper);
    }

    function bindDates(root) {
        var scope = root && root.querySelectorAll ? root : document;
        Array.prototype.forEach.call(scope.querySelectorAll("[data-ems-dt][data-ems-dt-mode='date']"), bindDate);
    }

    function normalizeInput(input) {
        var res = validate(input);
        var dateMode = isDateMode(wrapperOf(input));
        if (res.ok) {
            var canonical = dateMode ? formatDate(res.parts) : format(res.parts);
            if (input.value !== canonical) {
                input.value = canonical;
            }
            clearError(input);
        } else if (res.empty) {
            clearError(input);
        } else {
            showError(input, res.message);
        }
        if (dateMode) {
            pushIso(input, res);
        }
        return res;
    }

    function writeValue(input, parts) {
        input.value = isDateMode(wrapperOf(input)) ? formatDate(parts) : format(parts);
        clearError(input);
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    /* ── hadisələr (document-ə delegasiya; bir dəfə) ── */
    function onChange(event) {
        var target = event.target;
        if (target && target.hasAttribute && target.hasAttribute("data-ems-dt-input")) {
            normalizeInput(target);
        }
    }

    function onInput(event) {
        var target = event.target;
        if (target && target.hasAttribute && target.hasAttribute("data-ems-dt-input") && event.isTrusted !== false) {
            // Yazarkən köhnə xəta asılı qalmasın; yoxlama blur/change-də.
            if (target.getAttribute("aria-invalid") === "true") {
                clearError(target);
            }
        }
    }

    /* Göndərişdə brauzer customValidity ilə dayandırır — eyni mesaj sahənin altında da görünsün. */
    function onInvalid(event) {
        var target = event.target;
        if (target && target.hasAttribute && target.hasAttribute("data-ems-dt-input")) {
            var res = validate(target);
            if (!res.ok && !res.empty) {
                showError(target, res.message);
            }
        }
    }

    /* `<button type="reset">`: hər iki sahə öz defolt atributuna qayıdır — xəta/validity yenilənsin. */
    function onReset(event) {
        var form = event.target;
        window.setTimeout(function () {
            if (form && form.querySelectorAll) {
                Array.prototype.forEach.call(form.querySelectorAll("[data-ems-dt][data-ems-dt-mode='date']"), showFromIso);
            }
        }, 0);
    }

    function onFocusIn(event) {
        var wrapper = wrapperOf(event.target);
        if (wrapper) {
            bindDate(wrapper);
        }
    }

    if (!window.__emsDateTimeBound) {
        window.__emsDateTimeBound = true;
        document.addEventListener("change", onChange);
        document.addEventListener("input", onInput);
        document.addEventListener("invalid", onInvalid, true);
        document.addEventListener("reset", onReset);
        document.addEventListener("focusin", onFocusIn);
        // Proqram yazıları (modal prefill) istifadəçi toxunmazdan əvvəl gəlir: skript səhifənin sonunda
        // yüklənəndə artıq olan sahələri dərhal, qalanlarını hazır olanda / AJAX swap-dan sonra bağla.
        if (document.querySelectorAll) {
            bindDates(document);
        }
        if (typeof window.EMSReady === "function") {
            window.EMSReady(function () {
                bindDates(document);
            });
        } else if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", function () {
                bindDates(document);
            });
        }
    }

    window.EMSDateTime = {
        __ready: true,
        parse: parse,
        format: format,
        formatDate: formatDate,
        toIso: toIso,
        isoParts: isoParts,
        rangeCode: rangeCode,
        toDate: toDate,
        display: display,
        validate: validate,
        messageFor: messageFor,
        normalize: normalizeInput,
        bindDates: bindDates,
        // ems_datetime_picker.js üçün paylaşılan köməkçilər (ictimai API deyil).
        _internal: {
            pad: pad,
            daysInMonth: daysInMonth,
            texts: texts,
            wrapperOf: wrapperOf,
            writeValue: writeValue,
            isDateMode: isDateMode,
            rangeOf: rangeOf,
            dayKey: dayKey,
            defaultHour: DEFAULT_HOUR
        }
    };
})(window, document);
