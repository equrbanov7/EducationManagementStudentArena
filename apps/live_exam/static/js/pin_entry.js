document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("pinInput");
    const form = document.querySelector(".pin-entry-form");
    const submitBtn = document.getElementById("pinSubmitBtn");
    const i18n = window.LIVE_PIN_ENTRY_I18N || {};
    const pinLength = Number(i18n.pinLength || input?.getAttribute("maxlength") || 10);
    const minPinLength = Math.max(1, Number(i18n.minPinLength || 6));
    let themeSocket = null;
    let themeSocketPin = "";

    if (!input || !form || !submitBtn) {
        return;
    }

    const submitLabel = submitBtn.querySelector("span");
    const defaultLabel = submitLabel ? submitLabel.textContent : "";

    const sanitize = (value) => String(value || "")
        .toUpperCase()
        .replace(/[^0-9A-Z]/g, "")
        .slice(0, pinLength);
    const applyTheme = (settings) => {
        if (!settings) return;
        document.body.dataset.liveTheme = settings.theme_key || document.body.dataset.liveTheme || "aurora";
    };
    const closeThemeSocket = () => {
        if (!themeSocket) return;
        themeSocket.onclose = null;
        themeSocket.close();
        themeSocket = null;
        themeSocketPin = "";
    };
    const connectThemeSocket = (pin) => {
        const normalizedPin = sanitize(pin);
        if (normalizedPin.length !== pinLength) {
            closeThemeSocket();
            return;
        }
        if (themeSocket && themeSocketPin === normalizedPin && themeSocket.readyState <= 1) {
            return;
        }

        closeThemeSocket();
        themeSocketPin = normalizedPin;
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        themeSocket = new WebSocket(`${protocol}//${window.location.host}/ws/live/${encodeURIComponent(normalizedPin)}/lobby/`);
        themeSocket.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                const payload = message.data || message;
                if ((payload.type === "lobby_state" || payload.type === "session_settings") && payload.settings) {
                    applyTheme(payload.settings);
                }
            } catch (error) {
                console.error("pin entry theme sync parse error", error);
            }
        };
        themeSocket.onclose = () => {
            if (themeSocketPin === normalizedPin) {
                themeSocket = null;
            }
        };
    };

    const syncValue = () => {
        input.value = sanitize(input.value);
        input.dataset.pinChars = String(input.value.length || pinLength);
        const wrapper = input.closest(".pin-entry-input-wrap");
        if (wrapper) {
            wrapper.classList.remove("has-error");
        }
        input.setAttribute("aria-invalid", "false");
        if (input.value.length === pinLength) {
            connectThemeSocket(input.value);
        } else {
            closeThemeSocket();
        }
    };

    input.addEventListener("input", syncValue);
    input.addEventListener("paste", () => {
        window.setTimeout(syncValue, 0);
    });

    form.addEventListener("submit", (event) => {
        syncValue();
        if (input.value.length < minPinLength) {
            event.preventDefault();
            input.focus();
            input.setAttribute("aria-invalid", "true");
            const wrapper = input.closest(".pin-entry-input-wrap");
            if (wrapper) {
                wrapper.classList.add("has-error");
            }
            const errorNode = document.getElementById("pinError");
            if (!errorNode) {
                input.setCustomValidity(i18n.invalidPin || "Enter a valid PIN.");
                input.reportValidity();
                input.setCustomValidity("");
            }
            return;
        }

        submitBtn.disabled = true;
        if (submitLabel) {
            submitLabel.textContent = i18n.loading || defaultLabel;
        }
    });

    syncValue();

    const searchPin = sanitize(new URLSearchParams(window.location.search).get("pin"));
    if (searchPin.length >= minPinLength && input.value === searchPin) {
        window.setTimeout(() => {
            syncValue();
            if (!submitBtn.disabled && input.value.length >= minPinLength) {
                if (typeof form.requestSubmit === "function") {
                    form.requestSubmit(submitBtn);
                } else {
                    form.submit();
                }
            }
        }, 120);
    }

    window.addEventListener("beforeunload", closeThemeSocket);
});
