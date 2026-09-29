/* pin_entry.js — canlı oyun PIN girişi (LX-FE-PLAYER 2026-09-29).
 *  • PIN normallaşdırılır (böyük hərf, yalnız 0-9/A-Z), canlı sayğac «7/10»;
 *  • qısa PIN-də forma göndərilmir — sahə altında xəta; göndərişdə düymə «Yoxlanılır…»;
 *  • QR/link ilə gələn `?pin=` avtomatik göndərilir (iki addımlı qoşulma);
 *  • əvvəlki anonim WebSocket «tema sinxronu» çıxarıldı (server anonim socket-i rədd edir,
 *    tema onsuz da server tərəfindən render olunur).
 * AJAX-safe: EMSReady + idempotent qoruyucu.
 */
(function () {
    "use strict";

    function init() {
        const input = document.getElementById("pinInput");
        const form = document.querySelector(".pin-entry-form");
        const submitBtn = document.getElementById("pinSubmitBtn");
        if (!input || !form || !submitBtn || form.dataset.lxInit) return;
        form.dataset.lxInit = "1";

        const i18n = window.LIVE_PIN_ENTRY_I18N || {};
        const pinLength = Number(i18n.pinLength || input.getAttribute("maxlength") || 10);
        const minPinLength = Math.max(1, Number(i18n.minPinLength || 6));
        const counter = document.getElementById("pinCount");
        const wrapper = input.closest(".pin-entry-input-wrap");
        const label = submitBtn.querySelector("span");
        const defaultLabel = label ? label.textContent : "";

        const sanitize = (value) =>
            String(value || "")
                .toUpperCase()
                .replace(/[^0-9A-Z]/g, "")
                .slice(0, pinLength);

        function sync() {
            const clean = sanitize(input.value);
            if (input.value !== clean) input.value = clean;
            if (counter) counter.textContent = `${clean.length}/${pinLength}`;
            submitBtn.classList.toggle("is-ready", clean.length >= minPinLength);
            if (wrapper) wrapper.classList.remove("has-error");
            input.setAttribute("aria-invalid", "false");
        }

        function showInvalid() {
            input.setAttribute("aria-invalid", "true");
            if (wrapper) wrapper.classList.add("has-error");
            let error = document.getElementById("pinError");
            if (!error) {
                error = document.createElement("p");
                error.id = "pinError";
                error.className = "pin-entry-error lxpin-error";
                error.setAttribute("role", "alert");
                wrapper.insertAdjacentElement("afterend", error);
                input.setAttribute("aria-describedby", "pinHelp pinError");
            }
            error.textContent = i18n.invalidPin || "";
            input.focus();
        }

        input.addEventListener("input", sync);
        input.addEventListener("paste", () => window.setTimeout(sync, 0));
        form.addEventListener("submit", (event) => {
            sync();
            if (input.value.length < minPinLength) {
                event.preventDefault();
                showInvalid();
                return;
            }
            if (form.dataset.submitting) {
                event.preventDefault();
                return;
            }
            form.dataset.submitting = "1";
            submitBtn.disabled = true;
            if (label) label.textContent = i18n.loading || defaultLabel;
        });
        window.addEventListener("pageshow", (event) => {
            // Geri düyməsi ilə qayıdanda (bfcache) düymə kilidli qalmasın.
            if (event.persisted) {
                delete form.dataset.submitting;
                submitBtn.disabled = false;
                if (label) label.textContent = defaultLabel;
            }
        });

        sync();
        const searchPin = sanitize(new URLSearchParams(window.location.search).get("pin"));
        if (searchPin.length >= minPinLength && input.value === searchPin && !document.getElementById("pinError")) {
            window.setTimeout(() => {
                if (typeof form.requestSubmit === "function") form.requestSubmit(submitBtn);
                else form.submit();
            }, 120);
        }
    }

    if (window.EMSReady) window.EMSReady(init);
    else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
})();
