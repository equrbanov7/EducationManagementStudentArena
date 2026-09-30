/*
 * Giriş bloku geri sayımı (sahib 2026-10-01).
 *
 * Çoxlu uğursuz cəhddən sonra server `[data-login-lockout][data-seconds]` bannerini göstərir.
 * Burada: saniyə-saniyə geri sayım (MM:SS), vaxt bitənə qədər «Daxil ol» düyməsi bağlı, bitəndə
 * «indi yenidən cəhd edə bilərsiniz». Sayım SƏHİFƏ YÜKLƏNƏNDƏN nisbidir (server saniyəsi) —
 * istifadəçinin kompüter saatı səhv olsa da düz göstərir. Qapı serverdədir (429); JS yalnız UX-dir.
 */
(function () {
    "use strict";

    function pad(value) {
        return value < 10 ? "0" + value : String(value);
    }

    function format(seconds) {
        return pad(Math.floor(seconds / 60)) + ":" + pad(seconds % 60);
    }

    function start(root) {
        if (root.__emsLockoutBound) {
            return;
        }
        root.__emsLockoutBound = true;
        var seconds = parseInt(root.getAttribute("data-seconds"), 10);
        if (!(seconds > 0)) {
            return;
        }
        var clock = root.querySelector("[data-lockout-countdown]");
        var waiting = root.querySelector("[data-lockout-waiting]");
        var ready = root.querySelector("[data-lockout-ready]");
        var form = document.querySelector("form.auth-form");
        var submit = form ? form.querySelector("[type='submit']") : null;
        var endsAt = Date.now() + seconds * 1000;
        var timer = null;

        function setSubmitLocked(locked) {
            if (!submit) {
                return;
            }
            submit.disabled = locked;
            if (locked) {
                submit.setAttribute("aria-disabled", "true");
            } else {
                submit.removeAttribute("aria-disabled");
            }
        }

        function finish() {
            if (timer) {
                window.clearInterval(timer);
                timer = null;
            }
            root.classList.add("is-ready");
            if (waiting) {
                waiting.hidden = true;
            }
            if (ready) {
                ready.hidden = false;
            }
            setSubmitLocked(false);
        }

        function tick() {
            var left = Math.max(0, Math.ceil((endsAt - Date.now()) / 1000));
            if (clock) {
                clock.textContent = format(left);
            }
            if (left <= 0) {
                finish();
            }
        }

        setSubmitLocked(true);
        tick();
        if (!root.classList.contains("is-ready")) {
            timer = window.setInterval(tick, 1000);
        }
    }

    function init() {
        var roots = document.querySelectorAll("[data-login-lockout]");
        for (var i = 0; i < roots.length; i++) {
            start(roots[i]);
        }
    }

    if (window.EMSReady) {
        window.EMSReady(init);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
