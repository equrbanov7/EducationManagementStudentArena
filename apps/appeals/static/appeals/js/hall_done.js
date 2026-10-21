/* Zal apellyasiyasının uğur ekranı (2026-10-21): geri sayım → növün giriş səhifəsi (/exams/final/ | /exams/midterm/).
   URL və saniyə `[data-hall-done]` data-atributlarından (Django dəyəri xarici JS-ə bişirilmir). AJAX-safe, null-safe. */
(function () {
    'use strict';

    function init() {
        var root = document.querySelector('[data-hall-done]');
        if (!root || root.dataset.hallDoneBound === '1') {
            return;
        }
        root.dataset.hallDoneBound = '1';
        var url = root.dataset.hallDoneUrl;
        var left = parseInt(root.dataset.hallDoneSeconds, 10);
        if (!url || !(left > 0)) {
            return;
        }
        var counter = root.querySelector('[data-hall-done-countdown]');
        var timer = window.setInterval(function () {
            left -= 1;
            if (counter) {
                counter.textContent = String(Math.max(left, 0));
            }
            if (left <= 0) {
                window.clearInterval(timer);
                window.location.replace(url);
            }
        }, 1000);
    }

    if (typeof window.EMSReady === 'function') {
        window.EMSReady(init);
    } else if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
