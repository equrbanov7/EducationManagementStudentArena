/* Qlobal modal arxa-fon scroll kilidi (bütün Bootstrap modallar).
 *
 * Problem: SPA-scroll kontekstlərində səhifənin əsl scroller-i `<html>`-dir və
 * Bootstrap-ın `body.modal-open`-u fonu tam saxlamır — modal açıq ikən arxa
 * səhifə siçan təkəri ilə sürüşürdü (əvvəl eyni düzəliş yalnız imtahan
 * sehrbazında idi: html.exam-modal-open, 2026-08-01).
 *
 * Həll: İSTƏNİLƏN modalın shown/hidden hadisələri `<html>`-ə `ems-modal-open`
 * sinfini qoyur/çıxarır (CSS: static/css/modal_scroll_lock.css). Sinif yalnız
 * SƏHİFƏ scroll-unu bağlayır — `.modal` konteynerinin öz `overflow-y:auto`-su
 * (daxili scroll) toxunulmaz qalır, modal içində scroll İLİŞMİR.
 *
 * Sayğac əvəzinə DOM-dan yenidən hesablanır (self-healing): hansısa modal
 * qeyri-standart bağlansa belə kilid asılı qalmır.
 */
(function () {
    "use strict";

    if (window.__emsModalScrollLock) {
        return;
    }
    window.__emsModalScrollLock = true;

    function syncLock() {
        var anyOpen = document.querySelector(".modal.show") !== null;
        document.documentElement.classList.toggle("ems-modal-open", anyOpen);
    }

    document.addEventListener("shown.bs.modal", syncLock);
    document.addEventListener("hidden.bs.modal", syncLock);
    // SPA fraqment swap-ı açıq modalı hidden hadisəsi olmadan DOM-dan çıxara
    // bilər — kilid asılı qalmasın deyə swap-dan sonra yenidən hesabla.
    document.addEventListener("profile:section:loaded", syncLock);
})();
