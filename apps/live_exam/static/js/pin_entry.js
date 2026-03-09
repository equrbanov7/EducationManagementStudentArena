document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("pinInput");
    const form = document.querySelector(".pin-entry-form");
    const submitBtn = document.getElementById("pinSubmitBtn");
    const i18n = window.LIVE_PIN_ENTRY_I18N || {};

    if (!input || !form || !submitBtn) {
        return;
    }

    const submitLabel = submitBtn.querySelector("span");
    const defaultLabel = submitLabel ? submitLabel.textContent : "";

    const sanitize = (value) => String(value || "").replace(/\D/g, "").slice(0, 6);

    const syncValue = () => {
        input.value = sanitize(input.value);
        const wrapper = input.closest(".pin-entry-input-wrap");
        if (wrapper) {
            wrapper.classList.remove("has-error");
        }
        input.setAttribute("aria-invalid", "false");
    };

    input.addEventListener("input", syncValue);
    input.addEventListener("paste", () => {
        window.setTimeout(syncValue, 0);
    });

    form.addEventListener("submit", (event) => {
        syncValue();
        if (input.value.length !== 6) {
            event.preventDefault();
            input.focus();
            input.setAttribute("aria-invalid", "true");
            const wrapper = input.closest(".pin-entry-input-wrap");
            if (wrapper) {
                wrapper.classList.add("has-error");
            }
            const errorNode = document.getElementById("pinError");
            if (!errorNode) {
                input.setCustomValidity(i18n.invalidPin || "Enter a 6-digit PIN.");
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
});
