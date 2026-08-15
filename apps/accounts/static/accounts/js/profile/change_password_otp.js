/* Şifrə dəyişmə bölməsi — rejim keçidi + email OTP kodu göndərmə.
 *
 * AJAX-safe (EMSDelegate / EMSReady). Kod sorğusu:
 * #passwordOtpRequest[data-url] → accounts:change_password_otp_request.
 * 429 cavabında payload.retry_after saniyəsi qədər «Yenidən göndər (Ns)»
 * geri sayımı işləyir; uğurda da resend cooldown qədər gözlədilir.
 */
(function () {
    "use strict";

    function activateMode(mode) {
        var card = document.getElementById("changePasswordCard");
        if (!card) {
            return;
        }
        card.querySelectorAll("[data-password-mode-panel]").forEach(function (panel) {
            panel.hidden = panel.dataset.passwordModePanel !== mode;
        });
        card.querySelectorAll(".password-mode-switch [data-password-mode-btn]").forEach(function (button) {
            var isActive = button.dataset.passwordModeBtn === mode;
            button.classList.toggle("is-active", isActive);
            button.setAttribute("aria-selected", isActive ? "true" : "false");
        });
        card.dataset.activeMode = mode;
    }

    function setStatus(message, isError) {
        var status = document.getElementById("passwordOtpStatus");
        if (!status) {
            return;
        }
        status.textContent = message || "";
        status.classList.toggle("password-otp-status--error", Boolean(isError));
        status.classList.toggle("password-otp-status--ok", Boolean(message) && !isError);
    }

    function stopCountdown(button) {
        if (button && button.dataset.countdownTimer) {
            window.clearInterval(Number(button.dataset.countdownTimer));
            delete button.dataset.countdownTimer;
        }
    }

    function startCountdown(button, seconds, resendLabel) {
        var labelNode = button.querySelector("[data-password-otp-btn-label]");
        if (!labelNode) {
            return;
        }
        stopCountdown(button);
        var remaining = Math.max(1, Math.floor(seconds));
        button.disabled = true;
        labelNode.textContent = resendLabel + " (" + remaining + "s)";
        var timerId = window.setInterval(function () {
            remaining -= 1;
            if (remaining <= 0 || !document.contains(button)) {
                window.clearInterval(timerId);
                delete button.dataset.countdownTimer;
                button.disabled = false;
                labelNode.textContent = resendLabel;
                return;
            }
            labelNode.textContent = resendLabel + " (" + remaining + "s)";
        }, 1000);
        button.dataset.countdownTimer = String(timerId);
    }

    function requestCode(button) {
        var container = document.getElementById("passwordOtpRequest");
        if (!container || !container.dataset.url || !window.EMSCore) {
            return;
        }
        var resendLabel = container.dataset.labelResend || container.dataset.labelSend || "";
        var fallbackError = container.dataset.labelError || "Error";
        var spinner = button.querySelector(".spinner-border");

        button.disabled = true;
        if (spinner) {
            spinner.classList.remove("d-none");
        }
        setStatus("", false);

        window.EMSCore.fetchJSON(container.dataset.url, { method: "POST", body: new URLSearchParams() })
            .then(function (payload) {
                setStatus(payload && payload.detail ? payload.detail : "", false);
                var cooldown = payload && payload.resend_available_in ? payload.resend_available_in : 60;
                startCountdown(button, cooldown, resendLabel);
            })
            .catch(function (error) {
                var payload = error && typeof error.payload === "object" ? error.payload : null;
                setStatus(payload && payload.error ? payload.error : fallbackError, true);
                if (payload && payload.retry_after) {
                    startCountdown(button, payload.retry_after, resendLabel);
                } else {
                    button.disabled = false;
                }
            })
            .finally(function () {
                if (spinner) {
                    spinner.classList.add("d-none");
                }
            });
    }

    window.EMSReady(function () {
        var card = document.getElementById("changePasswordCard");
        if (!card) {
            return; // bölmə hələ DOM-da deyil (swap olunmayıb)
        }
        activateMode(card.dataset.activeMode === "otp" ? "otp" : "current");
    });

    window.EMSReady.once("accounts/profile/change_password_otp", function () {
        window.EMSDelegate.on("click", "[data-password-mode-btn]", function (event, button) {
            event.preventDefault();
            activateMode(button.dataset.passwordModeBtn === "otp" ? "otp" : "current");
        });

        window.EMSDelegate.on("click", "#passwordOtpSendBtn", function (event, button) {
            event.preventDefault();
            if (!button.disabled) {
                requestCode(button);
            }
        });
    });
})();
