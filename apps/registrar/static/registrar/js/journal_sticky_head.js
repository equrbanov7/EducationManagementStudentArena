/* ═══════════════════════════════════════════════════════════════════════════
   Jurnal — yapışqan başlıq sətri, daxili şaquli scroll OLMADAN (2026-10-19)
   ───────────────────────────────────────────────────────────────────────────
   `.jd2-grid-wrap` üfüqi sürüşür (`overflow-x: auto`) — bu, onu şaquli istiqamətdə də
   sürüşmə konteyneri edir və `thead th { position: sticky; top: 0 }` səhifə sürüşəndə
   işləmir. Qutuya `max-height` vermək sahibin qərarına ziddir («jurnalın içində scroll
   olmasın», 2026-09-06 — `journal_layout.css` ⚠️ qeydi). Bu skript başlıq xanalarını
   səhifə sürüşdükcə ekranın yuxarısında saxlayır: hər görünən cədvəlin `thead`-inə
   `--jd-head-y` (px) yazır, CSS `thead th { translate: 0 var(--jd-head-y) }` edir.

   • Klon YOXDUR — «i/e · q/b», tarix və redaktə düymələri eyni elementlərdir.
   • Ad sütunu (`left: 0`) toxunulmur; üfüqi sürüşmə qutunun içində qalır.
   • Başlıq cədvəldən kənara çıxmır (son sətirlərdə dayanır).
   • Yapışqan sayt başlığı varsa (fixed / sticky və ekranda) onun altında dayanır.
   • Ölçü yalnız `scroll` / `resize` / klikdən sonra `requestAnimationFrame` ilə — bir kadrda
     bir oxu-yazı dövrü; dəyər dəyişməyibsə yazılmır (stil yenidən hesablanmır).
   CSP: inline kod yoxdur; yalnız CSSOM (`style.setProperty`).
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    "use strict";

    var GRID = "[data-journal-grid]";
    var queued = false;

    function siteHeaderBottom() {
        var header = document.querySelector(".blog-header");
        if (!header) {
            return 0;
        }
        var position = window.getComputedStyle(header).position;
        if (position !== "fixed" && position !== "sticky") {
            return 0;
        }
        var rect = header.getBoundingClientRect();
        return rect.top <= 1 && rect.bottom > 0 ? rect.bottom : 0;
    }

    function update() {
        queued = false;
        var top = siteHeaderBottom();
        document.querySelectorAll(GRID).forEach(function (wrap) {
            var table = wrap.querySelector(":scope > table");
            var thead = table ? table.querySelector(":scope > thead") : null;
            if (!thead) {
                return;
            }
            var rect = table.getBoundingClientRect();
            var y = 0;
            if (rect.height > 0 && rect.top < top) {
                var room = rect.height - thead.offsetHeight * 2;
                y = Math.max(0, Math.min(top - rect.top, room));
            }
            y = Math.round(y);
            var value = y + "px";
            if (thead.style.getPropertyValue("--jd-head-y") !== value) {
                thead.style.setProperty("--jd-head-y", value);
            }
            thead.classList.toggle("is-floating", y > 0);
        });
    }

    function schedule() {
        if (queued) {
            return;
        }
        queued = true;
        window.requestAnimationFrame(update);
    }

    function bindOnce() {
        if (window.__emsJournalStickyHead) {
            return;
        }
        window.__emsJournalStickyHead = true;
        window.addEventListener("scroll", schedule, { passive: true });
        window.addEventListener("resize", schedule, { passive: true });
        /* Tab / pəncərə keçidi, sətir əlavəsi — ölçü dəyişə bilər. */
        document.addEventListener("click", schedule, true);
        document.addEventListener("profile:section:loaded", schedule);
    }

    if (typeof window.requestAnimationFrame !== "function") {
        return;
    }
    bindOnce();
    if (typeof window.EMSReady === "function") {
        window.EMSReady(schedule);
    } else {
        schedule();
    }
})();
