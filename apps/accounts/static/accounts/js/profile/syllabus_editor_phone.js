/* ═══════════════════════════════════════════════════════════════════════════
   Sillabus redaktoru — TELEFON naviqasiyası (≤ 768px, 2026-10-19)
   ───────────────────────────────────────────────────────────────────────────
   • Addım menyusu: `[data-syl-steps-toggle]` `[data-syl-steps]`-ə `.is-open` verir
     (`aria-expanded` ilə); addım seçiləndə, menyudan kənar klikdə və Escape-də bağlanır.
   • Sayğac: aktiv addım dəyişəndə (`syllabus_editor.js` `.syl-step.is-on`-u dəyişir)
     bütün `[data-syl-step-count]` «3/9», `[data-syl-step-current]` addımın adını göstərir.
     Mühərrikə toxunulmur — dəyişiklik `MutationObserver` ilə izlənir.
   Masaüstündə düymə CSS ilə gizlidir; skript zərərsizdir (menyu orada açılmır).

   AJAX-safe (docs/frontend/AJAX_SAFE_JS_PATTERN.md): kliklər `EMSDelegate` ilə
   `document`-ə bir dəfə bağlanır; `EMSReady` hər swap-da null-safe və idempotent
   işləyir (observer elementə bir dəfə qoşulur).
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    "use strict";

    function editor() {
        return document.querySelector("[data-syllabus-editor]");
    }

    function stepLabel(button) {
        var label = button.querySelector(".syl-step__label");
        var text = label ? label.textContent : button.textContent;
        /* «3. Təlim nəticələri» → «Təlim nəticələri» (nömrə sayğacdadır). */
        return String(text || "").replace(/^\s*\d+\.\s*/, "").trim();
    }

    function paint(el) {
        if (!el) {
            return;
        }
        var steps = Array.prototype.slice.call(el.querySelectorAll(".syl-step[data-syl-step]"));
        if (!steps.length) {
            return;
        }
        var index = 0;
        steps.forEach(function (button, position) {
            if (button.classList.contains("is-on")) {
                index = position;
            }
        });
        var count = index + 1 + "/" + steps.length;
        el.querySelectorAll("[data-syl-step-count]").forEach(function (node) {
            if (node.textContent !== count) {
                node.textContent = count;
            }
        });
        var label = stepLabel(steps[index]);
        el.querySelectorAll("[data-syl-step-current]").forEach(function (node) {
            if (node.textContent !== label) {
                node.textContent = label;
            }
        });
    }

    function setOpen(nav, open) {
        if (!nav) {
            return;
        }
        nav.classList.toggle("is-open", open);
        var toggle = nav.querySelector("[data-syl-steps-toggle]");
        if (toggle) {
            toggle.setAttribute("aria-expanded", open ? "true" : "false");
        }
    }

    function init() {
        var el = editor();
        if (!el) {
            return;
        }
        paint(el);
        var list = el.querySelector(".syl-steps__list");
        if (!list || list.__sylPhoneObserved || typeof window.MutationObserver !== "function") {
            return;
        }
        list.__sylPhoneObserved = true;
        new window.MutationObserver(function () {
            paint(editor());
        }).observe(list, { attributes: true, attributeFilter: ["class"], subtree: true });
    }

    function bindOnce() {
        if (window.__emsSyllabusPhoneBound || !window.EMSDelegate) {
            return;
        }
        window.__emsSyllabusPhoneBound = true;

        window.EMSDelegate.on("click", "[data-syl-steps-toggle]", function (event, toggle) {
            var nav = toggle.closest("[data-syl-steps]");
            setOpen(nav, !(nav && nav.classList.contains("is-open")));
        });
        /* Addım seçildi (mühərrik keçidi özü edir) → menyu bağlanır. */
        window.EMSDelegate.on("click", "[data-syl-steps] .syl-step", function (event, button) {
            setOpen(button.closest("[data-syl-steps]"), false);
        });
        document.addEventListener("click", function (event) {
            var nav = document.querySelector("[data-syl-steps].is-open");
            if (nav && !nav.contains(event.target)) {
                setOpen(nav, false);
            }
        });
        document.addEventListener("keydown", function (event) {
            if (event.key !== "Escape") {
                return;
            }
            var nav = document.querySelector("[data-syl-steps].is-open");
            if (nav) {
                setOpen(nav, false);
                var toggle = nav.querySelector("[data-syl-steps-toggle]");
                if (toggle && typeof toggle.focus === "function") {
                    toggle.focus();
                }
            }
        });
    }

    bindOnce();
    if (typeof window.EMSReady === "function") {
        window.EMSReady(init);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
