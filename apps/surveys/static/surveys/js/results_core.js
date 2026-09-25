/* =========================================================================
   results_core.js — «Sorğu nəticələri» ortaq nüvəsi (window.EMSSurveyResults.core)

   * Chart.js TƏNBƏL yüklənir: kabinet qabığı onu yalnız bəzi bölmələr üçün
     yükləyir; `window.Chart` yoxdursa `[data-chartjs-src]`-dən (static URL, CSP
     'self') bir dəfə skript əlavə olunur, gözləyənlər növbədə qalır.
   * Rənglər CSS tokenlərindən (`--svr-*`, results.css) — JS-də sabit rəng yoxdur.
   * Qrafiklər JSON adasından (`json_script`) çəkilir; hər qrafikin cədvəl
     qarşılığı serverdədir (qrafik yalnız vizual əlavədir, `role="img"`).
   * AJAX-safe: fayl iki dəfə yüklənsə də bir dəfə işləyir; render idempotentdir
     (köhnə qrafik məhv edilir). Toggle-lar `EMSDelegate` ilə (swap-a davamlı).
   ========================================================================= */
(function (window, document) {
    "use strict";

    var NS = (window.EMSSurveyResults = window.EMSSurveyResults || {});
    if (NS.core) {
        return;
    }

    /* ---- Chart.js tənbəl yükləmə ----------------------------------------- */
    var waiters = [];
    var loading = false;

    function flush() {
        if (typeof window.Chart !== "function") {
            return;
        }
        waiters.splice(0, waiters.length).forEach(function (fn) {
            try {
                fn(window.Chart);
            } catch (err) {
                if (window.console) {
                    window.console.error("svr chart:", err);
                }
            }
        });
    }

    function poll(attempt) {
        if (typeof window.Chart === "function") {
            loading = false;
            flush();
            return;
        }
        if (attempt > 100) {
            loading = false;
            return;
        }
        window.setTimeout(function () {
            poll(attempt + 1);
        }, 100);
    }

    function withChart(node, fn) {
        if (typeof window.Chart === "function") {
            fn(window.Chart);
            return;
        }
        waiters.push(fn);
        if (loading) {
            return;
        }
        loading = true;
        if (document.querySelector('script[src*="chart.umd"]')) {
            poll(0); // başqa bölmə artıq yükləyir — ikinci nüsxə lazım deyil
            return;
        }
        var holder = (node && node.closest && node.closest("[data-chartjs-src]")) || document.querySelector("[data-chartjs-src]");
        var src = holder ? holder.getAttribute("data-chartjs-src") : "";
        if (!src) {
            loading = false;
            return;
        }
        var script = document.createElement("script");
        script.src = src;
        script.async = true;
        script.addEventListener("load", function () {
            loading = false;
            flush();
        });
        script.addEventListener("error", function () {
            loading = false;
        });
        document.head.appendChild(script);
    }

    /* ---- Palitra, i18n, format ------------------------------------------- */
    function palette(node) {
        var host = (node && node.closest && node.closest(".svr, .svr-detail, .svr-print")) || document.documentElement;
        var styles = window.getComputedStyle(host);
        function v(name, fallback) {
            return (styles.getPropertyValue(name) || "").trim() || fallback;
        }
        return {
            c1: v("--svr-c1", "#2563eb"),
            c2: v("--svr-c2", "#d97706"),
            c3: v("--svr-c3", "#7c3aed"),
            ref: v("--svr-ref", "#334155"),
            ctx: v("--svr-ctx", "#94a3b8"),
            likert: [v("--svr-l1", "#b45309"), v("--svr-l2", "#d97706"), v("--svr-l3", "#cbd5e1"), v("--svr-l4", "#60a5fa"), v("--svr-l5", "#2563eb")],
            grid: v("--svr-grid", "#e2e8f0"),
            axis: v("--svr-axis", "#64748b"),
            ink: v("--svr-ink", "#0f172a"),
            surface: v("--svr-surface", "#ffffff"),
            font: styles.getPropertyValue("font-family") || "system-ui, sans-serif"
        };
    }

    function labels(node) {
        var host = node && node.closest ? node.closest("[data-i18n-n]") : null;
        return host ? host.dataset : {};
    }

    var LANG = (document.documentElement.getAttribute("lang") || "az").slice(0, 2);
    var formats = {};

    function formatter(digits) {
        if (!formats[digits]) {
            var opts = { minimumFractionDigits: digits, maximumFractionDigits: digits };
            try {
                formats[digits] = new Intl.NumberFormat(LANG, opts);
            } catch (err) {
                formats[digits] = new Intl.NumberFormat("en", opts);
            }
        }
        return formats[digits];
    }

    function fmt(value, digits) {
        if (value === null || value === undefined || isNaN(value)) {
            return "—";
        }
        return formatter(digits === undefined ? 2 : digits).format(value);
    }

    function isNum(value) {
        return typeof value === "number" && !isNaN(value);
    }

    function readIsland(id, scope) {
        if (!id) {
            return null;
        }
        var el = (scope && scope.querySelector && scope.querySelector("#" + id)) || document.getElementById(id);
        if (!el) {
            return null;
        }
        try {
            return JSON.parse(el.textContent || "null");
        } catch (err) {
            return null;
        }
    }

    function reducedMotion() {
        return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    }

    function merge(target, source) {
        Object.keys(source || {}).forEach(function (key) {
            var value = source[key];
            var isPlain = value && typeof value === "object" && !Array.isArray(value) && typeof value !== "function";
            if (isPlain && target[key] && typeof target[key] === "object" && !Array.isArray(target[key])) {
                merge(target[key], value);
            } else {
                target[key] = value;
            }
        });
        return target;
    }

    function axis(pal, extra) {
        return merge(
            {
                grid: { color: pal.grid, drawTicks: false },
                border: { display: false },
                ticks: { color: pal.axis, font: { size: 11, family: pal.font }, padding: 6 }
            },
            extra
        );
    }

    function base(pal, extra) {
        return merge(
            {
                responsive: true,
                maintainAspectRatio: false,
                animation: reducedMotion() ? false : { duration: 300 },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: pal.ink,
                        titleFont: { family: pal.font, size: 12, weight: "700" },
                        bodyFont: { family: pal.font, size: 12 },
                        padding: 10,
                        cornerRadius: 8,
                        boxWidth: 10,
                        boxHeight: 3
                    }
                }
            },
            extra
        );
    }

    function tickCallback(max) {
        return function (value) {
            var label = String(this.getLabelForValue ? this.getLabelForValue(value) : value);
            return label.length > max ? label.slice(0, max - 1) + "…" : label;
        };
    }

    /* Üfüqi qrafikin hündürlüyü sətir sayından (CSSOM — CSP style-attr deyil). */
    function sizeRows(wrap, rows, per, extra) {
        if (wrap) {
            wrap.style.height = Math.max(150, rows * (per || 28) + (extra || 52)) + "px";
        }
    }

    function mount(canvas, Chart, config) {
        if (!canvas) {
            return null;
        }
        if (canvas._svrChart) {
            canvas._svrChart.destroy();
        }
        canvas._svrChart = new Chart(canvas, config);
        return canvas._svrChart;
    }

    NS.core = {
        withChart: withChart,
        palette: palette,
        labels: labels,
        fmt: fmt,
        isNum: isNum,
        readIsland: readIsland,
        merge: merge,
        axis: axis,
        base: base,
        tickCallback: tickCallback,
        sizeRows: sizeRows,
        mount: mount
    };
})(window, document);
