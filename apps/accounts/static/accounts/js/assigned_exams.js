/* Extracted from accounts/assigned_exams.html (CSP: no inline script).
 * Exam-access-code modal. Buttons are wired by the global delegated handler in
 * static/js/csp_event_handlers.js, which calls window.openExamCodeModal /
 * window.closeExamCodeModal — so those MUST remain on window (as they were when
 * this was an inline classic <script>). Dynamic i18n strings are bridged via
 * data-* attributes on #exam-code-backdrop. */
window.EMSReady(function () {
    const backdrop = document.getElementById("exam-code-backdrop");
    if (!backdrop) return;

    const titleEl = document.getElementById("exam-code-title");
    const textEl = document.getElementById("exam-code-text");
    const slugInput = document.getElementById("exam-code-exam-slug");
    const codeInput = document.getElementById("exam-code-input");
    const codeError = document.getElementById("exam-code-error");
    const codeForm = document.getElementById("exam-code-form");

    const codeModalTitle = backdrop.dataset.i18nModalTitle || "";
    const codeModalPromptTemplate = backdrop.dataset.i18nPromptTemplate || "";
    const codeRequiredText = backdrop.dataset.i18nCodeRequired || "";
    const startFailedText = backdrop.dataset.i18nStartFailed || "";
    let codeSubmitInFlight = false;

    function setExamCodeError(message) {
        if (codeInput) {
            codeInput.classList.toggle("is-invalid", Boolean(message));
        }
        if (codeError) {
            codeError.textContent = message || "";
            codeError.hidden = !message;
        }
    }

    function openExamCodeModal(button) {
        const slug = button.getAttribute("data-exam-slug");
        const title = button.getAttribute("data-exam-title");

        slugInput.value = slug;
        titleEl.textContent = codeModalTitle;
        textEl.textContent = "";
        const textParts = codeModalPromptTemplate.split("{title}");
        textEl.appendChild(document.createTextNode(textParts[0] || ""));
        const strongEl = document.createElement("strong");
        strongEl.textContent = `"${title || ""}"`;
        textEl.appendChild(strongEl);
        if (textParts[1]) {
            textEl.appendChild(document.createTextNode(textParts[1]));
        }
        codeInput.value = "";
        setExamCodeError("");
        codeSubmitInFlight = false;

        backdrop.style.display = "flex";
        setTimeout(() => {
            backdrop.classList.add("show");
            codeInput.focus();
        }, 10);
    }

    function closeExamCodeModal() {
        backdrop.classList.remove("show");
        setTimeout(() => {
            backdrop.style.display = "none";
        }, 300);
    }

    // Preserve the global entry points consumed by csp_event_handlers.js.
    window.openExamCodeModal = openExamCodeModal;
    window.closeExamCodeModal = closeExamCodeModal;

    // Guard so event listeners bind only once even if EMSReady re-runs.
    if (backdrop.dataset.examCodeBound === "1") return;
    backdrop.dataset.examCodeBound = "1";

    backdrop.addEventListener("click", function (e) {
        if (e.target === backdrop) closeExamCodeModal();
    });

    if (codeInput) {
        codeInput.addEventListener("input", function () {
            this.value = this.value.replace(/[^0-9]/g, "");
            setExamCodeError("");
        });
    }

    if (codeForm) {
        codeForm.addEventListener("submit", async function (event) {
            event.preventDefault();
            if (!codeInput || !(codeInput.value || "").trim()) {
                setExamCodeError(codeRequiredText);
                if (codeInput) codeInput.focus();
                return;
            }
            if (codeSubmitInFlight) {
                return;
            }

            codeSubmitInFlight = true;
            try {
                const response = await fetch(codeForm.getAttribute("action"), {
                    method: "POST",
                    body: new FormData(codeForm),
                    headers: {
                        "X-Requested-With": "XMLHttpRequest"
                    }
                });
                const contentType = response.headers.get("content-type") || "";
                if (contentType.indexOf("application/json") !== -1) {
                    const payload = await response.json();
                    if (response.ok && payload.success) {
                        window.location.href = payload.redirect_url || window.location.href;
                        return;
                    }
                    setExamCodeError(payload.error || startFailedText);
                    return;
                }
                if (response.redirected && response.url) {
                    window.location.href = response.url;
                    return;
                }
                setExamCodeError(startFailedText);
            } catch (error) {
                setExamCodeError(startFailedText);
            } finally {
                codeSubmitInFlight = false;
            }
        });
    }
});
