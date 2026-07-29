/* Panel daxili siyahıda debounce-lu axtarış — PAYLAŞILAN komponent.

   Zal monitorundakı kompüter şəbəkəsi və zallar siyahısındakı "Hazırda gedən
   imtahanlar" paneli eyni davranışı işlədir. Süzgəc tamamilə klient tərəflidir
   — server sorğusu getmir, ona görə canlı yenilənmə (polling) pozulmur.

   Markup müqaviləsi:
     [data-panel-search]              axtarış qutusu
       [data-panel-search-input]      input
       [data-panel-search-count]      "3 / 25" sayğacı (opsional)
     [data-panel-search-scope]        süzüləcək sahə (eyni panelin içində)
       [data-search="…"]              hər süzülən element (kiçik hərflə açar mətn)
       [data-panel-search-empty]      "tapılmadı" mesajı (opsional)

   Bir səhifədə bir neçə panel ola bilər — hər qutu ÖZ panelinin sahəsinə bağlanır. */

(function () {
    "use strict";

    var DEBOUNCE_MS = 180;

    function bind(box) {
        if (box.dataset.panelSearchBound === "1") return; // idempotent (AJAX swap)

        // Sahə həmin panelin içindən götürülür: səhifədə bir neçə panel olanda
        // birinci qutunun ikincinin siyahısını süzməsinin qarşısını alır.
        var panel = box.closest("[data-panel-search-root]") || box.parentNode;
        var scope = panel ? panel.querySelector("[data-panel-search-scope]") : null;
        var input = box.querySelector("[data-panel-search-input]");
        if (!scope || !input) return;

        box.dataset.panelSearchBound = "1";

        var count = box.querySelector("[data-panel-search-count]");
        var empty = scope.querySelector("[data-panel-search-empty]");
        var timer = null;

        function apply() {
            // Elementlər hər dəfə yenidən oxunur: canlı yenilənmə DOM-u əvəz edə bilir.
            var items = scope.querySelectorAll("[data-search]");
            var needle = (input.value || "").trim().toLowerCase();
            var shown = 0;

            for (var i = 0; i < items.length; i++) {
                var item = items[i];
                var hay = item.getAttribute("data-search") || "";
                var match = !needle || hay.indexOf(needle) !== -1;
                item.hidden = !match;
                if (match) shown++;
            }

            if (empty) empty.hidden = shown !== 0;
            if (count) count.textContent = needle ? shown + " / " + items.length : "";
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

    function init() {
        var boxes = document.querySelectorAll("[data-panel-search]");
        for (var i = 0; i < boxes.length; i++) bind(boxes[i]);
    }

    if (window.EMSReady) {
        window.EMSReady(init);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init, { once: true });
    } else {
        init();
    }
})();
