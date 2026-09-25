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

    // 2026-09-26 (sahib: «açılan modalları scroll edəndə arxası da scroll gedir»): kilid
    // yalnız Bootstrap/ems-overlay-i tanıyırdı — jurnalın `jd-modal`-ları (hidden atributu),
    // native `<dialog open>` və digər `aria-modal="true"` pəncərələri kənarda qalırdı.
    // İndi GÖRÜNƏN istənilən modal kilidi saxlayır; dəyişiklik MutationObserver ilə
    // (hidden/open/class/style) tutulur, bir kadrda bir dəfə hesablanır.
    var MODAL_SELECTOR = [
        ".modal.show",
        ".ems-overlay:not([hidden])",
        "dialog[open]",
        '[aria-modal="true"]',
    ].join(",");

    // «Görünən» = render olunur VƏ gizlədilməyib. Bağlı modallar tez-tez DOM-da qalır və
    // `visibility:hidden` + `aria-hidden="true"` ilə gizlənir (məs. kurs yaratma modalı) —
    // bunlar kilid SAYILMAMALIDIR, əks halda səhifə scroll-u həmişəlik bağlanır (2026-09-26
    // baq). Opaklıq yoxlanmır: açılış animasiyası 0-dan başlayır, kilid gecikməsin.
    function isVisible(el) {
        if (el.closest('[aria-hidden="true"], [inert]')) {
            return false;
        }
        if (typeof el.checkVisibility === "function") {
            return el.checkVisibility({ checkVisibilityCSS: true });
        }
        return el.getClientRects().length > 0 && window.getComputedStyle(el).visibility !== "hidden";
    }

    function syncLock() {
        var anyOpen = false;
        var candidates = document.querySelectorAll(MODAL_SELECTOR);
        for (var i = 0; i < candidates.length; i += 1) {
            if (isVisible(candidates[i])) {
                anyOpen = true;
                break;
            }
        }
        document.documentElement.classList.toggle("ems-modal-open", anyOpen);
        // Bölmə AJAX ilə yenilənəndə açıq overlay DOM-la birlikdə itir və
        // `overlay.js`-in unlockScroll-u çağırılmır — kilid burada da düşsün.
        if (!anyOpen) {
            document.body.classList.remove("modal-open");
        }
    }

    var scheduled = false;
    function scheduleSync() {
        if (scheduled) {
            return;
        }
        scheduled = true;
        // rAF fon tabında dayanır — setTimeout hər halda işləyir (bir dövrədə bir hesab).
        window.setTimeout(function () {
            scheduled = false;
            syncLock();
        }, 16);
    }

    document.addEventListener("shown.bs.modal", syncLock);
    document.addEventListener("hidden.bs.modal", syncLock);
    // SPA fraqment swap-ı açıq modalı hidden hadisəsi olmadan DOM-dan çıxara
    // bilər — kilid asılı qalmasın deyə swap-dan sonra yenidən hesabla.
    document.addEventListener("profile:section:loaded", syncLock);

    // Bağlanış animasiyası bitəndə (visibility keçidi transition sonunda dəyişir) atribut
    // mutasiyası olmur — kilid asılı qalmasın deyə transition/animation sonunda da hesabla.
    document.addEventListener("transitionend", scheduleSync, true);
    document.addEventListener("animationend", scheduleSync, true);

    function observe() {
        if (!document.body || typeof MutationObserver === "undefined") {
            return;
        }
        new MutationObserver(scheduleSync).observe(document.body, {
            subtree: true,
            childList: true,
            attributes: true,
            attributeFilter: ["hidden", "open", "class", "style", "aria-hidden"],
        });
        scheduleSync();
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", observe);
    } else {
        observe();
    }
})();
