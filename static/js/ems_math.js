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

   Yüklənmə: `templates/partials/ems_ui/_math_assets.html` YALNIZ bu faylı (`defer`)
   verir; KaTeX (katex.min.js ≈266 KB + auto-render + katex.min.css) yolları skript
   teqinin `data-katex-*` atributlarındadır və TƏNBƏL yüklənir — yalnız səhifədə
   (və ya sonradan gələn konteynerdə) düstur ayırıcısı olanda (perf 2026-10-07:
   düstursuz imtahan səhifəsi KaTeX-i nə yükləyir, nə də parse edir). CSP-safe:
   same-origin `script src`/`link`, CDN yoxdur.
   ========================================================================= */
(function () {
    "use strict";

    if (window.EMSMath && window.EMSMath.__loaded) {
        return;
    }

    // `document.currentScript` YALNIZ ilk icrada mövcuddur — atributlar indi oxunur.
    var SELF = document.currentScript || null;
    var KATEX = SELF && typeof SELF.getAttribute === "function" ? {
        css: SELF.getAttribute("data-katex-css") || "",
        js: SELF.getAttribute("data-katex-js") || "",
        autorender: SELF.getAttribute("data-katex-autorender") || ""
    } : null;
    var katexState = 0; // 0 — yüklənməyib, 1 — yüklənir, 2 — bitdi (uğurlu və ya xəta)

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

    function appendScript(src, onDone) {
        var script = document.createElement("script");
        script.src = src;
        script.async = false; // katex.min.js auto-render-dən ƏVVƏL icra olunsun
        script.addEventListener("load", onDone);
        script.addEventListener("error", onDone);
        (document.head || document.body).appendChild(script);
    }

    function ensureKatex() {
        if (katexState !== 0 || !KATEX || !KATEX.js || !KATEX.autorender || typeof document.createElement !== "function") {
            return;
        }
        katexState = 1;
        if (KATEX.css) {
            var link = document.createElement("link");
            link.rel = "stylesheet";
            link.href = KATEX.css;
            (document.head || document.body).appendChild(link);
        }
        var pending = 2;
        function done() {
            pending -= 1;
            if (pending === 0) {
                katexState = 2;
                renderAll(document);
            }
        }
        appendScript(KATEX.js, done);
        appendScript(KATEX.autorender, done);
    }

    function collect(scope) {
        var nodes = [];
        if (scope.nodeType === 1 && scope.hasAttribute && scope.hasAttribute("data-ems-math")) {
            nodes.push(scope);
        }
        if (typeof scope.querySelectorAll === "function") {
            var found = scope.querySelectorAll("[data-ems-math]:not([data-ems-math-done])");
            for (var i = 0; i < found.length; i += 1) {
                nodes.push(found[i]);
            }
        }
        return nodes;
    }

    function renderAll(root) {
        var nodes = collect(root || document);
        var i;
        if (typeof window.renderMathInElement !== "function") {
            // KaTeX hələ yoxdur: düstursuz konteynerlər bitmiş sayılır, düstur varsa
            // KaTeX tənbəl yüklənir və bitəndə `renderAll` yenidən çağırılır.
            var needsKatex = false;
            for (i = 0; i < nodes.length; i += 1) {
                if (nodes[i].getAttribute("data-ems-math-done") === "1") {
                    continue;
                }
                if (QUICK_TEST.test(nodes[i].textContent || "")) {
                    needsKatex = true;
                } else {
                    nodes[i].setAttribute("data-ems-math-done", "1");
                }
            }
            if (needsKatex) {
                ensureKatex();
            }
            return;
        }
        for (i = 0; i < nodes.length; i += 1) {
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
