/* İmtahan zalı — imtahandan SONRAKI səhifələr üçün tam ekran qapısı (sahib 2026-10-21: «Appelyasiya zamanı da full
   screen açılsın»).

   Mexanizm imtahan nəzarətindəkinin eynisidir (exam_supervision/state.js `_detectCapabilities` /
   `_isFullscreenActive`, event_capture.js `_requestFullscreen` + `fullscreenchange`/`webkitfullscreenchange`):
   `document.documentElement.requestFullscreen()` (yoxdursa `webkitRequestFullscreen`) YALNIZ istifadəçi jesti ilə.
   Brauzer naviqasiyada tam ekranı atır, ona görə səhifə tam ekranda deyilsə «Tam ekranda davam et» örtüyü göstərilir.

   FƏRQ (qəsdən): imtahan bitib — tam ekrandan çıxmaq POZUNTU DEYİL. Bu fayl heç bir şəbəkə sorğusu göndərmir
   (nəzarət / incident endpoint-i yoxdur), sayğac, geri sayım və bloklama yoxdur — yalnız yenidən daxil olmaq üçün
   eyni örtük + «İndilik bağla». Fullscreen API olmayan brauzerdə örtük heç göstərilmir (kilid yoxdur); sorğu
   rədd edilsə də örtük bağlanır və tələbə davam edir.

   Şablon (Django dəyəri data-atributdadır — xarici JS-ə bişirilmir):
     <div data-hall-fullscreen="1">                       ← "1" olmasa skript heç nə etmir
       <div data-hall-fullscreen-overlay hidden>
         <… data-hall-fullscreen-when="start">…</…>       ← ilk açılış mətni
         <… data-hall-fullscreen-when="exit" hidden>…</…> ← tam ekrandan çıxanda
         <button data-hall-fullscreen-enter>…</button>
         <button data-hall-fullscreen-dismiss hidden>…</button>  ← yalnız «exit» halında
   AJAX-safe (window.EMSReady, idempotent), null-safe. API: window.EMSHallFullscreen. */
(function () {
    "use strict";

    var ROOT_SELECTOR = '[data-hall-fullscreen="1"]';
    var REQUEST_TIMEOUT_MS = 2000;

    function isSupported() {
        var el = document.documentElement;
        var hasRequest = !!(
            el &&
            (typeof el.requestFullscreen === "function" || typeof el.webkitRequestFullscreen === "function")
        );
        var enabled = true;
        if (typeof document.fullscreenEnabled === "boolean") {
            enabled = document.fullscreenEnabled;
        } else if (typeof document.webkitFullscreenEnabled === "boolean") {
            enabled = document.webkitFullscreenEnabled;
        }
        return hasRequest && enabled;
    }

    function isActive() {
        return !!(document.fullscreenElement || document.webkitFullscreenElement);
    }

    /** Promise<boolean> — tam ekran alındımı. Heç vaxt rədd olunmur. */
    function request() {
        if (!isSupported()) {
            return Promise.resolve(false);
        }
        try {
            var el = document.documentElement;
            var result = el.requestFullscreen ? el.requestFullscreen() : el.webkitRequestFullscreen();
            if (result && typeof result.then === "function") {
                return result.then(isActive, function () {
                    return false;
                });
            }
            return Promise.resolve(true);
        } catch (e) {
            return Promise.resolve(false);
        }
    }

    function currentRoot() {
        return document.querySelector(ROOT_SELECTOR);
    }

    function overlayOf(root) {
        return root ? root.querySelector("[data-hall-fullscreen-overlay]") : null;
    }

    function show(root, state) {
        var overlay = overlayOf(root);
        if (!overlay) {
            return;
        }
        root.dataset.hallFullscreenState = state;
        overlay.querySelectorAll("[data-hall-fullscreen-when]").forEach(function (node) {
            node.hidden = node.getAttribute("data-hall-fullscreen-when") !== state;
        });
        var dismiss = overlay.querySelector("[data-hall-fullscreen-dismiss]");
        if (dismiss) {
            dismiss.hidden = state !== "exit";
        }
        overlay.hidden = false;
        var enter = overlay.querySelector("[data-hall-fullscreen-enter]");
        if (enter && typeof enter.focus === "function") {
            try {
                enter.focus();
            } catch (e) {
                /* fokus vacib deyil */
            }
        }
    }

    function hide(root, state) {
        var overlay = overlayOf(root);
        if (overlay) {
            overlay.hidden = true;
        }
        if (root) {
            root.dataset.hallFullscreenState = state;
        }
    }

    var leaving = false;

    function onFullscreenChange() {
        var root = currentRoot();
        if (!root || root.dataset.hallFullscreenBound !== "1" || leaving) {
            return;
        }
        if (isActive()) {
            hide(root, "active");
        } else {
            show(root, "exit");
        }
    }

    var documentBound = false;

    function bindDocument() {
        if (documentBound) {
            return;
        }
        documentBound = true;
        document.addEventListener("fullscreenchange", onFullscreenChange);
        document.addEventListener("webkitfullscreenchange", onFullscreenChange);
        // Göndəriş / dil dəyişimi səhifəni tərk edir — brauzerin tam ekrandan çıxışı örtüyü yenidən açmasın.
        window.addEventListener("pagehide", function () {
            leaving = true;
        });
        window.addEventListener("pageshow", function () {
            leaving = false;
        });
    }

    function init() {
        var root = currentRoot();
        if (!root || root.dataset.hallFullscreenBound === "1") {
            return;
        }
        var overlay = overlayOf(root);
        if (!overlay) {
            return;
        }
        root.dataset.hallFullscreenBound = "1";
        if (!isSupported()) {
            // Köhnə brauzer / iOS / icazəsiz iframe: kilid yoxdur — səhifə adi rejimdə işləyir.
            hide(root, "unsupported");
            return;
        }
        bindDocument();

        var enter = overlay.querySelector("[data-hall-fullscreen-enter]");
        var pending = false;
        if (enter) {
            enter.addEventListener("click", function () {
                if (pending) {
                    return;
                }
                pending = true;
                // Bəzi daxili brauzerlər (kiosk / webview) sorğunu heç vaxt həll etmir — örtük əbədi qalmasın.
                var settle = new Promise(function (resolve) {
                    window.setTimeout(function () {
                        resolve(false);
                    }, REQUEST_TIMEOUT_MS);
                });
                Promise.race([request(), settle]).then(function (ok) {
                    pending = false;
                    // Rədd olunsa da örtük bağlanır — imtahan bitib, tələbəni kilidləmirik.
                    hide(root, ok || isActive() ? "active" : "failed");
                });
            });
        }
        var dismiss = overlay.querySelector("[data-hall-fullscreen-dismiss]");
        if (dismiss) {
            dismiss.addEventListener("click", function () {
                hide(root, "dismissed");
            });
        }

        if (isActive()) {
            hide(root, "active");
        } else {
            show(root, "start");
        }
    }

    window.EMSHallFullscreen = {
        isSupported: isSupported,
        isActive: isActive,
        request: request,
        init: init,
    };

    if (typeof window.EMSReady === "function") {
        window.EMSReady(init);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
