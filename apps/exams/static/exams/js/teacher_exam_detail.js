(function () {
    if (window._TEACHER_EXAM_DETAIL_INIT) {
        return;
    }
    window._TEACHER_EXAM_DETAIL_INIT = true;

    document.addEventListener("DOMContentLoaded", function () {
        (function initLiveSessionResumeModal() {
            var modal = document.querySelector("[data-live-session-modal]");
            if (!modal) {
                return;
            }

            var returnBtn = modal.querySelector("[data-live-session-return]");
            var newBtn = modal.querySelector("[data-live-session-new]");
            var pinEl = modal.querySelector("[data-live-session-pin]");
            var createdEl = modal.querySelector("[data-live-session-created]");
            var activeTrigger = null;
            var probeInFlight = false;

            function openModal(trigger) {
                activeTrigger = trigger;
                if (pinEl) {
                    pinEl.textContent = trigger.getAttribute("data-live-pin") || "-";
                }
                if (createdEl) {
                    createdEl.textContent = trigger.getAttribute("data-live-created") || "-";
                }
                modal.hidden = false;
                document.body.classList.add("live-session-modal-open");
                window.setTimeout(function () {
                    if (returnBtn) {
                        returnBtn.focus();
                    }
                }, 40);
            }

            function closeModal() {
                modal.hidden = true;
                document.body.classList.remove("live-session-modal-open");
            }

            function withQueryParam(rawUrl, name, value) {
                try {
                    var parsed = new URL(rawUrl, window.location.origin);
                    parsed.searchParams.set(name, value);
                    return parsed.pathname + parsed.search + parsed.hash;
                } catch (error) {
                    return rawUrl + (rawUrl.indexOf("?") === -1 ? "?" : "&") + name + "=" + encodeURIComponent(value);
                }
            }

            function navigateToStart(trigger) {
                var targetUrl = trigger ? trigger.getAttribute("href") : "";
                if (targetUrl) {
                    window.location.href = targetUrl;
                }
            }

            function hydrateTriggerFromPayload(trigger, payload) {
                if (!trigger || !payload) {
                    return;
                }
                trigger.setAttribute("data-has-active-session", "1");
                trigger.setAttribute("data-live-return-url", payload.return_url || "");
                trigger.setAttribute("data-live-new-url", payload.new_url || "");
                trigger.setAttribute("data-live-pin", payload.pin || "");
                trigger.setAttribute("data-live-created", payload.created || "");
            }

            async function probeLiveSession(trigger) {
                var href = trigger.getAttribute("href") || "";
                if (!href) {
                    return null;
                }

                var response = await fetch(withQueryParam(href, "probe", "1"), {
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                        "Accept": "application/json"
                    }
                });
                if (!response.ok) {
                    return null;
                }
                return response.json();
            }

            document.addEventListener("click", async function (event) {
                var trigger = event.target.closest("[data-live-start-trigger]");
                if (!trigger) {
                    return;
                }
                if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                    return;
                }
                event.preventDefault();

                if (trigger.getAttribute("data-has-active-session") === "1") {
                    openModal(trigger);
                    return;
                }

                if (probeInFlight) {
                    return;
                }
                probeInFlight = true;
                trigger.setAttribute("aria-busy", "true");

                try {
                    var payload = await probeLiveSession(trigger);
                    if (payload && payload.active) {
                        hydrateTriggerFromPayload(trigger, payload);
                        openModal(trigger);
                        return;
                    }
                    navigateToStart(trigger);
                } catch (error) {
                    navigateToStart(trigger);
                } finally {
                    probeInFlight = false;
                    trigger.removeAttribute("aria-busy");
                }
            });

            modal.addEventListener("click", function (event) {
                if (event.target.closest("[data-live-session-close]")) {
                    event.preventDefault();
                    closeModal();
                }
            });

            document.addEventListener("keydown", function (event) {
                if (modal.hidden || event.key !== "Escape") {
                    return;
                }
                closeModal();
            });

            if (returnBtn) {
                returnBtn.addEventListener("click", function () {
                    var targetUrl = activeTrigger ? activeTrigger.getAttribute("data-live-return-url") : "";
                    if (targetUrl) {
                        window.location.href = targetUrl;
                    }
                });
            }

            if (newBtn) {
                newBtn.addEventListener("click", function () {
                    var targetUrl = activeTrigger ? activeTrigger.getAttribute("data-live-new-url") : "";
                    if (!targetUrl && activeTrigger) {
                        targetUrl = activeTrigger.getAttribute("href") || "";
                    }
                    if (targetUrl) {
                        window.location.href = targetUrl;
                    }
                });
            }
        })();

        (function initQuestionLazyLoading() {
            var loader = document.querySelector("[data-question-lazy]");
            var list = document.querySelector("[data-question-list]");
            if (!loader || !list) {
                return;
            }

            var trigger = loader.querySelector("[data-question-lazy-trigger]");
            var status = loader.querySelector("[data-question-lazy-status]");
            var root = loader.closest(".questions-section");
            var isLoading = false;
            var observer = null;

            function setLoading(loading) {
                isLoading = loading;
                loader.setAttribute("aria-busy", loading ? "true" : "false");
                if (trigger) {
                    trigger.disabled = loading;
                    trigger.hidden = loading;
                }
                if (status) {
                    status.hidden = !loading;
                }
            }

            function buildPageUrl() {
                var rawUrl = loader.getAttribute("data-load-url") || "";
                var url = new URL(rawUrl, window.location.origin);
                url.searchParams.set("offset", loader.getAttribute("data-next-offset") || "0");
                url.searchParams.set("limit", loader.getAttribute("data-page-size") || "20");
                return url.pathname + url.search;
            }

            function finish(hasMore, nextOffset) {
                if (!hasMore) {
                    if (observer) {
                        observer.disconnect();
                    }
                    loader.remove();
                    return;
                }
                loader.setAttribute(
                    "data-next-offset",
                    String(nextOffset || loader.getAttribute("data-next-offset") || "0")
                );
                setLoading(false);
            }

            async function loadMoreQuestions() {
                if (isLoading || !document.body.contains(loader)) {
                    return;
                }
                setLoading(true);
                try {
                    var response = await fetch(buildPageUrl(), {
                        headers: {
                            "X-Requested-With": "XMLHttpRequest",
                            "Accept": "application/json"
                        }
                    });
                    if (!response.ok) {
                        throw new Error("request_failed");
                    }
                    var payload = await response.json();
                    if (payload.html) {
                        list.insertAdjacentHTML("beforeend", payload.html);
                    }
                    finish(Boolean(payload.has_more), payload.next_offset);
                } catch (error) {
                    setLoading(false);
                }
            }

            if (trigger) {
                trigger.addEventListener("click", function (event) {
                    event.preventDefault();
                    loadMoreQuestions();
                });
            }

            if ("IntersectionObserver" in window) {
                observer = new IntersectionObserver(function (entries) {
                    entries.forEach(function (entry) {
                        if (entry.isIntersecting) {
                            loadMoreQuestions();
                        }
                    });
                }, {
                    root: root || null,
                    rootMargin: "120px 0px 120px 0px",
                    threshold: 0.01
                });
                observer.observe(loader);
            }
        })();

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
                questionModalHeader.classList.remove(
                    "bg-primary",
                    "bg-info",
                    "question-form-modal__header--create",
                    "question-form-modal__header--edit"
                );
                questionModalHeader.classList.add("question-form-modal__header");
                questionModalHeader.classList.add(isEdit ? "question-form-modal__header--edit" : "question-form-modal__header--create");
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
