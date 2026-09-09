/* ═══════════════════════════════════════════════════════════════════════════
   pagination.js — səhifə keçidləri

   ⚠️ 2026-09-09 YENİDƏN YAZILDI (sahib: «səhifə dəyişərkən belə bir problem
   olur» — ekranın altında stilsiz markup görünürdü).

   Köhnə davranışın İKİ problemi var idi:

   1) `DOMContentLoaded` + hər linkə ayrıca `addEventListener` — layihənin
      qadağan etdiyi naxış (bax docs/frontend/AJAX_SAFE_JS_PATTERN.md). Bölmə
      AJAX ilə dəyişəndə yeni linklər ÇILPAQ qalırdı, panel iki dəfə
      yüklənəndə isə eyni link iki dəfə bağlanırdı.
   2) `preventDefault()` + 400 ms `setTimeout` → `location.href`. Həmin 400 ms
      ərzində səhifə hələ köhnə sənəddir; istifadəçi ikinci dəfə klikləyə
      bilir və brauzer iki naviqasiya növbəyə qoyur. Tam səhifə yüklənməsi isə
      bölmə CSS-i `<body>`-dən gəldiyi üçün (AJAX partial konvensiyası) qısa
      müddət STİLSİZ məzmun göstərir.

   İndi:
   * hadisə DELEGASİYA ilə tutulur (`EMSDelegate`) — swap-dan sonra da işləyir;
   * kabinet bölməsinin İÇİNDƏKİ səhifələmə tam səhifəni yeniləmir, yalnız
     paneli SPA ilə dəyişir (`EMSProfileLoadSection`) — stilsiz an ümumiyyətlə
     yaranmır, sol sidebar yerində qalır;
   * kabinetdən kənarda link normal işləyir, süni 400 ms gecikmə YOXDUR;
     yuxarı sürüşdürmə naviqasiyanı gözlətmir.
   ═══════════════════════════════════════════════════════════════════════════ */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    function modifiedClick(event) {
        return event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;
    }

    function scrollTop() {
        var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        try {
            window.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
        } catch (err) {
            window.scrollTo(0, 0);
        }
    }

    /* Kabinet paneli: `?section=` və `data-source-url` panelin öz atributlarındadır. */
    function panelOf(link) {
        return link.closest ? link.closest("[data-profile-section-panel]") : null;
    }

    DELEGATE.on("click", ".pagination a.page-link", function (event, link) {
        if (modifiedClick(event)) {
            return;
        }
        var href = link.getAttribute("href") || "";
        if (!href || href.charAt(0) === "#") {
            return;
        }

        var panel = panelOf(link);
        var section = panel ? panel.getAttribute("data-profile-section-panel") : "";
        if (section && typeof window.EMSProfileLoadSection === "function") {
            // SPA yolu: yalnız panel dəyişir — tam səhifə render olunmur.
            event.preventDefault();
            var url = new URL(href, window.location.href);
            url.searchParams.set("section", section);
            window.EMSProfileLoadSection(section, url.pathname + url.search);
            scrollTop();
            return;
        }

        // Kabinetdən kənar: linkin öz davranışı qalır, sadəcə yuxarı sürüşdürülür.
        scrollTop();
    });
})(window, document);
