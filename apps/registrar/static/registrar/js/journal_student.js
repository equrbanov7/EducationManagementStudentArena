/* Tələbə jurnal bölməsi: progress-bar enləri (CSP-safe — inline style yox).
   Profil SPA bölməsi AJAX ilə yenilənə bildiyi üçün MutationObserver ilə
   yeni gələn elementlər də doldurulur. */
(function () {
    "use strict";

    function fill(root) {
        (root.querySelectorAll ? root : document)
            .querySelectorAll("[data-jd-width]:not([data-jd-filled])")
            .forEach(function (bar) {
                bar.style.width = bar.getAttribute("data-jd-width") + "%";
                bar.setAttribute("data-jd-filled", "1");
            });
        (root.querySelectorAll ? root : document)
            .querySelectorAll("[data-sjx-abs]:not([data-jd-filled])")
            .forEach(function (bar) {
                var abs = parseFloat(bar.getAttribute("data-sjx-abs")) || 0;
                var limit = parseFloat(bar.getAttribute("data-sjx-limit")) || 0;
                var pct = limit > 0 ? Math.min(100, Math.round((abs / limit) * 100)) : 0;
                bar.style.width = pct + "%";
                bar.setAttribute("data-jd-filled", "1");
            });
    }

    fill(document);
    new MutationObserver(function () {
        fill(document);
    }).observe(document.body, { childList: true, subtree: true });
})();
