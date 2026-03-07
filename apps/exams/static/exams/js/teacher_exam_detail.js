(function () {
    if (window._TEACHER_EXAM_DETAIL_INIT) {
        return;
    }
    window._TEACHER_EXAM_DETAIL_INIT = true;

    document.addEventListener("DOMContentLoaded", function () {
        if (typeof bootstrap === "undefined") {
            return;
        }

        var i18n = window.TEACHER_EXAM_DETAIL_I18N || {};
        var questionModalElement = document.getElementById("questionFormModal");
        var questionModalBody = document.getElementById("questionFormModalBody");
        var questionModalTitle = document.getElementById("questionFormModalTitle");
        var questionModalHeader = questionModalElement ? questionModalElement.querySelector(".modal-header") : null;
        var deleteModalElement = document.getElementById("examDetailDeleteConfirmModal");
        var deleteModalMessage = document.getElementById("examDetailDeleteConfirmMessage");
        var deleteModalTarget = document.getElementById("examDetailDeleteConfirmTarget");
        var deleteConfirmForm = document.getElementById("examDetailDeleteConfirmForm");
        var questionModal = null;
        var deleteModal = null;
        var submitInFlight = false;

        if (questionModalElement && questionModalBody) {
            questionModal = bootstrap.Modal.getOrCreateInstance(questionModalElement);
        }
        if (deleteModalElement) {
            deleteModal = bootstrap.Modal.getOrCreateInstance(deleteModalElement);
        }

        function buildModalUrl(rawUrl) {
            try {
                var parsed = new URL(rawUrl, window.location.origin);
                parsed.searchParams.set("modal", "1");
                return parsed.pathname + parsed.search;
            } catch (error) {
                return rawUrl + (rawUrl.indexOf("?") === -1 ? "?modal=1" : "&modal=1");
            }
        }

        function getLoadingMarkup() {
            return '<div class="create-exam-modal-loading">' + (i18n.loadingForm || "Loading...") + "</div>";
        }

        function getErrorMarkup() {
            return '<div class="create-exam-modal-error">' + (i18n.submitError || "Please try again.") + "</div>";
        }

        function applyQuestionModalMode(mode) {
            var isEdit = mode === "edit";
            if (questionModalTitle) {
                questionModalTitle.textContent = isEdit ? (i18n.questionEditTitle || "Edit question") : (i18n.questionCreateTitle || "Add question");
            }

            if (questionModalHeader) {
                questionModalHeader.classList.remove("bg-primary", "bg-info");
                questionModalHeader.classList.add(isEdit ? "bg-primary" : "bg-info");
                questionModalHeader.classList.add("text-white");
            }
        }

        function bindQuestionModalForm() {
            if (!questionModalBody) {
                return;
            }

            var formRoot = questionModalBody.querySelector(".js-exam-question-form-root");
            if (window.ExamQuestionForm && formRoot) {
                window.ExamQuestionForm.init(formRoot);
            }

            var closeInlineBtn = questionModalBody.querySelector(".js-close-question-form-modal");
            if (closeInlineBtn && questionModal) {
                closeInlineBtn.addEventListener("click", function () {
                    questionModal.hide();
                });
            }

            var form = questionModalBody.querySelector("form");
            if (!form) {
                return;
            }

            form.addEventListener("submit", async function (event) {
                event.preventDefault();
                if (submitInFlight) {
                    return;
                }

                submitInFlight = true;
                var submitButton = form.querySelector('button[type="submit"]');
                if (submitButton) {
                    submitButton.disabled = true;
                }

                try {
                    var response = await fetch(form.getAttribute("action"), {
                        method: "POST",
                        body: new FormData(form),
                        headers: {
                            "X-Requested-With": "XMLHttpRequest"
                        }
                    });

                    var contentType = response.headers.get("content-type") || "";

                    if (contentType.indexOf("application/json") !== -1) {
                        var payload = await response.json();
                        if (response.ok && payload.success) {
                            if (questionModal) {
                                questionModal.hide();
                            }
                            window.location.reload();
                            return;
                        }
                        if (payload.html) {
                            questionModalBody.innerHTML = payload.html;
                            bindQuestionModalForm();
                            return;
                        }
                    }

                    var html = await response.text();
                    questionModalBody.innerHTML = html || getErrorMarkup();
                    bindQuestionModalForm();
                } catch (error) {
                    questionModalBody.innerHTML = getErrorMarkup();
                } finally {
                    submitInFlight = false;
                    if (submitButton) {
                        submitButton.disabled = false;
                    }
                }
            });
        }

        async function openQuestionModal(rawUrl, mode) {
            if (!questionModal || !questionModalBody || !rawUrl) {
                return;
            }

            applyQuestionModalMode(mode);
            questionModalBody.innerHTML = getLoadingMarkup();
            questionModal.show();

            try {
                var response = await fetch(buildModalUrl(rawUrl), {
                    headers: {
                        "X-Requested-With": "XMLHttpRequest"
                    }
                });

                if (!response.ok) {
                    throw new Error("request_failed");
                }

                questionModalBody.innerHTML = await response.text();
                bindQuestionModalForm();
            } catch (error) {
                questionModalBody.innerHTML = getErrorMarkup();
            }
        }

        document.addEventListener("click", function (event) {
            var deleteTrigger = event.target.closest(".js-open-delete-confirm-modal");
            if (deleteTrigger) {
                event.preventDefault();
                if (!deleteModal || !deleteConfirmForm) {
                    return;
                }

                deleteConfirmForm.setAttribute("action", deleteTrigger.getAttribute("data-delete-action") || "");
                if (deleteModalMessage) {
                    deleteModalMessage.textContent = deleteTrigger.getAttribute("data-delete-message") || "";
                }
                if (deleteModalTarget) {
                    deleteModalTarget.textContent = deleteTrigger.getAttribute("data-delete-target") || "";
                    deleteModalTarget.hidden = !deleteModalTarget.textContent;
                }

                deleteModal.show();
                return;
            }

            var questionTrigger = event.target.closest(".js-open-question-form-modal");
            if (!questionTrigger) {
                return;
            }

            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                return;
            }

            event.preventDefault();
            openQuestionModal(
                questionTrigger.getAttribute("data-question-modal-url") || questionTrigger.getAttribute("href"),
                questionTrigger.getAttribute("data-question-modal-mode") || "edit"
            );
        });

        if (questionModalElement) {
            questionModalElement.addEventListener("hidden.bs.modal", function () {
                submitInFlight = false;
                if (questionModalBody) {
                    questionModalBody.innerHTML = getLoadingMarkup();
                }
            });
        }
    });
})();
