(function (ns, window, document) {
    "use strict";

    function slideHasSelectedOption(slide) {
        return slide.querySelector('input[name^="q_"]:checked') !== null;
    }

    function slideHasWrittenText(slide) {
        var textAnswer = slide.querySelector("textarea.written-answer");
        return Boolean(textAnswer && textAnswer.value.trim().length > 0);
    }

    function slideHasAttachedFiles(slide) {
        var fileInput = slide.querySelector('input[type="file"][data-take-exam-file-input]');
        if (fileInput && fileInput.files && fileInput.files.length > 0) {
            return true;
        }
        var previewArea = slide.querySelector(".file-preview-area");
        if (previewArea && previewArea.querySelector(".file-preview-item") !== null) {
            return true;
        }
        return Boolean(previewArea && Number(previewArea.dataset.existingFileCount || "0") > 0);
    }

    function slideHasPaintAnswer(slide) {
        var paintCard = slide.querySelector(".paint-card");
        if (!paintCard) {
            return false;
        }

        var enabledHidden = paintCard.querySelector(".paint-enabled-hidden");
        if (!enabledHidden || enabledHidden.value !== "1") {
            return false;
        }

        var clearHidden = paintCard.querySelector(".paint-clear-hidden");
        if (clearHidden && clearHidden.value === "1") {
            return false;
        }

        var dataHidden = paintCard.querySelector(".paint-data-hidden");
        if (dataHidden && dataHidden.value && dataHidden.value.length > 50) {
            return true;
        }

        return Boolean(paintCard.dataset.existingUrl);
    }

    function loadMarkedQuestionIds(ctx) {
        try {
            var storedValue = localStorage.getItem(ctx.markedStorageKey);
            if (storedValue) {
                var parsedStored = JSON.parse(storedValue);
                if (Array.isArray(parsedStored)) {
                    return parsedStored.map(String);
                }
            }
        } catch (error) {
            // Fall back to the server-saved value below.
        }

        try {
            var parsed = JSON.parse((ctx.markedQuestionIdsField && ctx.markedQuestionIdsField.value) || "[]");
            return Array.isArray(parsed) ? parsed.map(String) : [];
        } catch (error) {
            return [];
        }
    }

    ns.progress = {
        init: function (ctx) {
            ctx.markedQuestionIds = new Set(loadMarkedQuestionIds(ctx));
            ns.progress.syncMarkedQuestionInput(ctx);
            window.updateProgress = function () {
                ns.progress.updateProgress(ctx);
            };
        },

        isSlideAnswered: function (slide) {
            return (
                slideHasSelectedOption(slide) ||
                slideHasWrittenText(slide) ||
                slideHasAttachedFiles(slide) ||
                slideHasPaintAnswer(slide)
            );
        },

        getAnsweredCount: function (ctx) {
            var answeredCount = 0;
            ctx.slides.forEach(function (slide) {
                if (ns.progress.isSlideAnswered(slide)) {
                    answeredCount += 1;
                }
            });
            return answeredCount;
        },

        getUnansweredCount: function (ctx) {
            return Math.max(ctx.totalSlides - ns.progress.getAnsweredCount(ctx), 0);
        },

        getSlideQuestionId: function (slide) {
            return slide && slide.dataset ? String(slide.dataset.questionId || "") : "";
        },

        syncMarkedQuestionInput: function (ctx) {
            if (ctx.markedQuestionIdsField) {
                ctx.markedQuestionIdsField.value = JSON.stringify(Array.from(ctx.markedQuestionIds));
            }
        },

        persistMarkedQuestionIds: function (ctx) {
            ns.progress.syncMarkedQuestionInput(ctx);
            try {
                localStorage.setItem(ctx.markedStorageKey, JSON.stringify(Array.from(ctx.markedQuestionIds)));
            } catch (error) {
                // Mark state is a convenience helper; exam submission must continue even if storage fails.
            }
        },

        toggleMarkedQuestion: function (ctx, questionId) {
            var normalizedId = String(questionId || "");
            if (!normalizedId) {
                return;
            }
            if (ctx.markedQuestionIds.has(normalizedId)) {
                ctx.markedQuestionIds.delete(normalizedId);
            } else {
                ctx.markedQuestionIds.add(normalizedId);
            }
            ns.progress.persistMarkedQuestionIds(ctx);
            ctx.hasUnsavedChanges = true;
            ctx.answerRevision += 1;
            ns.progress.updateProgress(ctx);
            ns.draft.queueAutoSave(ctx, 1000);
        },

        updateMarkedButtons: function (ctx) {
            ctx.markButtons.forEach(function (button) {
                var questionId = String(button.dataset.questionId || "");
                var isMarked = ctx.markedQuestionIds.has(questionId);
                var icon = button.querySelector("i");
                var label = button.querySelector("[data-mark-label]");

                button.classList.toggle("is-marked", isMarked);
                button.setAttribute("aria-pressed", isMarked ? "true" : "false");
                if (icon) {
                    icon.className = isMarked ? "fas fa-bookmark" : "far fa-bookmark";
                }
                if (label) {
                    label.textContent = isMarked ? ctx.i18n.marked : ctx.i18n.mark;
                }
            });
        },

        updateQuestionNav: function (ctx) {
            ctx.questionNavButtons.forEach(function (button) {
                var index = Number(button.dataset.targetIndex || 0);
                var slide = ctx.slides[index];
                var questionId = String(button.dataset.questionId || ns.progress.getSlideQuestionId(slide));
                var isCurrent = index === ctx.currentIndex;
                var isAnswered = slide ? ns.progress.isSlideAnswered(slide) : false;
                var isMarked = ctx.markedQuestionIds.has(questionId);

                button.classList.toggle("is-current", isCurrent);
                button.classList.toggle("is-answered", isAnswered);
                button.classList.toggle("is-marked", isMarked);
                button.setAttribute("aria-current", isCurrent ? "step" : "false");
            });
        },

        updateProgress: function (ctx) {
            var answeredCount = ns.progress.getAnsweredCount(ctx);
            var unansweredCount = ns.progress.getUnansweredCount(ctx);
            ctx.answeredCountEl.textContent = answeredCount;
            if (ctx.sidebarAnsweredCountEl) {
                ctx.sidebarAnsweredCountEl.textContent = answeredCount;
            }
            if (ctx.unansweredCountEl) {
                ctx.unansweredCountEl.textContent = unansweredCount;
            }
            var percent = ctx.totalSlides > 0 ? ((ctx.currentIndex + 1) / ctx.totalSlides) * 100 : 0;
            ctx.progressFill.style.width = percent + "%";
            ns.progress.updateQuestionNav(ctx);
            ns.progress.updateMarkedButtons(ctx);
        }
    };
})(window.EMSTakeExam = window.EMSTakeExam || {}, window, document);
