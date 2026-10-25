/*
 * static/js/phone_field.js — telefon sahəsi: ölkə seçicisi + yerli nömrə (sahib 2026-10-25).
 * Markup: templates/partials/_phone_field.html (`{% phone_field %}`); server yoxlaması: core/phone.py.
 *
 * Bu fayl yalnız İPUCUDUR (placeholder, ölkənin avtomatik seçilməsi) — yoxlama və E.164 çevirməsi həmişə
 * serverdədir. Hadisələr SƏNƏDƏ delegə olunub (bir dəfə qoşulur): AJAX ilə gələn və ya JS-lə yaradılan
 * sahələr üçün ayrıca init lazım deyil. `base_auth.html` EMSReady yükləmir — buna görə sadə IIFE.
 */
(function () {
    "use strict";
    if (window.EMSPhoneField) {
        return;
    }

    var DIAL_RE = /^(?:\+|00)\s*([0-9][0-9\s().\-]*)$/;

    function parts(node) {
        var box = node && node.closest ? node.closest("[data-phone-field]") : null;
        if (!box) {
            return null;
        }
        return {
            box: box,
            select: box.querySelector("[data-phone-country]"),
            input: box.querySelector("[data-phone-input]"),
        };
    }

    // Seçilmiş ölkənin nümunəsi xananın placeholder-i olur.
    function syncPlaceholder(box) {
        var p = parts(box.querySelector("[data-phone-input]"));
        if (!p || !p.select || !p.input) {
            return;
        }
        var option = p.select.options[p.select.selectedIndex];
        if (option && option.getAttribute("data-example")) {
            p.input.placeholder = option.getAttribute("data-example");
        }
    }

    // «+90 555 …» və ya «0090 555 …»: ən uzun uyğun zəng kodu (4→1 rəqəm) tapılır, ölkə seçilir, kod xanadan atılır.
    function findDialOption(select, digits) {
        for (var len = Math.min(4, digits.length); len >= 1; len -= 1) {
            var dial = digits.slice(0, len);
            var found = null;
            Array.prototype.forEach.call(select.options, function (option) {
                if (option.getAttribute("data-dial") !== dial) {
                    return;
                }
                if (!found || option.hasAttribute("data-main")) {
                    found = option;
                }
            });
            if (found) {
                return { option: found, length: len };
            }
        }
        return null;
    }

    function detectCountry(input) {
        var p = parts(input);
        if (!p || !p.select) {
            return;
        }
        var match = DIAL_RE.exec(String(input.value || "").trim());
        if (!match) {
            return;
        }
        var digits = match[1].replace(/\D/g, "");
        var hit = findDialOption(p.select, digits);
        if (!hit) {
            return;
        }
        p.select.value = hit.option.value;
        p.select.dispatchEvent(new Event("change", { bubbles: true }));
        input.value = digits.slice(hit.length);
        syncPlaceholder(p.box);
    }

    document.addEventListener("change", function (event) {
        var target = event.target;
        if (!target || !target.matches) {
            return;
        }
        if (target.matches("[data-phone-country]")) {
            var p = parts(target);
            if (p) {
                syncPlaceholder(p.box);
            }
        } else if (target.matches("[data-phone-input]")) {
            detectCountry(target);
        }
    });

    document.addEventListener("paste", function (event) {
        var target = event.target;
        if (target && target.matches && target.matches("[data-phone-input]")) {
            window.setTimeout(function () {
                detectCountry(target);
            }, 0);
        }
    });

    // `form.reset()` seçimi defolta qaytarır, amma «change» buraxmır — placeholder və menyu yenilənsin.
    document.addEventListener("reset", function (event) {
        var form = event.target;
        if (!form || !form.querySelectorAll) {
            return;
        }
        window.setTimeout(function () {
            form.querySelectorAll("[data-phone-field]").forEach(function (box) {
                var select = box.querySelector("[data-phone-country]");
                if (select && window.EMSBootstrapSelect) {
                    window.EMSBootstrapSelect.refresh(select);
                }
                syncPlaceholder(box);
            });
        }, 0);
    });

    // Dinamik qurulan sahə (məs. RİM redaktə paneli) üçün: ölkə + yerli nömrə təyin edir.
    function setValue(box, region, national) {
        var select = box.querySelector("[data-phone-country]");
        var input = box.querySelector("[data-phone-input]");
        if (select && region) {
            select.value = region;
            if (window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.refresh(select);
            }
        }
        if (input) {
            input.value = national || "";
        }
        syncPlaceholder(box);
    }

    window.EMSPhoneField = { sync: syncPlaceholder, detect: detectCountry, set: setValue };
})();
