/* ═══════════════════════════════════════════════════════════════════════════
   Sillabus — TAM SƏHİFƏ sənədinin davranışı.

   Səhifə server-render olunur; JS-in yeganə işi iki xırda addımdır:
     * tamamlanma zolağının enini `data-syl-percent`-dən boyamaq,
     * «Çap et» düyməsini brauzerin çap dialoquna bağlamaq.

   Mətn YOXDUR (xarici .js Django template engine-dən keçmir), dinamik dəyər
   yalnız `data-*` atributundan oxunur. AJAX-safe naxış: `EMSDelegate` +
   `EMSReady` — səhifə profil qabığından kənar olsa da eyni qayda saxlanılır.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    "use strict";

    function root() {
        return document.querySelector("[data-syllabus-detail]");
    }

    function paintBars(el) {
        el.querySelectorAll("[data-syl-percent]").forEach(function (node) {
            var percent = parseInt(node.getAttribute("data-syl-percent"), 10) || 0;
            node.style.width = Math.max(0, Math.min(percent, 100)) + "%";
        });
    }

    function bindOnce() {
        if (!window.EMSDelegate || window.__emsSyllabusDetailBound) {
            return;
        }
        window.__emsSyllabusDetailBound = true;
        window.EMSDelegate.on("click", "[data-syllabus-detail] [data-syl-print]", function () {
            window.print();
        });
    }

    window.EMSReady(function () {
        bindOnce();
        var el = root();
        if (!el) {
            return;
        }
        paintBars(el);
    });
})();
