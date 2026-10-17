/*
 * teacher_exam_detail_lazy.js — imtahan sehrbazı paketinin tənbəl yüklənməsi (Paket B, 2026-10-17).
 * Source: exams/teacher/teacher_exam_detail.html
 *
 * Detal səhifəsi əvvəl hər açılışda «Redaktə» sehrbazının 3 CSS + 11 JS faylını yükləyirdi,
 * halbuki «Redaktə» nadir klikdir (OLD_DESIGN_INVENTORY P3). İndi `#ted-wizard-assets`
 * siyahısı İLK `.js-open-exam-form-modal` klikində (və ya fokus/hover-də qabaqcadan) qoşulur:
 * CSS paralel, JS ARDICIL (namespace → … → entry.js sırası vacibdir). Yükləndikdən sonra
 * klik təkrarlanır və entry.js-in öz dinləyicisi modalı açır. Paket artıq varsa
 * (window.EMSExamCreateEditModal.form) heç nə etmir.
 */
(function () {
    "use strict";

    var state = "idle"; // idle | loading | ready | failed
    var waiters = [];

    function readAssets() {
        var el = document.getElementById("ted-wizard-assets");
        if (!el) {
            return null;
        }
        try {
            return JSON.parse(el.textContent) || null;
        } catch (err) {
            return null;
        }
    }

    function bundlePresent() {
        var ns = window.EMSExamCreateEditModal;
        return Boolean(ns && ns.form && window._EXAM_CREATE_EDIT_MODAL_INIT);
    }

    function addCss(href) {
        if (document.querySelector('link[rel="stylesheet"][href="' + href + '"]')) {
            return;
        }
        var link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = href;
        document.head.appendChild(link);
    }

    function addScript(src) {
        return new Promise(function (resolve, reject) {
            if (document.querySelector('script[src="' + src + '"]')) {
                resolve();
                return;
            }
            var script = document.createElement("script");
            script.src = src;
            script.async = false;
            script.onload = function () {
                resolve();
            };
            script.onerror = function () {
                // Uğursuz teq DOM-da qalsa, növbəti cəhd onu «yüklənib» sayardı (ölü «Redaktə»).
                script.remove();
                reject(new Error("load_failed:" + src));
            };
            document.body.appendChild(script);
        });
    }

    function load() {
        if (state === "ready" || bundlePresent()) {
            state = "ready";
            return Promise.resolve();
        }
        if (state === "loading") {
            return new Promise(function (resolve, reject) {
                waiters.push([resolve, reject]);
            });
        }
        var assets = readAssets();
        if (!assets) {
            state = "failed";
            return Promise.reject(new Error("no_assets"));
        }
        state = "loading";
        (assets.css || []).forEach(addCss);
        var chain = Promise.resolve();
        (assets.js || []).forEach(function (src) {
            chain = chain.then(function () {
                return addScript(src);
            });
        });
        return chain.then(
            function () {
                state = "ready";
                waiters.splice(0).forEach(function (w) {
                    w[0]();
                });
            },
            function (err) {
                state = "failed";
                waiters.splice(0).forEach(function (w) {
                    w[1](err);
                });
                throw err;
            }
        );
    }

    var SELECTOR = ".js-open-exam-form-modal";

    // Niyyət siqnalı (hover / klaviatura fokusu) — klikdən əvvəl yükləməyə başlayır.
    function prefetch(event) {
        if (state === "idle" && event.target && event.target.closest && event.target.closest(SELECTOR)) {
            load().catch(function () {
                state = "idle";
            });
        }
    }
    document.addEventListener("pointerover", prefetch, { passive: true });
    document.addEventListener("focusin", prefetch);

    // Capture: entry.js hələ yoxdursa klik burada saxlanılır, paket gəldikdən sonra təkrarlanır.
    document.addEventListener(
        "click",
        function (event) {
            var trigger = event.target.closest ? event.target.closest(SELECTOR) : null;
            if (!trigger || state === "ready" || bundlePresent()) {
                return;
            }
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                return; // yeni tabda açmaq — adi keçid
            }
            event.preventDefault();
            event.stopPropagation();
            trigger.setAttribute("aria-busy", "true");
            load().then(
                function () {
                    trigger.removeAttribute("aria-busy");
                    trigger.click();
                },
                function () {
                    // Paket gəlmədi — tam səhifə redaktə formasına keç (əvvəlki fallback).
                    trigger.removeAttribute("aria-busy");
                    window.location.href = trigger.getAttribute("href");
                }
            );
        },
        true
    );

    window.TEDWizardLazy = { load: load };
})();
