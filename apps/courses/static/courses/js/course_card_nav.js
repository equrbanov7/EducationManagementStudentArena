/*
 * courses/js/course_card_nav.js — «Kurslarım» kartından kurs panelinə keçid skeleti (2026-09-28).
 *
 * Kurs paneli tam səhifədir (AJAX bölmə deyil). Brauzer yeni səhifəni gətirənə
 * qədər köhnə kart şəbəkəsi donuq qalırdı — istifadəçi kliklə nəticə arasında
 * heç bir əks-əlaqə görmürdü. İndi adi (modifikatorsuz) klikdə şəbəkə gizlənir və
 * panelin formasında skelet (`[data-mc-nav-skeleton]`) göstərilir. Geri
 * qayıdanda (bfcache `pageshow.persisted`) vəziyyət bərpa olunur.
 * AJAX-safe: document səviyyəsində bir dəfə delegə olunur.
 */
(function () {
    "use strict";

    if (window.__emsCourseCardNav) {
        return;
    }
    window.__emsCourseCardNav = true;

    function panelOf(card) {
        return card.closest("[data-profile-section-panel]") || document;
    }

    function restore() {
        document.querySelectorAll("[data-mc-grid].is-navigating").forEach(function (grid) {
            grid.classList.remove("is-navigating");
            grid.hidden = false;
            var sk = panelOf(grid).querySelector("[data-mc-nav-skeleton]");
            if (sk) {
                sk.hidden = true;
            }
        });
    }

    document.addEventListener("click", function (event) {
        var card = event.target.closest && event.target.closest("[data-mc-card]");
        if (!card || event.defaultPrevented) {
            return;
        }
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return; // yeni tab / pəncərə — cari səhifə dəyişmir
        }
        var grid = card.closest("[data-mc-grid]");
        var sk = panelOf(card).querySelector("[data-mc-nav-skeleton]");
        if (!grid || !sk) {
            return;
        }
        grid.classList.add("is-navigating");
        grid.hidden = true;
        sk.hidden = false;
        window.scrollTo({ top: 0, behavior: "auto" });
    });

    window.addEventListener("pageshow", function (event) {
        if (event.persisted) {
            restore();
        }
    });
})();
