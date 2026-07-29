/* Zal nəzarəti — kompüter siyahısında debounce-lu axtarış.

   25+ kompüterli zalda siyahını gözlə tapmaq çətindir; burada ad, MAC, IP,
   yer nömrəsi və (məşğuldursa) tələbə/imtahan adı üzrə süzgəc var. Süzgəc
   tamamilə klient tərəflidir — server sorğusu getmir, ona görə canlı
   yenilənmə (polling) pozulmur. */

(function () {
    "use strict";

    var DEBOUNCE_MS = 180;

    function init() {
        var box = document.querySelector("[data-rma-csearch]");
        var scroll = document.querySelector("[data-rma-cscroll]");
        if (!box || !scroll) return;
        if (box.dataset.rmaBound === "1") return; // idempotent (AJAX swap)
        box.dataset.rmaBound = "1";

        var input = box.querySelector("[data-rma-csearch-input]");
        var count = box.querySelector("[data-rma-csearch-count]");
        var empty = scroll.querySelector("[data-rma-csearch-empty]");
        if (!input) return;

        var timer = null;

        function apply() {
            // Kartlar hər dəfə yenidən oxunur: canlı yenilənmə DOM-u əvəz edə bilir.
            var cards = scroll.querySelectorAll("[data-rma-comp]");
            var needle = (input.value || "").trim().toLowerCase();
            var shown = 0;

            for (var i = 0; i < cards.length; i++) {
                var card = cards[i];
                var hay = card.getAttribute("data-search") || "";
                var match = !needle || hay.indexOf(needle) !== -1;
                card.hidden = !match;
                if (match) shown++;
            }

            if (empty) empty.hidden = shown !== 0;
            if (count) {
                count.textContent = needle ? shown + " / " + cards.length : "";
            }
        }

        input.addEventListener("input", function () {
            if (timer) clearTimeout(timer);
            timer = setTimeout(apply, DEBOUNCE_MS);
        });

        // Escape ilə süzgəci sıfırla.
        input.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && input.value) {
                input.value = "";
                apply();
            }
        });
    }

    if (window.EMSReady) {
        window.EMSReady(init);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init, { once: true });
    } else {
        init();
    }
})();
