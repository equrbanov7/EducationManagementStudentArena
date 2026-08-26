/* RİM mərkəzi — modal açma/bağlama və parol göstərmə. */
(function (window, document) {
    "use strict";

    var ns = (window.EMSRimCenter = window.EMSRimCenter || {});
    var modals = (ns.modals = {});

    modals.open = function open(selector) {
        var el = document.querySelector(selector);
        if (el) {
            el.hidden = false;
        }
    };

    modals.close = function close(selector) {
        var el = document.querySelector(selector);
        if (el) {
            el.hidden = true;
        }
    };

    modals.closeAll = function closeAll() {
        var all = document.querySelectorAll("[data-rim-detail-modal], [data-rim-confirm-modal], [data-rim-password-modal]");
        Array.prototype.forEach.call(all, function (el) {
            el.hidden = true;
        });
    };

    /**
     * Birdəfəlik parolu göstərir.
     *
     * Parol DOM-a yazılır və modal bağlananda dərhal təmizlənir — brauzer
     * yaddaşında qalmasın. Heç bir yerə (localStorage/sessionStorage/log)
     * yazılmır.
     */
    modals.showPassword = function showPassword(password) {
        var valueEl = document.querySelector("[data-rim-password-value]");
        if (valueEl) {
            valueEl.textContent = password;
        }
        modals.open("[data-rim-password-modal]");
    };

    modals.clearPassword = function clearPassword() {
        var valueEl = document.querySelector("[data-rim-password-value]");
        if (valueEl) {
            valueEl.textContent = "";
        }
    };

    modals.copyPassword = function copyPassword(button) {
        var valueEl = document.querySelector("[data-rim-password-value]");
        if (!valueEl || !valueEl.textContent) {
            return;
        }
        var text = valueEl.textContent;
        var done = function () {
            if (button) {
                var original = button.innerHTML;
                button.textContent = ns.t("copied");
                window.setTimeout(function () {
                    button.innerHTML = original;
                }, 1500);
            }
        };
        if (window.navigator.clipboard && window.navigator.clipboard.writeText) {
            window.navigator.clipboard.writeText(text).then(done, function () {});
            return;
        }
        // Köhnə brauzer geri düşməsi.
        var helper = document.createElement("textarea");
        helper.value = text;
        document.body.appendChild(helper);
        helper.select();
        try {
            document.execCommand("copy");
            done();
        } catch (err) {
            /* səssiz — operator əl ilə seçə bilər */
        }
        document.body.removeChild(helper);
    };
})(window, document);
