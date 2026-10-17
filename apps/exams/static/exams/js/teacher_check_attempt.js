/*
 * teacher_check_attempt.js — yoxlama səhifəsinin dialoq + saxlama qatı (Paket B, 2026-10-17).
 * Source: exams/teacher/teacher_check_attempt.html
 *
 * Vəziyyət/cəmi bal/klaviatura naviqasiyası teacher_check_attempt_ui.js-dədir
 * (window.TCAGrading). Bu fayl:
 *   • «Ətraflı» dialoqu (#questionModal): sualın tam mətni, cavab, AI qiymətləndirmə,
 *     əvvəlki/növbəti (Alt+←/→), Enter → tətbiq et və növbəti; Escape/×/fon → dəyişiklik
 *     varsa xəbərdarlıq (#warningModal);
 *   • «Geri» keçidi və səhifədən çıxış — yadda saxlanmamış dəyişiklik xəbərdarlığı;
 *   • göndərmə təsdiqi (window.openActionConfirmModal) və Ctrl/⌘+S.
 * Form sahələri (score_<id>, feedback_<id>), POST ünvanı və ID-lər dəyişməyib.
 */
(function () {
    "use strict";

    function init() {
        var root = document.querySelector("[data-tca-root]");
        var G = window.TCAGrading;
        if (!root || !G) {
            return;
        }
        var i18n = window.TEACHER_CHECK_I18N || {};
        var t = {
            modalTitleDetails: i18n.modalTitleDetails || "Question details",
            noAnswer: i18n.noAnswer || "No answer",
            pointsUnit: i18n.pointsUnit || "pts",
            statusNotChecked: i18n.statusNotChecked || "Not reviewed",
            confirmTitle: i18n.confirmTitle || "Save review",
            confirmMessage: i18n.confirmMessage || "Are you sure you want to save and finalize this review?",
            aiGrading: i18n.aiGrading || "AI is grading...",
            aiError: i18n.aiError || "AI grading error",
            aiCached: i18n.aiCached || "Cached",
            aiQuotaInfo: i18n.aiQuotaInfo || "{remaining}/{limit} ({window})",
            aiNoAnswer: i18n.aiNoAnswer || "No answer to grade",
            uploadedFilesLabel: i18n.uploadedFilesLabel || "Uploaded files",
            answeredWithPaint: i18n.answeredWithPaint || "Answered with paint",
            stateSaving: i18n.stateSaving || "Saving…",
            questionN: i18n.questionN || "Question %(n)s",
        };
        if (!G.init(i18n)) {
            return; // artıq bağlanıb (idempotent)
        }

        var backdrop = document.getElementById("modalBackdrop");
        var modal = document.getElementById("questionModal");
        var warning = document.getElementById("warningModal");
        var form = document.getElementById("gradingForm");
        var mainSaveBtn = document.getElementById("mainSaveBtn");
        var backBtn = document.getElementById("backBtn");
        var scoreEl = document.getElementById("modalScoreInput");
        var maxEl = document.getElementById("modalMaxPointsInput");
        var feedbackEl = document.getElementById("modalFeedbackInput");
        var currentEl = document.getElementById("currentQuestionId");
        var prevBtn = document.getElementById("modalPrevBtn");
        var nextBtn = document.getElementById("modalNextBtn");
        var aiBtn = document.getElementById("aiGradeBtn");
        var aiStatus = document.getElementById("aiGradeStatus");

        var modalDirty = false;
        var submitConfirmed = false;
        var pendingNavigationUrl = null;
        var pendingAfterWarning = null;
        var returnFocus = null;

        function isOpen(el) {
            return el && !el.hidden;
        }

        function dataStore(qId) {
            var card = document.getElementById("tca-q-" + qId);
            return card ? card.querySelector(".data-store") : null;
        }

        function lockScroll(lock) {
            document.body.classList.toggle("modal-open", lock);
            document.documentElement.classList.toggle("ems-modal-open", lock);
        }

        /* ---- dialoq ------------------------------------------------------- */
        function fillAnswer(qId) {
            var store = dataStore(qId);
            var answerEl = document.getElementById("modalAnswerText");
            var card = document.getElementById("tca-q-" + qId);
            if (!store || !answerEl) {
                return;
            }
            answerEl.textContent = "";
            var codeFiles = card ? card.querySelector(".coding-files-review") : null;
            var ansText = store.getAttribute("data-ans-text");
            var note = null;
            if (codeFiles) {
                answerEl.appendChild(codeFiles.cloneNode(true));
            } else if (ansText) {
                answerEl.textContent = ansText;
            } else if (store.getAttribute("data-has-file-answer") === "1") {
                note = t.uploadedFilesLabel;
            } else if (store.getAttribute("data-has-paint-answer") === "1") {
                note = t.answeredWithPaint;
            } else if (store.getAttribute("data-has-answer") === "1") {
                note = t.statusNotChecked;
            } else {
                note = t.noAnswer;
            }
            if (note) {
                var em = document.createElement("em");
                em.className = "tca-dialog__muted";
                em.textContent = note;
                answerEl.appendChild(em);
            }
        }

        function loadQuestion(qId) {
            var store = dataStore(qId);
            if (!store) {
                return;
            }
            var card = document.getElementById("tca-q-" + qId);
            var index = card ? card.getAttribute("data-index") : "";
            var ids = G.orderedIds();
            document.getElementById("modalTitle").textContent = t.questionN.replace("%(n)s", index);
            var sub = document.getElementById("modalSubtitle");
            if (sub) {
                sub.textContent = t.modalTitleDetails + " · " + index + " / " + ids.length;
            }
            document.getElementById("modalQuestionText").textContent = store.getAttribute("data-q-text") || "";
            fillAnswer(qId);

            var model = document.getElementById("modalModelAnswer");
            var modelText = store.getAttribute("data-q-correct-answer") || "";
            if (model) {
                model.hidden = !modelText;
                model.open = false;
                var modelBody = model.querySelector("[data-tca-modal-model]");
                if (modelBody) {
                    modelBody.textContent = modelText;
                }
            }

            currentEl.value = qId;
            scoreEl.value = G.scoreInput(qId) ? G.scoreInput(qId).value : "";
            feedbackEl.value = G.feedbackInput(qId) ? G.feedbackInput(qId).value : "";
            var max = String(G.maxPoints(qId));
            maxEl.value = max;
            maxEl.setAttribute("placeholder", max);
            scoreEl.setAttribute("max", max);
            scoreEl.setAttribute("placeholder", "\u2013");
            G.setInvalid(scoreEl, false);

            if (prevBtn) {
                prevBtn.disabled = !G.neighbour(qId, -1);
            }
            if (nextBtn) {
                nextBtn.disabled = !G.neighbour(qId, 1);
            }
            resetAi(store.getAttribute("data-has-ai-gradable") === "1");
            modalDirty = false;
            if (window.EMSMath && typeof window.EMSMath.render === "function") {
                window.EMSMath.render(modal);
            }
        }

        function openModal(qId) {
            if (!backdrop || !modal || !dataStore(qId)) {
                return;
            }
            returnFocus = document.activeElement;
            loadQuestion(qId);
            backdrop.hidden = false;
            lockScroll(true);
            scoreEl.focus();
            scoreEl.select();
        }

        function closeModal() {
            if (!backdrop) {
                return;
            }
            backdrop.hidden = true;
            modalDirty = false;
            lockScroll(isOpen(warning));
            var qId = currentEl.value;
            var fallback = qId ? G.scoreInput(qId) : null;
            var target = returnFocus && document.contains(returnFocus) ? returnFocus : fallback;
            if (target && typeof target.focus === "function") {
                target.focus();
            }
            returnFocus = null;
        }

        /* Dialoqdakı dəyərləri karta yazır. Etibarsızdırsa false (fokus sahədə qalır). */
        function applyModal() {
            var qId = currentEl.value;
            if (!qId) {
                return false;
            }
            var max = G.maxPoints(qId);
            var raw = scoreEl.value.trim();
            var value = G.parseScore(raw);
            // badInput: brauzer mətni oxumadı (`value === ""`) — boş sayıb balı SİLMƏ.
            if (G.isBadInput(scoreEl) || (raw && value === null)) {
                G.setInvalid(scoreEl, true);
                scoreEl.focus();
                return false;
            }
            G.setInvalid(scoreEl, false);
            if (value !== null && value > max) {
                value = max;
            }
            G.setValues(qId, value, feedbackEl.value);
            modalDirty = false;
            return true;
        }

        function move(step) {
            var target = G.neighbour(currentEl.value, step);
            if (!target) {
                return;
            }
            if (!applyModal()) {
                return;
            }
            loadQuestion(target);
            scoreEl.focus();
            scoreEl.select();
        }

        function attemptClose() {
            if (modalDirty) {
                pendingAfterWarning = function () {
                    closeModal();
                };
                openWarning();
                return;
            }
            closeModal();
        }

        /* ---- xəbərdarlıq -------------------------------------------------- */
        function openWarning() {
            if (!warning) {
                return;
            }
            warning.hidden = false;
            lockScroll(true);
            var cancel = document.getElementById("warningCancelBtn");
            if (cancel) {
                cancel.focus();
            }
        }

        function closeWarning() {
            warning.hidden = true;
            pendingNavigationUrl = null;
            pendingAfterWarning = null;
            lockScroll(isOpen(backdrop));
            if (isOpen(backdrop)) {
                scoreEl.focus();
            } else if (backBtn) {
                backBtn.focus();
            }
        }

        function confirmWarning() {
            var url = pendingNavigationUrl;
            var after = pendingAfterWarning;
            warning.hidden = true;
            pendingNavigationUrl = null;
            pendingAfterWarning = null;
            if (url) {
                submitConfirmed = true; // beforeunload xəbərdarlığı təkrar çıxmasın
                window.location.href = url;
                return;
            }
            modalDirty = false;
            if (after) {
                after();
            }
            lockScroll(isOpen(backdrop));
        }

        /* ---- AI qiymətləndirmə ------------------------------------------- */
        function setAiLoading(loading) {
            if (!aiBtn) {
                return;
            }
            aiBtn.disabled = loading;
            aiBtn.classList.toggle("is-loading", loading);
            aiBtn.setAttribute("aria-busy", loading ? "true" : "false");
            var icon = aiBtn.querySelector(".btn-ai-grade__icon");
            var text = aiBtn.querySelector(".btn-ai-grade__text");
            var loader = aiBtn.querySelector(".btn-ai-grade__loader");
            if (icon) {
                icon.hidden = loading;
            }
            if (text) {
                text.textContent = loading ? t.aiGrading : i18n.aiGradeBtn || text.textContent;
            }
            if (loader) {
                loader.hidden = !loading;
            }
        }

        function setAiStatus(text, kind) {
            if (!aiStatus) {
                return;
            }
            aiStatus.textContent = text || "";
            aiStatus.className = "ai-grade-status" + (kind ? " ai-grade-" + kind : "");
        }

        function resetAi(enabled) {
            setAiLoading(false);
            if (aiBtn) {
                aiBtn.disabled = !enabled;
            }
            setAiStatus("", "");
        }

        function flash(el) {
            if (!el) {
                return;
            }
            el.classList.add("ai-filled");
            window.setTimeout(function () {
                el.classList.remove("ai-filled");
            }, 2000);
        }

        function runAiGrade() {
            var qId = currentEl.value;
            var store = qId ? dataStore(qId) : null;
            var url = window.AI_GRADE_URL;
            if (!store || !url) {
                return;
            }
            if (!store.getAttribute("data-ans-text") && store.getAttribute("data-has-ai-gradable") !== "1") {
                setAiStatus(t.aiNoAnswer, "error");
                return;
            }
            setAiLoading(true);
            setAiStatus("", "");
            var csrf = document.querySelector("[name=csrfmiddlewaretoken]");
            fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrf ? csrf.value : "",
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: JSON.stringify({ question_id: parseInt(qId, 10), max_points: G.maxPoints(qId) }),
            })
                .then(function (res) {
                    if (!res.ok) {
                        throw new Error("HTTP " + res.status);
                    }
                    return res.json();
                })
                .then(function (data) {
                    setAiLoading(false);
                    if (currentEl.value !== qId) {
                        return; // istifadəçi artıq başqa suala keçib
                    }
                    if (!data.ok) {
                        setAiStatus(data.error || t.aiError, "error");
                        return;
                    }
                    scoreEl.value = data.score;
                    feedbackEl.value = data.explanation || "";
                    modalDirty = true;
                    flash(scoreEl);
                    flash(feedbackEl);
                    var parts = [];
                    if (data.cached) {
                        parts.push(t.aiCached);
                    }
                    if (data.remaining !== undefined && data.limit !== undefined) {
                        parts.push(
                            t.aiQuotaInfo
                                .replace("{remaining}", data.remaining)
                                .replace("{limit}", data.limit)
                                .replace("{window}", data.window || "")
                        );
                    }
                    setAiStatus(parts.join(" · "), "success");
                })
                .catch(function () {
                    setAiLoading(false);
                    setAiStatus(t.aiError, "error");
                });
        }

        /* ---- göndərmə ----------------------------------------------------- */
        function submitNow() {
            submitConfirmed = true;
            G.markSaving(t.stateSaving);
            if (mainSaveBtn) {
                mainSaveBtn.disabled = true;
                mainSaveBtn.setAttribute("aria-busy", "true");
            }
            // requestSubmit `submit` hadisəsini yenidən atır; bayraq ikinci dövrü buraxır.
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit();
            } else {
                form.submit();
            }
        }

        if (form) {
            form.addEventListener("submit", function (event) {
                if (submitConfirmed) {
                    return;
                }
                event.preventDefault();
                var invalid = G.normalizeAll();
                if (invalid.length) {
                    G.focusQuestion(invalid[0]);
                    return; // oxunmayan bal var — təsdiq dialoqu açılmır
                }
                if (!G.changedCount()) {
                    return;
                }
                if (typeof window.openActionConfirmModal !== "function") {
                    submitNow();
                    return;
                }
                window.openActionConfirmModal({
                    title: t.confirmTitle,
                    message: t.confirmMessage,
                    confirmLabel: mainSaveBtn ? mainSaveBtn.textContent.trim() : "",
                    confirmButtonClass: "btn btn-success",
                    onConfirm: submitNow,
                });
            });
        }

        window.addEventListener("beforeunload", function (event) {
            if (!submitConfirmed && G.changedCount()) {
                event.preventDefault();
                event.returnValue = "";
            }
        });

        if (backBtn) {
            backBtn.addEventListener("click", function (event) {
                if (!G.changedCount() || event.metaKey || event.ctrlKey || event.shiftKey) {
                    return;
                }
                event.preventDefault();
                pendingNavigationUrl = backBtn.getAttribute("href");
                openWarning();
            });
        }

        /* ---- bağlamalar --------------------------------------------------- */
        root.addEventListener("click", function (event) {
            var opener = event.target.closest("[data-tca-open]");
            if (opener) {
                event.preventDefault();
                openModal(opener.getAttribute("data-tca-open"));
            }
        });

        [scoreEl, maxEl, feedbackEl].forEach(function (el) {
            if (el) {
                el.addEventListener("input", function () {
                    modalDirty = true;
                    if (el === scoreEl && !G.isBadInput(scoreEl)) {
                        G.setInvalid(scoreEl, false);
                    }
                });
            }
        });

        scoreEl.addEventListener("blur", function () {
            var qId = currentEl.value;
            if (G.isBadInput(scoreEl)) {
                G.setInvalid(scoreEl, true);
            } else if (qId && scoreEl.value.trim()) {
                G.normalizeScoreField(scoreEl, G.maxPoints(qId));
            }
        });

        scoreEl.addEventListener("keydown", function (event) {
            if (event.key !== "Enter" || event.isComposing) {
                return;
            }
            event.preventDefault();
            if (G.neighbour(currentEl.value, 1)) {
                move(1);
            } else if (applyModal()) {
                closeModal();
            }
        });

        document.getElementById("modalCloseBtn").addEventListener("click", attemptClose);
        document.getElementById("modalCancelBtn").addEventListener("click", attemptClose);
        document.getElementById("modalSaveBtn").addEventListener("click", function () {
            if (applyModal()) {
                closeModal();
            }
        });
        if (prevBtn) {
            prevBtn.addEventListener("click", function () {
                move(-1);
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener("click", function () {
                move(1);
            });
        }
        if (aiBtn) {
            aiBtn.addEventListener("click", function (event) {
                event.preventDefault();
                runAiGrade();
            });
        }
        document.getElementById("warningCancelBtn").addEventListener("click", closeWarning);
        document.getElementById("warningConfirmBtn").addEventListener("click", confirmWarning);

        // Fona klik (mousedown + mouseup eyni yerdə) — mətn seçimi zamanı yanlış bağlanmasın.
        var downOnScrim = false;
        backdrop.addEventListener("mousedown", function (event) {
            downOnScrim = event.target === backdrop;
        });
        backdrop.addEventListener("mouseup", function (event) {
            if (downOnScrim && event.target === backdrop) {
                attemptClose();
            }
            downOnScrim = false;
        });

        document.addEventListener("keydown", function (event) {
            if (isOpen(warning)) {
                if (event.key === "Escape") {
                    event.preventDefault();
                    closeWarning();
                } else if (event.key === "Tab") {
                    G.trapFocus(event, warning);
                }
                return;
            }
            if (isOpen(backdrop)) {
                if (event.key === "Escape") {
                    event.preventDefault();
                    attemptClose();
                } else if (event.key === "Tab") {
                    G.trapFocus(event, modal);
                } else if (event.altKey && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
                    event.preventDefault();
                    move(event.key === "ArrowLeft" ? -1 : 1);
                } else if ((event.ctrlKey || event.metaKey) && String(event.key).toLowerCase() === "s") {
                    event.preventDefault(); // brauzerin «Səhifəni saxla» dialoqu açılmasın
                }
                return;
            }
            if ((event.ctrlKey || event.metaKey) && !event.altKey && String(event.key).toLowerCase() === "s") {
                if (document.querySelector(".modal.show")) {
                    return; // təsdiq dialoqu artıq açıqdır
                }
                event.preventDefault();
                if (mainSaveBtn && !mainSaveBtn.disabled && form) {
                    if (typeof form.requestSubmit === "function") {
                        form.requestSubmit(mainSaveBtn);
                    } else {
                        mainSaveBtn.click();
                    }
                }
            }
        });
    }

    if (typeof window.EMSReady === "function") {
        window.EMSReady(init);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
