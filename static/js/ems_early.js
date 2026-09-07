/*
 * ems_early.js — <head>-də, HƏR şeydən əvvəl yüklənən növbə stub-u.
 *
 * Problem: bölmə partial-larının `<script src>`-ləri `{% block content %}` içindədir
 * və `ems_ajax_init.js` (əsl `EMSReady` / `EMSDelegate`) body-nin sonunda gəlir.
 * Tam səhifə render-də partial skripti `window.EMSReady(...)` çağıranda funksiya
 * hələ yoxdur → `TypeError: window.EMSReady is not a function` və bölmənin JS-i
 * heç vaxt bağlanmır (QA 2026-09-05, P1-1).
 *
 * Həll: burada `EMSReady` / `EMSReady.once` / `EMSDelegate.on` üçün çağırışları
 * YIĞAN stub-lar təyin olunur. `ems_ajax_init.js` yüklənəndə stub-ları əsl
 * implementasiya ilə əvəz edir və növbəni eyni sıra ilə boşaldır. Beləliklə skript
 * sırası nə olursa olsun qeydiyyat itmir. Partial skriptlərinə `defer` qoymaq
 * konvensiyası qalır — bu fayl ona əlavə təhlükəsizlik qatıdır.
 */
(function () {
    "use strict";

    if (window.EMSReady && !window.EMSReady.__emsStub) {
        return; // Əsl implementasiya artıq var.
    }

    var queue = { ready: [], once: [], on: [] };

    function readyStub(fn) {
        if (typeof fn === "function") {
            queue.ready.push(fn);
        }
    }
    readyStub.__emsStub = true;
    readyStub.once = function (key, fn) {
        if (typeof fn === "function") {
            queue.once.push([key, fn]);
        }
    };

    var delegateStub = {
        __emsStub: true,
        on: function (eventType, selector, handler) {
            if (typeof handler === "function") {
                queue.on.push([eventType, selector, handler]);
            }
        }
    };

    window.__emsEarlyQueue = queue;
    window.EMSReady = readyStub;
    window.EMSDelegate = delegateStub;
})();
