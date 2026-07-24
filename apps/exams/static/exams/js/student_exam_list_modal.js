/*
 * student_exam_list_modal.js
 * Source: exams/student/partials/_student_exam_list_scripts.html
 *
 * Student exam-list page: the "start exam" modal (access-code entry, language
 * choice), the live-session PIN join modal, and search/pagination helpers.
 * All triggers are data-* based; i18n comes from the #student-exam-list-i18n
 * JSON island. No server URLs are embedded here.
 */
(function () {
    "use strict";

    var i18nEl = document.getElementById("student-exam-list-i18n");
    var I18N_STUDENT_EXAM_LIST = i18nEl ? JSON.parse(i18nEl.textContent) : {};

    document.addEventListener("DOMContentLoaded", function() {
        const modalElement = document.getElementById("examStartModal");
        const modalInstance = modalElement && window.bootstrap ? new bootstrap.Modal(modalElement) : null;
        const examNameEl = document.getElementById("examStartModalExamName");
        const typeEl = document.getElementById("examStartModalType");
        const accessEl = document.getElementById("examStartModalAccess");
        const attemptsEl = document.getElementById("examStartModalAttempts");
        const durationEl = document.getElementById("examStartModalDuration");
        const startEl = document.getElementById("examStartModalStart");
        const endEl = document.getElementById("examStartModalEnd");
        const noteEl = document.getElementById("examStartModalNote");
        const noteWrapEl = noteEl ? noteEl.closest(".exam-start-modal__note") : null;
        const codeForm = document.getElementById("examStartCodeForm");
        const slugInput = document.getElementById("examStartModalSlug");
        const codeInput = document.getElementById("examStartModalCodeInput");
        const codeErrorEl = document.getElementById("examStartModalCodeError");
        const codeHintEl = document.getElementById("examStartModalCodeHint");
        const codeLanguageInput = document.getElementById("examStartModalCodeLanguage");
        const languageBlock = document.getElementById("examStartLanguageBlock");
        const languageSelect = document.getElementById("examStartLanguageSelect");
        const actionBtn = document.getElementById("examStartModalActionBtn");
        const livePinModal = document.querySelector("[data-live-pin-modal]");
        const livePinForm = livePinModal ? livePinModal.querySelector("[data-live-pin-form]") : null;
        const livePinInput = livePinModal ? livePinModal.querySelector("[data-live-pin-input]") : null;
        const livePinError = livePinModal ? livePinModal.querySelector("[data-live-pin-error]") : null;
        const livePinTitle = livePinModal ? livePinModal.querySelector("[data-live-pin-exam-title]") : null;
        const livePinTeacher = livePinModal ? livePinModal.querySelector("[data-live-pin-exam-teacher]") : null;

        let startUrl = "";
        let requiresCode = false;
        let codeSubmitInFlight = false;
        let selectedLanguage = "";
        let expectedLivePin = "";
        let liveJoinUrl = "";

        function setCodeError(message) {
            if (codeInput) {
                codeInput.classList.toggle("is-invalid", Boolean(message));
            }
            if (codeErrorEl) {
                codeErrorEl.textContent = message || "";
                codeErrorEl.classList.toggle("d-none", !message);
            }
        }

        function setCodeHint(title) {
            if (!codeHintEl) {
                return;
            }

            if (!title) {
                codeHintEl.textContent = I18N_STUDENT_EXAM_LIST.modalAccessCodeDescription;
                return;
            }

            codeHintEl.textContent = "";
            const parts = I18N_STUDENT_EXAM_LIST.modalAccessCodeDescriptionWithTitle.split("{title}");
            codeHintEl.appendChild(document.createTextNode(parts[0] || ""));

            if (title) {
                const strongEl = document.createElement("strong");
                strongEl.textContent = `"${title}"`;
                codeHintEl.appendChild(strongEl);
            }

            if (parts[1]) {
                codeHintEl.appendChild(document.createTextNode(parts[1]));
            }
        }

        function getLanguageOptions(trigger) {
            const optionsId = trigger.getAttribute("data-language-options-id") || "";
            const optionsScript = optionsId ? document.getElementById(optionsId) : null;
            if (!optionsScript) {
                return [];
            }

            try {
                const parsed = JSON.parse(optionsScript.textContent || "[]");
                return Array.isArray(parsed) ? parsed : [];
            } catch (error) {
                return [];
            }
        }

        function setSelectedLanguage(language) {
            selectedLanguage = language || "";
            if (codeLanguageInput) {
                codeLanguageInput.value = selectedLanguage;
            }
        }

        function buildStartUrlWithLanguage(rawUrl) {
            if (!rawUrl || !selectedLanguage) {
                return rawUrl;
            }

            try {
                const url = new URL(rawUrl, window.location.origin);
                url.searchParams.set("language", selectedLanguage);
                return `${url.pathname}${url.search}${url.hash}`;
            } catch (error) {
                const separator = rawUrl.indexOf("?") === -1 ? "?" : "&";
                return `${rawUrl}${separator}language=${encodeURIComponent(selectedLanguage)}`;
            }
        }

        function refreshLanguageSelect() {
            if (!languageSelect) {
                return;
            }

            if (window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.refresh(languageSelect);
            }
        }

        function normalizeLivePin(value) {
            return String(value || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 10);
        }

        function setLivePinError(message) {
            if (livePinInput) {
                livePinInput.classList.toggle("is-invalid", Boolean(message));
            }
            if (livePinError) {
                livePinError.textContent = message || "";
                livePinError.hidden = !message;
            }
        }

        function openLivePinModal(trigger) {
            if (!livePinModal) {
                return;
            }

            expectedLivePin = normalizeLivePin(trigger.getAttribute("data-live-pin"));
            liveJoinUrl = trigger.getAttribute("data-live-join-url") || "";

            if (livePinTitle) {
                livePinTitle.textContent = trigger.getAttribute("data-live-title") || "-";
            }
            if (livePinTeacher) {
                const teacher = trigger.getAttribute("data-live-teacher") || "";
                livePinTeacher.textContent = teacher ? teacher : "";
                livePinTeacher.hidden = !teacher;
            }
            if (livePinInput) {
                livePinInput.value = "";
            }
            setLivePinError("");
            livePinModal.hidden = false;
            document.body.classList.add("ex-live-pin-modal-open");
            window.setTimeout(function() {
                if (livePinInput) {
                    livePinInput.focus();
                }
            }, 80);
        }

        function closeLivePinModal() {
            if (!livePinModal) {
                return;
            }
            livePinModal.hidden = true;
            document.body.classList.remove("ex-live-pin-modal-open");
            expectedLivePin = "";
            liveJoinUrl = "";
            setLivePinError("");
        }

        function configureLanguageChoice(trigger) {
            const options = getLanguageOptions(trigger);
            const defaultLanguage = trigger.getAttribute("data-default-language") || "";
            const defaultOption = options.find(function(option) {
                return option.language === defaultLanguage;
            }) || options[0] || null;

            if (!languageSelect || !languageBlock) {
                setSelectedLanguage(defaultOption ? defaultOption.language : "");
                return;
            }

            languageSelect.innerHTML = "";
            options.forEach(function(option) {
                const optionEl = document.createElement("option");
                optionEl.value = option.language || "";
                optionEl.textContent = option.display_name || option.language || "";
                languageSelect.appendChild(optionEl);
            });

            if (defaultOption) {
                languageSelect.value = defaultOption.language;
                setSelectedLanguage(defaultOption.language);
            } else {
                setSelectedLanguage("");
            }

            languageBlock.classList.toggle("d-none", options.length <= 1);
            languageSelect.required = options.length > 1;
            refreshLanguageSelect();
        }

        function resetModalState() {
            startUrl = "";
            requiresCode = false;
            setSelectedLanguage("");

            if (accessEl) {
                accessEl.classList.remove("exam-start-modal__badge--danger", "exam-start-modal__badge--success");
            }
            if (languageBlock) {
                languageBlock.classList.add("d-none");
            }
            if (languageSelect) {
                languageSelect.innerHTML = "";
                languageSelect.required = false;
                refreshLanguageSelect();
            }
            if (noteWrapEl) {
                noteWrapEl.classList.remove("is-empty");
            }
            if (codeForm) {
                codeForm.reset();
                codeForm.classList.add("d-none");
            }

            if (codeInput) {
                codeInput.required = false;
            }
            setCodeError("");

            if (actionBtn) {
                actionBtn.textContent = I18N_STUDENT_EXAM_LIST.modalActionStart;
                actionBtn.disabled = false;
            }
            codeSubmitInFlight = false;
        }

        document.addEventListener("click", function(event) {
            const liveJoinTrigger = event.target.closest("[data-open-live-pin-modal]");
            if (liveJoinTrigger) {
                event.preventDefault();
                openLivePinModal(liveJoinTrigger);
                return;
            }

            const trigger = event.target.closest("[data-open-exam-start-modal]");
            if (!trigger || !modalInstance) {
                return;
            }

            event.preventDefault();

            startUrl = trigger.getAttribute("data-start-url") || trigger.getAttribute("href") || "";
            requiresCode = trigger.getAttribute("data-requires-code") === "1";
            configureLanguageChoice(trigger);

            if (examNameEl) {
                examNameEl.textContent = trigger.getAttribute("data-exam-title") || "";
            }
            if (typeEl) {
                typeEl.textContent = trigger.getAttribute("data-exam-type") || "-";
            }
            if (accessEl) {
                accessEl.textContent = trigger.getAttribute("data-exam-access") || "-";
                accessEl.classList.toggle("exam-start-modal__badge--danger", requiresCode);
                accessEl.classList.toggle("exam-start-modal__badge--success", !requiresCode);
            }
            if (attemptsEl) {
                attemptsEl.textContent = trigger.getAttribute("data-exam-attempts") || "-";
            }
            if (durationEl) {
                durationEl.textContent = trigger.getAttribute("data-exam-duration") || "-";
            }
            if (startEl) {
                startEl.textContent = trigger.getAttribute("data-exam-start") || "-";
            }
            if (endEl) {
                endEl.textContent = trigger.getAttribute("data-exam-end") || "-";
            }
            if (noteEl) {
                const noteText = trigger.getAttribute("data-exam-note") || I18N_STUDENT_EXAM_LIST.modalNoteEmpty;
                noteEl.textContent = noteText;
                if (noteWrapEl) {
                    noteWrapEl.classList.toggle("is-empty", !trigger.getAttribute("data-exam-note"));
                }
            }
            if (slugInput) {
                slugInput.value = trigger.getAttribute("data-exam-slug") || "";
            }
            if (codeForm) {
                codeForm.classList.toggle("d-none", !requiresCode);
            }
            if (codeInput) {
                codeInput.required = requiresCode;
                codeInput.value = "";
                setCodeError("");
            }
            if (actionBtn) {
                actionBtn.textContent = requiresCode
                    ? I18N_STUDENT_EXAM_LIST.modalActionConfirmCode
                    : I18N_STUDENT_EXAM_LIST.modalActionStart;
            }
            if (requiresCode) {
                setCodeHint(trigger.getAttribute("data-exam-title") || "");
            }

            modalInstance.show();

            if (requiresCode && codeInput) {
                window.setTimeout(function() {
                    codeInput.focus();
                }, 200);
            }
        });

        if (codeInput) {
            codeInput.addEventListener("input", function() {
                this.value = this.value.replace(/[^0-9]/g, "");
                setCodeError("");
            });
        }

        if (livePinInput) {
            livePinInput.addEventListener("input", function() {
                this.value = normalizeLivePin(this.value);
                setLivePinError("");
            });
        }

        if (livePinModal) {
            livePinModal.addEventListener("click", function(event) {
                if (event.target.closest("[data-live-pin-close]")) {
                    event.preventDefault();
                    closeLivePinModal();
                }
            });
            document.addEventListener("keydown", function(event) {
                if (!livePinModal.hidden && event.key === "Escape") {
                    closeLivePinModal();
                }
            });
        }

        if (livePinForm) {
            livePinForm.addEventListener("submit", function(event) {
                event.preventDefault();
                const enteredPin = normalizeLivePin(livePinInput ? livePinInput.value : "");
                if (!enteredPin) {
                    setLivePinError(I18N_STUDENT_EXAM_LIST.livePinRequiredError);
                    if (livePinInput) livePinInput.focus();
                    return;
                }
                if (enteredPin !== expectedLivePin) {
                    setLivePinError(I18N_STUDENT_EXAM_LIST.livePinMismatchError);
                    if (livePinInput) livePinInput.focus();
                    return;
                }
                if (liveJoinUrl) {
                    window.location.href = liveJoinUrl;
                }
            });
        }

        if (languageSelect) {
            languageSelect.addEventListener("change", function() {
                setSelectedLanguage(this.value || "");
            });
        }

        if (codeForm) {
            codeForm.addEventListener("submit", async function(event) {
                event.preventDefault();
                if (!requiresCode) {
                    return;
                }

                if (!(codeInput && codeInput.value.trim())) {
                    setCodeError(I18N_STUDENT_EXAM_LIST.modalAccessCodeRequiredError);
                    if (codeInput) codeInput.focus();
                    return;
                }
                if (codeSubmitInFlight) {
                    return;
                }

                codeSubmitInFlight = true;
                if (actionBtn) {
                    actionBtn.disabled = true;
                }

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
                            window.location.href = payload.redirect_url || buildStartUrlWithLanguage(startUrl) || window.location.href;
                            return;
                        }
                        setCodeError(payload.error || I18N_STUDENT_EXAM_LIST.modalAccessCodeGenericError);
                        return;
                    }
                    if (response.redirected && response.url) {
                        window.location.href = response.url;
                        return;
                    }
                    setCodeError(I18N_STUDENT_EXAM_LIST.modalAccessCodeGenericError);
                } catch (error) {
                    setCodeError(I18N_STUDENT_EXAM_LIST.modalAccessCodeGenericError);
                } finally {
                    codeSubmitInFlight = false;
                    if (actionBtn) {
                        actionBtn.disabled = false;
                    }
                }
            });
        }

        if (actionBtn) {
            actionBtn.addEventListener("click", function() {
                if (requiresCode) {
                    if (!codeForm || !codeInput || !codeInput.value.trim()) {
                        setCodeError(I18N_STUDENT_EXAM_LIST.modalAccessCodeRequiredError);
                        if (codeInput) codeInput.focus();
                        return;
                    }

                    if (typeof codeForm.requestSubmit === "function") {
                        codeForm.requestSubmit();
                    } else {
                        codeForm.submit();
                    }
                    return;
                }

                if (startUrl) {
                    window.location.href = buildStartUrlWithLanguage(startUrl);
                }
            });
        }

        if (modalElement) {
            modalElement.addEventListener("hidden.bs.modal", resetModalState);
        }

        // --- A) PAGINATION PARAMETER FIX ---
        // Səhifə dəyişəndə axtarış sözünün (q) və tipin (type) itməməsini təmin edir.
        const paginationLinks = document.querySelectorAll('.page-link');

        if(paginationLinks.length > 0) {
            const currentUrlParams = new URLSearchParams(window.location.search);

            paginationLinks.forEach(link => {
                const href = link.getAttribute('href');
                if (href && href.startsWith('?page=')) {
                    const pageNum = href.split('=')[1];
                    currentUrlParams.set('page', pageNum);
                    link.setAttribute('href', '?' + currentUrlParams.toString());
                }
            });
        }

        // --- B) LIVE SEARCH (DEBOUNCE 1 saniyə) ---
        const searchInput = document.querySelector('input[name="q"]');
        const searchForm = document.querySelector('.exam-toolbar');

        if (searchInput && searchForm) {
            let debounceTimer;

            searchInput.addEventListener('input', function() {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(() => {
                    searchForm.submit();
                }, 1000);
            });

            searchForm.addEventListener('submit', function() {
                clearTimeout(debounceTimer);
            });

            if(searchInput.value) {
                searchInput.focus();
                const val = searchInput.value;
                searchInput.value = '';
                searchInput.value = val;
            }
        }
    });
})();
