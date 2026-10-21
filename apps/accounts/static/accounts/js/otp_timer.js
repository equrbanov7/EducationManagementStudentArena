/*
 * OTP kodunun qalan müddəti (parol bərpası, ilk giriş 2-ci addım).
 *
 * Sahib 2026-10-21 («OTP kodunun vaxtı keçib» deyir): əvvəl sayğac `expires_at - Date.now()` idi —
 * istifadəçinin kompüter saatı irəlidədirsə kod hələ etibarlı ikən «vaxtı keçib» görünürdü. İndi
 * server `data-otp-remaining-seconds` verir və sayım SƏHİFƏ YÜKLƏNƏNDƏN nisbidir (login_lockout.js
 * kimi); atribut yoxdursa köhnə `data-otp-expires-at` (ISO) ehtiyat yoludur.
 *
 * Banner: `[data-otp-expires-at]` və ya `[data-otp-timer]`; içində `[data-otp-countdown]`.
 * Bitəndə `is-expired` sinfi + `data-expired-label` mətni; `[data-otp-expired-note]` görünür.
 * AJAX-safe: idempotent (`__emsOtpTimerBound`), EMSReady varsa onunla.
 */
(function () {
    "use strict";

    function pad(value) {
        return value < 10 ? "0" + value : String(value);
    }

    function format(seconds) {
        return pad(Math.floor(seconds / 60)) + ":" + pad(seconds % 60);
    }

    function endsAtFor(banner) {
        var remainingRaw = banner.getAttribute("data-otp-remaining-seconds");
        if (remainingRaw !== null && remainingRaw !== "") {
            var remaining = parseInt(remainingRaw, 10);
            return Date.now() + (remaining > 0 ? remaining : 0) * 1000;
        }
        var expiresAt = new Date(banner.getAttribute("data-otp-expires-at") || "");
        return Number.isNaN(expiresAt.getTime()) ? Date.now() : expiresAt.getTime();
    }

    function start(banner) {
        if (banner.__emsOtpTimerBound) {
            return;
        }
        banner.__emsOtpTimerBound = true;
        var valueNode = banner.querySelector("[data-otp-countdown]");
        if (!valueNode) {
            return;
        }
        var expiredLabel = banner.getAttribute("data-expired-label") || "--:--";
        var note = banner.querySelector("[data-otp-expired-note]");
        var endsAt = endsAtFor(banner);
        var timer = null;

        function tick() {
            var left = Math.max(0, Math.ceil((endsAt - Date.now()) / 1000));
            if (left <= 0) {
                valueNode.textContent = expiredLabel;
                banner.classList.add("is-expired");
                if (note) {
                    note.hidden = false;
                }
                if (timer) {
                    window.clearInterval(timer);
                    timer = null;
                }
                return;
            }
            valueNode.textContent = format(left);
            banner.classList.remove("is-expired");
        }

        tick();
        if (!banner.classList.contains("is-expired")) {
            timer = window.setInterval(function () {
                if (!document.contains(banner)) {
                    window.clearInterval(timer);
                    return;
                }
                tick();
            }, 1000);
        }
    }

    function init() {
        var banners = document.querySelectorAll("[data-otp-expires-at], [data-otp-timer]");
        for (var i = 0; i < banners.length; i++) {
            start(banners[i]);
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
