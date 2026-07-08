/* Entry point for the exam create/edit Bootstrap modal bundle. */
(function (ns, document, window) {
    "use strict";

    if (window._EXAM_CREATE_EDIT_MODAL_INIT) {
        return;
    }
    window._EXAM_CREATE_EDIT_MODAL_INIT = true;

    function start() {
        var modalElement = document.getElementById("examCreateEditModal");
        var modalBody = document.getElementById("examCreateEditModalBody");
        var modalTitle = document.getElementById("examCreateEditModalTitle");
        var modalHeader = modalElement ? modalElement.querySelector(".modal-header") : null;
        var i18n = window.EXAM_CREATE_EDIT_MODAL_I18N || {};

        if (!modalElement || !modalBody || typeof bootstrap === "undefined") {
            return;
        }

        var ctx = {
            modalElement: modalElement,
            modalBody: modalBody,
            modalTitle: modalTitle,
            modalHeader: modalHeader,
            bsModal: bootstrap.Modal.getOrCreateInstance(modalElement),
            submitInFlight: false,
            modalLoadToken: 0,
            i18n: i18n
        };

        document.addEventListener("click", function (event) {
            var trigger = event.target.closest(".js-open-exam-form-modal");
            if (!trigger) {
                return;
            }

            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                return;
            }

            event.preventDefault();

            var targetUrl = trigger.getAttribute("data-exam-modal-url") || trigger.getAttribute("href");
            var mode = trigger.getAttribute("data-exam-modal-mode") || "edit";

            var parentModal = trigger.closest(".modal.show");
            if (parentModal && parentModal !== modalElement) {
                var parentModalInstance = bootstrap.Modal.getInstance(parentModal);
                if (parentModalInstance) {
                    parentModal.addEventListener(
                        "hidden.bs.modal",
                        function () {
                            ns.form.openExamModal(ctx, targetUrl, mode);
                        },
                        { once: true }
                    );
                    parentModalInstance.hide();
                    return;
                }
            }

            ns.form.openExamModal(ctx, targetUrl, mode);
        });

        var confirmEl = modalElement.querySelector("[data-ew-confirm]");
        function hideUnsavedConfirm() {
            if (confirmEl) {
                confirmEl.hidden = true;
            }
        }
        if (confirmEl) {
            var cancelBtn = confirmEl.querySelector("[data-ew-confirm-cancel]");
            var saveBtn = confirmEl.querySelector("[data-ew-confirm-save]");
            var discardBtn = confirmEl.querySelector("[data-ew-confirm-discard]");
            if (cancelBtn) {
                cancelBtn.addEventListener("click", hideUnsavedConfirm);
            }
            if (saveBtn) {
                saveBtn.addEventListener("click", function () {
                    hideUnsavedConfirm();
                    var form = modalBody.querySelector("#createExamModalForm");
                    if (!form) {
                        return;
                    }
                    if (form.requestSubmit) {
                        form.requestSubmit();
                    } else {
                        var sb = form.querySelector('button[type="submit"]');
                        if (sb) sb.click();
                    }
                });
            }
            if (discardBtn) {
                discardBtn.addEventListener("click", function () {
                    hideUnsavedConfirm();
                    modalElement.dataset.examDiscard = "1";
                    ctx.bsModal.hide();
                });
            }
        }

        modalElement.addEventListener("hide.bs.modal", function (event) {
            if (modalElement.dataset.examDiscard === "1") {
                modalElement.dataset.examDiscard = "";
                return;
            }
            if (ctx.submitInFlight) {
                return;
            }
            var form = modalBody.querySelector("#createExamModalForm");
            if (form && form.dataset.ewDirty === "1") {
                event.preventDefault();
                if (confirmEl) {
                    confirmEl.hidden = false;
                }
            }
        });

        // Fon sürüşməsini bloklamaq — Bootstrap-ın `modal-open`-u bəzi
        // SPA-scroll kontekstlərində fonu tam saxlamır, ona görə <html>-ə
        // birbaşa kilid sinfi əlavə edirik.
        modalElement.addEventListener("shown.bs.modal", function () {
            document.documentElement.classList.add("exam-modal-open");
        });

        modalElement.addEventListener("hidden.bs.modal", function () {
            document.documentElement.classList.remove("exam-modal-open");
            ctx.submitInFlight = false;
            hideUnsavedConfirm();
            modalElement.dataset.examDiscard = "";
            ns.markup.resetModalBody(ctx);
        });

        ns.markup.resetModalBody(ctx);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})(window.EMSExamCreateEditModal = window.EMSExamCreateEditModal || {}, document, window);
