/* İmtahan dili — məcburi addımın xəta vəziyyəti (sahib 2026-11-06; şablon: _language_step.html).
 *
 * `[data-language-step-form]` formasında çoxdilli `[data-language-step]` varsa və heç bir dil seçilməyibsə
 * forma göndərilmir: addım qırmızı olur, «dil seçin» mesajı görünür, addım görünən sahəyə sürüşür və
 * ilk variant fokuslanır. Dil seçiləndə xəta təmizlənir. Server də eyni qaydanı yoxlayır.
 * AJAX-safe: yalnız document səviyyəli `EMSDelegate` (gələcək swap-lar da tutulur).
 */
(function (window) {
    "use strict";

    function stepOf(node) {
        return node && node.querySelector ? node.querySelector("[data-language-step]") : null;
    }

    function setError(step, show) {
        if (!step) return;
        var error = step.querySelector("[data-language-step-error]");
        var text = step.querySelector("[data-language-step-error-text]");
        step.classList.toggle("is-invalid", Boolean(show));
        if (error) {
            if (show && text && !text.textContent.trim()) {
                text.textContent = error.getAttribute("data-default-message") || "";
            }
            error.hidden = !show;
        }
    }

    function hasChoice(step) {
        return Boolean(step.querySelector('input[name="language"]:checked'));
    }

    function flagMissing(step) {
        setError(step, true);
        step.classList.remove("is-shaking");
        // Animasiyanı yenidən işə salmaq üçün reflow.
        void step.offsetWidth;
        step.classList.add("is-shaking");
        if (typeof step.scrollIntoView === "function") {
            step.scrollIntoView({ behavior: "smooth", block: "center" });
        }
        var first = step.querySelector('input[name="language"]');
        if (first) first.focus({ preventScroll: true });
    }

    window.EMSReady.once("exam-language-step", function () {
        window.EMSDelegate.on("submit", "[data-language-step-form]", function (event, form) {
            var step = stepOf(form);
            if (!step || hasChoice(step)) return;
            // «Geri» kimi `formnovalidate` düymələri dilsiz də göndərilir.
            if (event.submitter && event.submitter.hasAttribute("formnovalidate")) return;
            event.preventDefault();
            flagMissing(step);
        });
        // Brauzerin öz `required` balonu formanı əvvəlcədən dayandırır — eyni vəziyyəti göstər.
        document.addEventListener(
            "invalid",
            function (event) {
                var input = event.target;
                if (!input || input.name !== "language" || !input.closest) return;
                var step = input.closest("[data-language-step]");
                if (!step) return;
                event.preventDefault();
                flagMissing(step);
            },
            true
        );
        window.EMSDelegate.on("change", '[data-language-step] input[name="language"]', function (event, input) {
            var step = input.closest("[data-language-step]");
            setError(step, false);
            if (step) step.classList.remove("is-shaking");
        });
    });

    window.EMSLanguageStep = { flagMissing: flagMissing, clear: function (step) { setError(step, false); } };
})(window);
