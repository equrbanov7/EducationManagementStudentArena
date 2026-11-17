/*
 * exam_score_entry_appeal.js — «İmtahan balının daxil edilməsi»: «Apellyasiya balı» xanası (sahib 2026-11-17).
 *
 * Sahib: «balın yanında appel xanası da olsun, yəni 2 xana. Appelyasiya xanasından gələn bal əsas götürülür.»
 * Server qaydası `apps/registrar/exam_score_appeal.py`-dadır; bu fayl yalnız UX-dir:
 *   · xananın yoxlanması (0..maks tam ədəd, boş = toxunma) və dəyişiklik işarəsi (`is-dirty` / `is-invalid`);
 *   · `window.EMSExamScoreEntryAppeal` — təsdiq dialoqu (`exam_score_entry_confirm.js`) dəyişən apellyasiya
 *     xanalarını oxuyur: sayı xülasəyə düşür və apellyasiya SƏNƏDİ tələb olunur.
 *
 * CSP: inline yoxdur. AJAX-safe: `EMSDelegate` (açar `[data-ese-appeal]` — yalnız burada).
 */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    function inputs(host) {
        return host ? Array.prototype.slice.call(host.querySelectorAll("[data-ese-appeal]")) : [];
    }

    function state(input) {
        var raw = (input.value || "").trim();
        var initial = input.getAttribute("data-initial") || "";
        if (input.disabled || raw === "" || raw === initial) {
            return { dirty: false, invalid: false };
        }
        var max = Number(input.getAttribute("max") || "0");
        var value = Number(raw);
        var ok = /^\d+$/.test(raw) && value >= 0 && value <= max;
        return { dirty: true, invalid: !ok };
    }

    function paint(input) {
        var s = state(input);
        input.classList.toggle("is-dirty", s.dirty && !s.invalid);
        input.classList.toggle("is-invalid", s.invalid);
        if (s.invalid) {
            input.setAttribute("aria-invalid", "true");
        } else {
            input.removeAttribute("aria-invalid");
        }
        return s;
    }

    DELEGATE.on("input", "[data-ese-appeal]", function (event, input) {
        paint(input);
    });

    window.EMSExamScoreEntryAppeal = {
        /* Dəyişən (yazılacaq) xanalar: [{name, old, value}] — etibarsız xana daxil deyil. */
        changes: function (host) {
            var list = [];
            inputs(host).forEach(function (input) {
                var s = paint(input);
                if (s.dirty && !s.invalid) {
                    list.push({
                        name: input.getAttribute("data-student") || "",
                        old: input.getAttribute("data-initial") || "",
                        value: (input.value || "").trim()
                    });
                }
            });
            return list;
        },
        /* İlk etibarsız xana (yoxdursa null). */
        invalid: function (host) {
            var bad = null;
            inputs(host).forEach(function (input) {
                if (!bad && paint(input).invalid) {
                    bad = input;
                }
            });
            return bad;
        },
        reset: function (host) {
            inputs(host).forEach(function (input) {
                input.value = input.getAttribute("data-initial") || "";
                paint(input);
            });
        }
    };
})(window, document);
