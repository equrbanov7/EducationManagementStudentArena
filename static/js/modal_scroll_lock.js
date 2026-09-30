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

/* ── Şkaf / sidebar fon-scroll kilidi — `window.EMSScrollLock` (sahib 2026-09-30) ──
 *
 * Problem: mobil şkaf (burgerMenu.js) və kabinet sidebar-ı (profile/ui.js) açıq
 * ikən içində sürüşdürəndə ARXA səhifə də sürüşürdü. Səbəb: `main.css`-də
 * `html { overflow-x: hidden }` var — belə olanda body-nin `overflow`-u viewport-a
 * ÖTÜRÜLMÜR, əsl scroller `<html>`-dir; şkaflar isə yalnız `body`-ni bağlayırdı.
 *
 * Həll (modal kilidi ilə EYNİ prinsip, ayrıca sinif — bir-birini açmasınlar):
 *   • açarlı sahib sayğacı: `lock(key, konteyner)` / `unlock(key)` / `set(key, on, konteyner)`;
 *   • ilk kilid `<html>`-ə `ems-scroll-locked` qoyur (CSS: html+body overflow:hidden,
 *     overscroll-behavior:none, masaüstündə scrollbar eni qədər boşluq — sıçrayış olmasın);
 *   • iOS Safari (<16 `overflow:hidden`-ə məhəl qoymur) və scroll zəncirlənməsi üçün
 *     touchmove qoruyucusu: toxunuş kilid sahibinin konteynerindən KƏNARDADIRSA və ya
 *     konteyner o istiqamətdə sona çatıbsa hərəkət ləğv olunur (pinch-zoom toxunulmaz);
 *   • səhifənin scroll mövqeyi yadda saxlanır və son kilid açılanda ANİ bərpa olunur.
 *     İstisna: kilid ərzində fokus səhifə məzmununa keçibsə (məs. bölmə keçidində
 *     başlığa fokus → scroll) həmin qəsdən edilmiş sürüşmə saxlanır.
 */
(function () {
    "use strict";

    if (window.EMSScrollLock) {
        return;
    }

    var LOCK_CLASS = "ems-scroll-locked";
    var owners = {};
    var saved = null;
    var lastTouch = null;
    var startOpts = { passive: true, capture: true };
    var moveOpts = { passive: false, capture: true };

    function keys() {
        return Object.keys(owners);
    }

    function canScroll(node, dx, dy) {
        var style = window.getComputedStyle(node);
        if (Math.abs(dy) >= Math.abs(dx)) {
            if (!/(auto|scroll)/.test(style.overflowY) || node.scrollHeight <= node.clientHeight + 1) {
                return false;
            }
            // Barmaq aşağı (dy > 0) → məzmun yuxarı: yuxarıda yer qalıbmı?
            return dy > 0 ? node.scrollTop > 0 : node.scrollTop + node.clientHeight < node.scrollHeight - 1;
        }
        if (!/(auto|scroll)/.test(style.overflowX) || node.scrollWidth <= node.clientWidth + 1) {
            return false;
        }
        return dx > 0 ? node.scrollLeft > 0 : node.scrollLeft + node.clientWidth < node.scrollWidth - 1;
    }

    function allowsTouchScroll(target, dx, dy) {
        var list = keys();
        for (var i = 0; i < list.length; i += 1) {
            var box = owners[list[i]];
            if (!box || !box.contains(target)) {
                continue;
            }
            for (var node = target; node && node.nodeType === 1; node = node.parentElement) {
                if (canScroll(node, dx, dy)) {
                    return true;
                }
                if (node === box) {
                    break;
                }
            }
        }
        return false;
    }

    function onTouchStart(event) {
        var touch = event.touches && event.touches[0];
        lastTouch = touch ? { x: touch.clientX, y: touch.clientY } : null;
    }

    function onTouchMove(event) {
        if (!event.cancelable || !event.touches || event.touches.length !== 1 || !lastTouch) {
            return;
        }
        var touch = event.touches[0];
        var dx = touch.clientX - lastTouch.x;
        var dy = touch.clientY - lastTouch.y;
        lastTouch = { x: touch.clientX, y: touch.clientY };
        if (!allowsTouchScroll(event.target, dx, dy)) {
            event.preventDefault();
        }
    }

    function scrollPos() {
        var root = document.documentElement;
        return { x: window.pageXOffset || root.scrollLeft || 0, y: window.pageYOffset || root.scrollTop || 0 };
    }

    function restore(box) {
        var target = saved;
        saved = null;
        if (!target) {
            return;
        }
        var now = scrollPos();
        if (Math.abs(now.y - target.y) < 1 && Math.abs(now.x - target.x) < 1) {
            return;
        }
        var active = document.activeElement;
        if (active && active !== document.body && box && !box.contains(active)) {
            return; // qəsdən sürüşmə (fokus səhifəyə keçib) — saxla
        }
        var root = document.documentElement;
        var previous = root.style.scrollBehavior;
        root.style.scrollBehavior = "auto"; // html { scroll-behavior: smooth } — bərpa ANİ olsun
        window.scrollTo(target.x, target.y);
        root.style.scrollBehavior = previous;
    }

    function lock(key, container) {
        key = String(key || "default");
        var first = keys().length === 0;
        owners[key] = container || null;
        if (!first) {
            return;
        }
        var root = document.documentElement;
        saved = scrollPos();
        root.style.setProperty("--ems-scroll-lock-gutter", Math.max(0, window.innerWidth - root.clientWidth) + "px");
        root.classList.add(LOCK_CLASS);
        document.addEventListener("touchstart", onTouchStart, startOpts);
        document.addEventListener("touchmove", onTouchMove, moveOpts);
    }

    function unlock(key) {
        key = String(key || "default");
        if (!Object.prototype.hasOwnProperty.call(owners, key)) {
            return;
        }
        var box = owners[key];
        delete owners[key];
        if (keys().length) {
            return;
        }
        var root = document.documentElement;
        root.classList.remove(LOCK_CLASS);
        root.style.removeProperty("--ems-scroll-lock-gutter");
        document.removeEventListener("touchstart", onTouchStart, startOpts);
        document.removeEventListener("touchmove", onTouchMove, moveOpts);
        lastTouch = null;
        restore(box);
    }

    window.EMSScrollLock = {
        lock: lock,
        unlock: unlock,
        set: function (key, on, container) {
            if (on) {
                lock(key, container);
            } else {
                unlock(key);
            }
        },
        isLocked: function () {
            return keys().length > 0;
        },
    };
})();
