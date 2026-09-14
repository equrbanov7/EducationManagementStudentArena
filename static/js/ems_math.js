/* =========================================================================
   ems_math.js — sual mətnindəki LaTeX düsturlarını KaTeX ilə render edir.

   W3 2026-09-14 (sahibin istəyi: «şəkil və düstur olanda problem yaranmasın»).
   Düstur bazada MƏTN kimi saxlanır (`$…$`, `$$…$$`, `\(…\)`, `\[…\]`); HTML
   Django tərəfindən escape olunur, KaTeX yalnız mətn düyünlərini oxuyur —
   XSS səthi yoxdur (`trust:false`, `throwOnError:false`).

   Yalnız `[data-ems-math]` konteynerlərinin içi render olunur. AJAX ilə
   dəyişən bölmələr (kabinet, imtahanın «strict delivery» sual gövdəsi) üçün
   `EMSReady` + `MutationObserver` təkrar işə salır. Konteynerə bir dəfə
   `data-ems-math-done="1"` yazılır — idempotent, null-safe.

   Yüklənmə: `templates/partials/ems_ui/_math_assets.html` (katex.min.js,
   auto-render.min.js, bu fayl — hamısı `defer`, CSP-safe, CDN yoxdur).
   ========================================================================= */
(function () {
    "use strict";

    if (window.EMSMath && window.EMSMath.__loaded) {
        return;
    }

    var DELIMITERS = [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "\\(", right: "\\)", display: false }
    ];
    var SINGLE_DOLLAR = { left: "$", right: "$", display: false };
    var OPTIONS = {
        delimiters: DELIMITERS,
        throwOnError: false,
        trust: false,
        strict: "ignore",
        errorColor: "#b42318",
        ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code", "option", "input", "select"]
    };
    var QUICK_TEST = /\$|\\\(|\\\[/;
    // «$5 və $10» kimi valyuta mətni düstur deyil: konteynerdə `$`-dan dərhal sonra
    // rəqəm gəlirsə tək-`$` ayırıcısı həmin konteyner üçün söndürülür (idxal
    // zamanı əsl düsturlar onsuz da `\(…\)` kanonik formasına salınır).
    var CURRENCY_TEST = /\$\s?\d/;

    function optionsFor(text) {
        if (CURRENCY_TEST.test(text)) {
            return OPTIONS;
        }
        var withDollar = {};
        for (var key in OPTIONS) {
            if (Object.prototype.hasOwnProperty.call(OPTIONS, key)) {
                withDollar[key] = OPTIONS[key];
            }
        }
        withDollar.delimiters = DELIMITERS.concat([SINGLE_DOLLAR]);
        return withDollar;
    }

    function renderOne(container) {
        if (!container || container.getAttribute("data-ems-math-done") === "1") {
            return;
        }
        if (typeof window.renderMathInElement !== "function") {
            return; // KaTeX hələ yüklənməyib — növbəti keçiddə render olunacaq.
        }
        container.setAttribute("data-ems-math-done", "1");
        var text = container.textContent || "";
        if (!QUICK_TEST.test(text)) {
            return;
        }
        try {
            window.renderMathInElement(container, optionsFor(text));
        } catch (error) {
            // Render xətası səhifəni sındırmamalıdır; mətn olduğu kimi qalır.
            if (window.console && console.debug) {
                console.debug("EMSMath: render alınmadı", error);
            }
        }
    }

    function renderAll(root) {
        var scope = root || document;
        if (scope.nodeType === 1 && scope.hasAttribute && scope.hasAttribute("data-ems-math")) {
            renderOne(scope);
        }
        if (typeof scope.querySelectorAll !== "function") {
            return;
        }
        var nodes = scope.querySelectorAll("[data-ems-math]:not([data-ems-math-done])");
        for (var i = 0; i < nodes.length; i += 1) {
            renderOne(nodes[i]);
        }
    }

    var scheduled = false;
    function schedule() {
        if (scheduled) {
            return;
        }
        scheduled = true;
        var raf = window.requestAnimationFrame || function (fn) { return setTimeout(fn, 16); };
        raf(function () {
            scheduled = false;
            renderAll(document);
        });
    }

    function observe() {
        if (!window.MutationObserver || window.EMSMath.__observer || !document.body) {
            return;
        }
        var observer = new MutationObserver(function (mutations) {
            for (var i = 0; i < mutations.length; i += 1) {
                if (mutations[i].addedNodes && mutations[i].addedNodes.length) {
                    schedule();
                    return;
                }
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
        window.EMSMath.__observer = observer;
    }

    function start() {
        renderAll(document);
        observe();
    }

    window.EMSMath = {
        __loaded: true,
        __observer: null,
        render: renderAll,
        options: OPTIONS
    };

    if (typeof window.EMSReady === "function") {
        window.EMSReady(start);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
