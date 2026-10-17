/* Tələbə jurnal bölməsi: köhnə progress-bar enləri (CSP-safe — inline style atributu yox).
   Paket A (2026-10-18): tələbə jurnalı indi native `<progress>` işlədir; bu skript yalnız
   `[data-jd-width]` / `[data-sjx-abs]` saxlayan digər (köhnə) fraqmentlər üçün qalır.
   Əvvəl BÜTÜN kabinetdə `document.body` üzərində subtree MutationObserver işləyirdi (hər DOM
   dəyişikliyində tam sənəd sorğusu) — indi `EMSReady` ilə ilk açılışda + hər bölmə swap-ından
   sonra bir dəfə işləyir (idempotent: `data-jd-filled`). */
(function () {
    "use strict";

    function fill() {
        document.querySelectorAll("[data-jd-width]:not([data-jd-filled])").forEach(function (bar) {
            bar.style.width = bar.getAttribute("data-jd-width") + "%";
            bar.setAttribute("data-jd-filled", "1");
        });
        document.querySelectorAll("[data-sjx-abs]:not([data-jd-filled])").forEach(function (bar) {
            var abs = parseFloat(bar.getAttribute("data-sjx-abs")) || 0;
            var limit = parseFloat(bar.getAttribute("data-sjx-limit")) || 0;
            var pct = limit > 0 ? Math.min(100, Math.round((abs / limit) * 100)) : 0;
            bar.style.width = pct + "%";
            bar.setAttribute("data-jd-filled", "1");
        });
    }

    if (window.EMSReady) {
        window.EMSReady(fill);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", fill);
    } else {
        fill();
    }
})();
