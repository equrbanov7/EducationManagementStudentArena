/* Assigned-exam info/code modal. Delegated so AJAX swaps keep buttons live. */
(function (ns) {
    "use strict";

    ns.register(function installAssignedExamModal(ctx) {
        if (!ctx.profilePage || !ctx.sectionLinks.length || !ctx.sectionPanels.length) {
            return;
        }

        var assignedExamInfoBackdrop = document.getElementById("assignedExamInfoBackdrop");
        var assignedExamInfoStartBtn = document.getElementById("assignedExamInfoStartBtn");
        var assignedExamInfoExamName = document.getElementById("assignedExamInfoExamName");
        var assignedExamInfoType = document.getElementById("assignedExamInfoType");
        var assignedExamInfoDuration = document.getElementById("assignedExamInfoDuration");
        var assignedExamInfoStart = document.getElementById("assignedExamInfoStart");
        var assignedExamInfoEnd = document.getElementById("assignedExamInfoEnd");
        var assignedExamInfoNote = document.getElementById("assignedExamInfoNote");
        var assignedExamCodeForm = document.getElementById("assignedExamCodeForm");
        var assignedExamCodeSlug = document.getElementById("assignedExamCodeSlug");
        var assignedExamAccessCodeInput = document.getElementById("assignedExamAccessCodeInput");
        var assignedExamCodeError = document.getElementById("assignedExamCodeError");
        var assignedExamModalStartUrl = "";
        var assignedExamModalRequiresCode = false;
        var assignedExamCodeSubmitInFlight = false;

        function setAssignedExamCodeError(message) {
            if (assignedExamAccessCodeInput) {
                assignedExamAccessCodeInput.classList.toggle("is-invalid", Boolean(message));
            }
            if (assignedExamCodeError) {
                assignedExamCodeError.textContent = message || "";
                assignedExamCodeError.hidden = !message;
            }
        }

        function refreshAssignedExamRefs() {
            assignedExamInfoBackdrop = document.getElementById("assignedExamInfoBackdrop");
            assignedExamInfoExamName = document.getElementById("assignedExamInfoExamName");
            assignedExamInfoType = document.getElementById("assignedExamInfoType");
            assignedExamInfoDuration = document.getElementById("assignedExamInfoDuration");
            assignedExamInfoStart = document.getElementById("assignedExamInfoStart");
            assignedExamInfoEnd = document.getElementById("assignedExamInfoEnd");
            assignedExamInfoNote = document.getElementById("assignedExamInfoNote");
            assignedExamInfoStartBtn = document.getElementById("assignedExamInfoStartBtn");
            assignedExamCodeForm = document.getElementById("assignedExamCodeForm");
            assignedExamCodeSlug = document.getElementById("assignedExamCodeSlug");
            assignedExamAccessCodeInput = document.getElementById("assignedExamAccessCodeInput");
            assignedExamCodeError = document.getElementById("assignedExamCodeError");
        }

        function openAssignedExamInfoModal(trigger) {
            refreshAssignedExamRefs();

            if (!assignedExamInfoBackdrop || !trigger) {
                return;
            }

            assignedExamModalStartUrl = trigger.getAttribute("data-start-url") || "";
            assignedExamModalRequiresCode = trigger.getAttribute("data-requires-code") === "1";

            if (assignedExamInfoExamName) {
                assignedExamInfoExamName.textContent = trigger.getAttribute("data-exam-title") || "";
            }
            if (assignedExamInfoType) {
                assignedExamInfoType.textContent = trigger.getAttribute("data-exam-type") || "-";
            }
            if (assignedExamInfoDuration) {
                assignedExamInfoDuration.textContent = trigger.getAttribute("data-exam-duration") || "-";
            }
            if (assignedExamInfoStart) {
                assignedExamInfoStart.textContent = trigger.getAttribute("data-exam-start") || "-";
            }
            if (assignedExamInfoEnd) {
                assignedExamInfoEnd.textContent = trigger.getAttribute("data-exam-end") || "-";
            }
            if (assignedExamInfoNote) {
                var noteText = trigger.getAttribute("data-exam-note") || "";
                assignedExamInfoNote.textContent = noteText || "Qeyd yoxdur.";
            }

            if (assignedExamCodeSlug) {
                assignedExamCodeSlug.value = trigger.getAttribute("data-exam-slug") || "";
            }
            if (assignedExamCodeForm) {
                assignedExamCodeForm.classList.toggle("is-hidden", !assignedExamModalRequiresCode);
            }
            if (assignedExamAccessCodeInput) {
                assignedExamAccessCodeInput.value = "";
            }
            setAssignedExamCodeError("");
            if (assignedExamInfoStartBtn) {
                assignedExamInfoStartBtn.textContent = assignedExamModalRequiresCode
                    ? gettext("Kodu təsdiqlə və başla")
                    : gettext("İmtahana başla");
                assignedExamInfoStartBtn.disabled = false;
            }
            assignedExamCodeSubmitInFlight = false;

            assignedExamInfoBackdrop.classList.add("is-open");
            assignedExamInfoBackdrop.setAttribute("aria-hidden", "false");
            document.body.style.overflow = "hidden";

            if (assignedExamModalRequiresCode && assignedExamAccessCodeInput) {
                window.setTimeout(function () {
                    assignedExamAccessCodeInput.focus();
                }, 40);
            }
        }

        function closeAssignedExamInfoModal() {
            assignedExamInfoBackdrop = document.getElementById("assignedExamInfoBackdrop");
            if (!assignedExamInfoBackdrop) {
                return;
            }
            assignedExamInfoBackdrop.classList.remove("is-open");
            assignedExamInfoBackdrop.setAttribute("aria-hidden", "true");
            if (!ctx.createExamModal || !ctx.createExamModal.classList.contains("active")) {
                document.body.style.overflow = "";
            }
        }

        async function submitAssignedExamCodeForm() {
            if (!assignedExamCodeForm || !assignedExamAccessCodeInput) {
                return;
            }

            var codeValue = (assignedExamAccessCodeInput.value || "").trim();
            if (!codeValue) {
                setAssignedExamCodeError(gettext("İmtahan kodu tələb olunur."));
                assignedExamAccessCodeInput.focus();
                return;
            }

            if (assignedExamCodeSubmitInFlight) {
                return;
            }

            assignedExamCodeSubmitInFlight = true;
            if (assignedExamInfoStartBtn) {
                assignedExamInfoStartBtn.disabled = true;
            }

            try {
                var response = await fetch(assignedExamCodeForm.getAttribute("action"), {
                    method: "POST",
                    body: new FormData(assignedExamCodeForm),
                    headers: {
                        "X-Requested-With": "XMLHttpRequest"
                    }
                });
                var contentType = response.headers.get("content-type") || "";
                if (contentType.indexOf("application/json") !== -1) {
                    var payload = await response.json();
                    if (response.ok && payload.success) {
                        window.location.href = payload.redirect_url || assignedExamModalStartUrl || window.location.href;
                        return;
                    }
                    setAssignedExamCodeError(payload.error || gettext("İmtahana başlamaq mümkün olmadı."));
                    return;
                }
                if (response.redirected && response.url) {
                    window.location.href = response.url;
                    return;
                }
                setAssignedExamCodeError(gettext("İmtahana başlamaq mümkün olmadı."));
            } catch (error) {
                setAssignedExamCodeError(gettext("İmtahana başlamaq mümkün olmadı."));
            } finally {
                assignedExamCodeSubmitInFlight = false;
                if (assignedExamInfoStartBtn) {
                    assignedExamInfoStartBtn.disabled = false;
                }
            }
        }

        ctx.closeAssignedExamInfoModal = closeAssignedExamInfoModal;
        ctx.isAssignedExamInfoOpen = function isAssignedExamInfoOpen() {
            return Boolean(assignedExamInfoBackdrop && assignedExamInfoBackdrop.classList.contains("is-open"));
        };

        document.addEventListener("click", function (event) {
            var trigger = event.target.closest(".js-open-assigned-exam-modal");
            if (!trigger) {
                return;
            }
            event.preventDefault();
            openAssignedExamInfoModal(trigger);
        });

        document.addEventListener("click", function (event) {
            var backdrop = document.getElementById("assignedExamInfoBackdrop");
            if (backdrop && event.target === backdrop) {
                closeAssignedExamInfoModal();
                return;
            }
            if (event.target.closest && event.target.closest("#assignedExamInfoClose, #assignedExamInfoCancelBtn")) {
                closeAssignedExamInfoModal();
            }
        });

        document.addEventListener("input", function (event) {
            if (event.target && event.target.id === "assignedExamAccessCodeInput") {
                event.target.value = event.target.value.replace(/[^0-9]/g, "");
                setAssignedExamCodeError("");
            }
        });

        document.addEventListener("submit", function (event) {
            if (event.target && event.target.id === "assignedExamCodeForm") {
                event.preventDefault();
                submitAssignedExamCodeForm();
            }
        });

        document.addEventListener("click", function (event) {
            if (!event.target.closest || !event.target.closest("#assignedExamInfoStartBtn")) {
                return;
            }
            if (assignedExamModalRequiresCode) {
                submitAssignedExamCodeForm();
                return;
            }
            if (assignedExamModalStartUrl) {
                window.location.href = assignedExamModalStartUrl;
            }
        });
    });
})(window.EMSProfile = window.EMSProfile || {});
