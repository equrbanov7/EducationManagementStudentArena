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

   Seçici dialoqu ayrı fayldadır: static/js/ems_datetime_picker.js (bu fayldan
   SONRA yüklənir; 600 sətir modul limiti).

   API: EMSDateTime.parse(text, {requireTime}) → {ok, parts|code}
        EMSDateTime.format(parts) → "gg.aa.iiii ss:dd"
        EMSDateTime.validate(input) → {ok, empty, code, message, parts}
        EMSDateTime.toDate(parts) → Date (brauzerin yerli vaxtı)
        EMSDateTime.display(isoOrText) → "gg.aa.iiii ss:dd" (modal prefill-i)
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSDateTime && window.EMSDateTime.__ready) {
        return;
    }

    var TIME = "(?:(?:\\s+|\\s*[T,]\\s*)(\\d{1,2})[:.](\\d{2})(?::(\\d{2})(?:\\.\\d+)?)?)?";
    var DAY_FIRST_RE = new RegExp("^(\\d{1,2})[./-](\\d{1,2})[./-](\\d{4}|\\d{2})" + TIME + "$");
    var ISO_RE = new RegExp("^(\\d{4})-(\\d{1,2})-(\\d{1,2})" + TIME + "$");

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

    function texts(wrapper) {
        if (!wrapper) {
            return FALLBACK;
        }
        if (wrapper.__emsDtI18n) {
            return wrapper.__emsDtI18n;
        }
        var parsed = null;
        try {
            parsed = JSON.parse(wrapper.getAttribute("data-ems-dt-i18n") || "null");
        } catch (err) {
            parsed = null;
        }
        var merged = {};
        Object.keys(FALLBACK).forEach(function (key) {
            merged[key] = parsed && parsed[key] ? parsed[key] : FALLBACK[key];
        });
        wrapper.__emsDtI18n = merged;
        return merged;
    }

    function messageFor(input, code) {
        var t = texts(wrapperOf(input));
        return (t.errors && t.errors[code]) || FALLBACK.errors[code] || FALLBACK.errors.invalid;
    }

    function validate(input) {
        var result = parse(input ? input.value : "");
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
       mesajı öz keçici xətası kimi tanıyır — eyni mətn iki dəfə göstərilmir. */
    function errorNode(input) {
        var wrapper = wrapperOf(input);
        if (!wrapper || !wrapper.parentNode) {
            return null;
        }
        return wrapper.parentNode.querySelector("[data-ems-dt-error='" + (input.id || input.name) + "']");
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
            var hint = wrapper.nextElementSibling;
            var anchor = hint && hint.classList.contains("ems-dt__hint") ? hint : wrapper;
            anchor.parentNode.insertBefore(node, anchor.nextSibling);
        }
        node.textContent = message;
    }

    function normalizeInput(input) {
        var res = validate(input);
        if (res.ok) {
            var canonical = format(res.parts);
            if (input.value !== canonical) {
                input.value = canonical;
            }
            clearError(input);
        } else if (res.empty) {
            clearError(input);
        } else {
            showError(input, res.message);
        }
        return res;
    }

    function writeValue(input, parts) {
        input.value = format(parts);
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

    if (!window.__emsDateTimeBound) {
        window.__emsDateTimeBound = true;
        document.addEventListener("change", onChange);
        document.addEventListener("input", onInput);
    }

    window.EMSDateTime = {
        __ready: true,
        parse: parse,
        format: format,
        toDate: toDate,
        display: display,
        validate: validate,
        messageFor: messageFor,
        normalize: normalizeInput,
        // ems_datetime_picker.js üçün paylaşılan köməkçilər (ictimai API deyil).
        _internal: {
            pad: pad,
            daysInMonth: daysInMonth,
            texts: texts,
            wrapperOf: wrapperOf,
            writeValue: writeValue,
            defaultHour: DEFAULT_HOUR
        }
    };
})(window, document);
