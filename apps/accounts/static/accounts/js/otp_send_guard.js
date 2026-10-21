/*
 * OTP formalarında ikiqat göndərişin qarşısı (sahib 2026-10-21: «müəllim 2 dəfə OTP göndərməyə
 * vuranda problem olur»).
 *
 * 1) `form[data-otp-submit-once]` — ilk submit-dən (klik və ya Enter) sonra forma «göndərilir»
 *    vəziyyətinə keçir: submit düymələri bağlanır, düymə mətni `data-busy-label` olur, təkrar
 *    submit ləğv edilir. Şəbəkə ilişərsə `UNLOCK_AFTER_MS`-dən sonra kilid açılır (server tərəfi
 *    onsuz da idempotentdir — cooldown daxilində ikinci kod yaranmır).
 * 2) `[data-otp-resend-wait]` düyməsi — «Kodu yenidən göndər» cooldown bitənə qədər bağlı,
 *    mətn `data-label-wait` («… ({s})») ilə geri sayır. Sayım SERVER saniyəsindən nisbidir.
 *
 * AJAX-safe: hadisə document-ə BİR dəfə bağlanır (delegasiya), init idempotentdir.
 * Qapı serverdədir; JS yalnız UX-dir.
 */
(function () {
    "use strict";

    var UNLOCK_AFTER_MS = 30000;

    function submitButtons(form) {
        var nodes = form.querySelectorAll("button[type='submit'], button:not([type]), input[type='submit']");
        if (form.id) {
            var outside = document.querySelectorAll("[form='" + form.id + "'][type='submit']");
            nodes = Array.prototype.slice.call(nodes).concat(Array.prototype.slice.call(outside));
        }
        return Array.prototype.slice.call(nodes);
    }

    function setBusy(form, busy) {
        submitButtons(form).forEach(function (button) {
            if (busy) {
                if (button.__emsOtpLabel === undefined) {
                    button.__emsOtpLabel = button.textContent;
                }
                button.disabled = true;
                button.setAttribute("aria-disabled", "true");
                var busyLabel = form.getAttribute("data-busy-label");
                if (busyLabel && button.tagName === "BUTTON") {
                    button.textContent = busyLabel;
                }
            } else {
                if (button.__emsOtpLabel !== undefined && button.tagName === "BUTTON") {
                    button.textContent = button.__emsOtpLabel;
                }
                delete button.__emsOtpLabel;
                if (!button.__emsOtpWaiting) {
                    button.disabled = false;
                    button.removeAttribute("aria-disabled");
                }
            }
        });
        if (busy) {
            form.setAttribute("aria-busy", "true");
            form.dataset.otpSubmitting = "1";
        } else {
            form.removeAttribute("aria-busy");
            delete form.dataset.otpSubmitting;
        }
    }

    function guardedForm(event) {
        var form = event.target;
        return form && form.nodeName === "FORM" && form.hasAttribute("data-otp-submit-once") ? form : null;
    }

    // Capture fazası: forma artıq göndərilirsə təkrar submit-i HAMIDAN əvvəl ləğv et.
    function blockRepeat(event) {
        var form = guardedForm(event);
        if (form && form.dataset.otpSubmitting === "1") {
            event.preventDefault();
            event.stopImmediatePropagation();
        }
    }

    // Bubble fazası: göndəriş həqiqətən gedirsə (başqa skript dayandırmayıbsa) formanı kilidlə.
    function lockOnSubmit(event) {
        var form = guardedForm(event);
        if (!form || event.defaultPrevented) {
            return;
        }
        form.dataset.otpSubmitting = "1";
        // Düymələri növbəti tikdə bağla: brauzer forma məlumatını submit hadisəsindən sonra yığır.
        window.setTimeout(function () {
            setBusy(form, true);
        }, 0);
        window.setTimeout(function () {
            if (document.contains(form)) {
                setBusy(form, false);
            }
        }, UNLOCK_AFTER_MS);
    }

    function startResendWait(button) {
        if (button.__emsOtpWaitBound) {
            return;
        }
        button.__emsOtpWaitBound = true;
        var seconds = parseInt(button.getAttribute("data-otp-resend-wait"), 10);
        if (!(seconds > 0)) {
            return;
        }
        var label = button.textContent.trim();
        var waitTemplate = button.getAttribute("data-label-wait") || label + " ({s})";
        var endsAt = Date.now() + seconds * 1000;
        var timer = null;

        function tick() {
            var left = Math.max(0, Math.ceil((endsAt - Date.now()) / 1000));
            if (left <= 0 || !document.contains(button)) {
                if (timer) {
                    window.clearInterval(timer);
                    timer = null;
                }
                button.__emsOtpWaiting = false;
                button.disabled = false;
                button.removeAttribute("aria-disabled");
                button.textContent = label;
                return;
            }
            button.textContent = waitTemplate.replace("{s}", String(left));
        }

        button.__emsOtpWaiting = true;
        button.disabled = true;
        button.setAttribute("aria-disabled", "true");
        tick();
        if (button.__emsOtpWaiting) {
            timer = window.setInterval(tick, 1000);
        }
    }

    function init() {
        var buttons = document.querySelectorAll("[data-otp-resend-wait]");
        for (var i = 0; i < buttons.length; i++) {
            startResendWait(buttons[i]);
        }
    }

    if (!window.__emsOtpSendGuardBound) {
        window.__emsOtpSendGuardBound = true;
        document.addEventListener("submit", blockRepeat, true);
        document.addEventListener("submit", lockOnSubmit, false);
        // bfcache-dən qayıdanda (Geri düyməsi) forma «göndərilir» vəziyyətində ilişib qalmasın.
        window.addEventListener("pageshow", function (event) {
            if (!event.persisted) {
                return;
            }
            var forms = document.querySelectorAll("form[data-otp-submit-once]");
            for (var i = 0; i < forms.length; i++) {
                setBusy(forms[i], false);
            }
        });
    }

    if (window.EMSReady) {
        window.EMSReady(init);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
