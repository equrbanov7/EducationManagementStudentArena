/* ═══════════════════════════════════════════════════════════════════════════
   change_password_strength.js — «Şifrəni dəyiş» bölməsinin canlı köməkçiləri

   Sahib (2026-09-10): «şifrəni dəyişmək hissəsini tam profesional, modern
   ux/ui prinsipləri əsasında yenidən dizayn et».

   NƏ EDİR
   ────────
   1. Göz düyməsi — şifrə sahəsini müvəqqəti açıq mətnə çevirir.
   2. Güc göstəricisi — yeni şifrənin uzunluğu və simvol müxtəlifliyi.
   3. Tələb siyahısı — sağ sütundakı bəndlər YAZARKƏN yanır/sönür.
   4. Uyğunluq — «təkrarla» sahəsi ilə fərq göndərməmişdən ƏVVƏL bildirilir.
   5. Caps Lock xəbərdarlığı — səhv şifrənin ən çox rast gəlinən səbəbi.

   ⚠️ Tələblər Django validatorlarının EYNİSİdir (bax
   `config/settings/components/security.py`): MinimumLength(8), Numeric,
   UserAttributeSimilarity. `CommonPasswordValidator` brauzerdə yoxlanıla
   bilməz (siyahı serverdədir) — o, şablonda mətnlə xəbərdarlıq kimi verilir.
   Bu qat serveri ƏVƏZ ETMİR, sadəcə səhvi bir addım əvvəl göstərir.

   AJAX-safe: `EMSDelegate` + `EMSReady.once` — bölmə swap olunandan sonra da
   işləyir, təkrar qeydiyyatda dinləyici yığılmır.
   ═══════════════════════════════════════════════════════════════════════════ */
(function (window, document) {
    "use strict";

    var LOWER = /[a-zəöüğışç]/;
    var UPPER = /[A-ZƏÖÜĞİŞÇ]/;
    var DIGIT = /\d/;
    var SYMBOL = /[^0-9A-Za-zƏÖÜĞİŞÇəöüğışç]/;

    /* Tam rəqəm — Django `NumericPasswordValidator`. */
    var ALL_DIGITS = /^\d+$/;

    /* Səviyyə → `data-label-*` açarı. ⚠️ Rəqəmli ad (`data-label-1`) İŞLƏMİR:
       DOM `dataset` yalnız hərfdən əvvəlki defisi silir, ona görə açar
       `dataset["label-1"]` olur və `dataset.label1` boş qayıdır. */
    var LEVEL_KEYS = ["labelNone", "labelWeak", "labelFair", "labelGood", "labelStrong"];

    function field(input) {
        return input && input.closest ? input.closest(".pwfield") : null;
    }

    function rulesCard() {
        return document.querySelector("[data-pw-rules]");
    }

    /* ── 1. Güc ─────────────────────────────────────────────────────────── */
    function strengthOf(value) {
        if (!value) {
            return 0;
        }
        var classes = 0;
        [LOWER, UPPER, DIGIT, SYMBOL].forEach(function (pattern) {
            if (pattern.test(value)) {
                classes += 1;
            }
        });
        if (value.length < 8) {
            return 1; // Server onsuz da rədd edir — «zəif»dən yuxarı qalxmır.
        }
        var score = 1;
        if (value.length >= 12) {
            score += 1;
        }
        if (classes >= 3) {
            score += 1;
        }
        if (classes >= 4 || value.length >= 16) {
            score += 1;
        }
        return Math.min(score, 4);
    }

    function paintStrength(input) {
        var host = field(input);
        if (!host) {
            return;
        }
        var meter = host.querySelector("[data-pw-meter-out]");
        var label = host.querySelector("[data-pw-meter-label]");
        var level = strengthOf(input.value);
        if (meter) {
            meter.setAttribute("data-level", String(level));
        }
        if (label) {
            label.textContent = label.dataset[LEVEL_KEYS[level]] || "";
            label.setAttribute("data-level", String(level));
        }
    }

    /* ── 2. Tələblər ────────────────────────────────────────────────────── */
    function identityTokens(card) {
        return (card.getAttribute("data-pw-identity") || "")
            .toLowerCase()
            .split(/[\s@._-]+/)
            .filter(function (token) {
                return token.length >= 3;
            });
    }

    function looksLikeIdentity(value, tokens) {
        var lowered = value.toLowerCase();
        return tokens.some(function (token) {
            return lowered.indexOf(token) !== -1 || token.indexOf(lowered) !== -1;
        });
    }

    function varietyOk(value) {
        var classes = 0;
        [LOWER, UPPER, DIGIT, SYMBOL].forEach(function (pattern) {
            if (pattern.test(value)) {
                classes += 1;
            }
        });
        return classes >= 3;
    }

    function setRule(card, name, state) {
        var row = card.querySelector('[data-pw-rule="' + name + '"]');
        if (!row) {
            return;
        }
        row.setAttribute("data-state", state);
        var icon = row.querySelector(".pwrule__icon");
        if (!icon) {
            return;
        }
        icon.className = "pwrule__icon fas " + (
            state === "ok" ? "fa-circle-check" : (state === "bad" ? "fa-circle-xmark" : "fa-circle")
        );
    }

    function paintRules(value) {
        var card = rulesCard();
        if (!card) {
            return;
        }
        if (!value) {
            ["length", "numeric", "identity", "variety"].forEach(function (name) {
                setRule(card, name, "idle");
            });
            return;
        }
        var tokens = identityTokens(card);
        setRule(card, "length", value.length >= 8 ? "ok" : "bad");
        setRule(card, "numeric", ALL_DIGITS.test(value) ? "bad" : "ok");
        setRule(card, "identity", looksLikeIdentity(value, tokens) ? "bad" : "ok");
        setRule(card, "variety", varietyOk(value) ? "ok" : "bad");
    }

    /* ── 3. Uyğunluq ────────────────────────────────────────────────────── */
    function firstPasswordValue(panel) {
        var source = panel ? panel.querySelector("[data-pw-meter] input") : null;
        return source ? source.value : "";
    }

    function paintMatch(input) {
        var host = field(input);
        var note = host ? host.querySelector("[data-pw-confirm-note]") : null;
        if (!note) {
            return;
        }
        if (!input.value) {
            note.hidden = true;
            return;
        }
        var panel = input.closest("[data-password-mode-panel]");
        var same = input.value === firstPasswordValue(panel);
        note.hidden = false;
        note.textContent = same ? (note.dataset.labelOk || "") : (note.dataset.labelBad || "");
        note.setAttribute("data-state", same ? "ok" : "bad");
    }

    /* ── 4. Göz düyməsi ─────────────────────────────────────────────────── */
    function toggleReveal(button) {
        var control = button.closest(".pwfield__control");
        var input = control ? control.querySelector("input") : null;
        if (!input) {
            return;
        }
        var shown = input.getAttribute("type") === "text";
        input.setAttribute("type", shown ? "password" : "text");
        button.classList.toggle("is-on", !shown);
        // İkon CARİ VƏZİYYƏTİ göstərir (sahib 2026-09-11): şifrə gizlidirsə
        // üstündən xətt çəkilmiş göz, görünürsə açıq göz. Əvvəl əksinə —
        // «əməl» ikonu — idi və sahibə tərs gəlirdi.
        var icon = button.querySelector("i");
        if (icon) {
            icon.className = shown ? "fas fa-eye-slash" : "fas fa-eye";
        }
        // Fokus sahədə qalsın: göz düyməsi yazı axınını kəsməməlidir.
        input.focus();
    }

    /* ── 5. Caps Lock ───────────────────────────────────────────────────── */
    function paintCaps(input, event) {
        var host = field(input);
        var note = host ? host.querySelector("[data-pw-caps-note]") : null;
        if (!note || typeof event.getModifierState !== "function") {
            return;
        }
        note.hidden = !event.getModifierState("CapsLock");
    }

    window.EMSReady.once("accounts/profile/change_password_strength", function () {
        window.EMSDelegate.on("click", "[data-pw-reveal]", function (event, button) {
            event.preventDefault();
            toggleReveal(button);
        });

        window.EMSDelegate.on("input", "[data-pw-meter] input", function (event, input) {
            paintStrength(input);
            paintRules(input.value);
            var panel = input.closest("[data-password-mode-panel]");
            var confirm = panel ? panel.querySelector("[data-pw-confirm] input") : null;
            if (confirm && confirm.value) {
                paintMatch(confirm);
            }
        });

        window.EMSDelegate.on("input", "[data-pw-confirm] input", function (event, input) {
            paintMatch(input);
        });

        window.EMSDelegate.on("keyup", "[data-pw-caps] input", function (event, input) {
            paintCaps(input, event);
        });
    });

    window.EMSReady(function () {
        // Bound forma ilə qayıdanda (server validasiyası) vəziyyət bərpa olunur.
        var input = document.querySelector("[data-pw-meter] input");
        if (input) {
            paintStrength(input);
            paintRules(input.value);
        }
    });
})(window, document);
