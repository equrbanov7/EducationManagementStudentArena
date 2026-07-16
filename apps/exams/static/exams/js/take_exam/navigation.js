(function (ns, window, document) {
    "use strict";

    ns.navigation = {
        showSlide: function (ctx, index) {
            ctx.slides.forEach(function (slide) {
                slide.classList.remove("active");
            });

            var currentSlide = ctx.slides[index];
            currentSlide.classList.add("active");

            ctx.currentQNum.textContent = index + 1;

            ctx.prevBtn.style.visibility = index === 0 ? "hidden" : "visible";
            if (index === ctx.totalSlides - 1) {
                ctx.nextBtn.style.display = "none";
            } else {
                ctx.nextBtn.style.display = "flex";
            }

            ctx.currentIndex = index;
            localStorage.setItem(ctx.storageKey, index);
            ns.timers.startQuestionTimer(ctx, currentSlide);
            ns.progress.updateProgress(ctx);
        },

        navigateToSlide: function (ctx, index) {
            if (index < 0 || index >= ctx.totalSlides || index === ctx.currentIndex) {
                return;
            }

            if (!ctx.questionTransitionSkeleton) {
                ns.navigation.showSlide(ctx, index);
                return;
            }

            clearTimeout(ctx.questionTransitionTimer);
            clearTimeout(ctx.questionTransitionHideTimer);
            ctx.questionTransitionSkeleton.classList.add("is-visible");

            ctx.questionTransitionTimer = setTimeout(function () {
                ns.navigation.showSlide(ctx, index);
                ctx.questionTransitionHideTimer = setTimeout(function () {
                    ctx.questionTransitionSkeleton.classList.remove("is-visible");
                }, 120);
            }, 180);
        },

        prepareExamFinishNavigation: function (ctx) {
            ctx.isFinishingExam = true;
            ctx.finishRequestInFlight = false;
            ctx.hasUnsavedChanges = false;
            window.EXAM_SUPERVISION_NAVIGATING = true;
            if (window.ExamSupervision && typeof window.ExamSupervision.destroy === "function") {
                window.ExamSupervision.destroy();
            }
        },

        init: function (ctx) {
            var finishConfirmBackdrop = document.getElementById("finishConfirmBackdrop");
            var cancelFinishBtn = document.getElementById("cancelFinishBtn");
            var confirmFinishBtn = document.getElementById("confirmFinishBtn");
            var finishConfirmSummary = document.getElementById("finishConfirmSummary");

            function updateFinishConfirmSummary() {
                if (!finishConfirmSummary) {
                    return;
                }

                var unansweredCount = ns.progress.getUnansweredCount(ctx);
                if (unansweredCount > 0) {
                    finishConfirmSummary.textContent = ctx.i18n.finishUnansweredCount.replace(
                        "{count}",
                        unansweredCount
                    );
                    finishConfirmSummary.classList.add("is-warning");
                    finishConfirmSummary.classList.remove("is-success");
                    return;
                }

                finishConfirmSummary.textContent = ctx.i18n.finishAllAnswered;
                finishConfirmSummary.classList.add("is-success");
                finishConfirmSummary.classList.remove("is-warning");
            }

            window.addEventListener("beforeunload", function (event) {
                if (!ctx.hasUnsavedChanges || ctx.isFinishingExam) {
                    return;
                }
                ns.draft.persistLocalDraft(ctx);
                event.preventDefault();
                event.returnValue = "";
            });

            ctx.finishBtn.addEventListener("click", function () {
                updateFinishConfirmSummary();
                finishConfirmBackdrop.style.display = "flex";
            });

            cancelFinishBtn.addEventListener("click", function () {
                finishConfirmBackdrop.style.display = "none";
            });

            finishConfirmBackdrop.addEventListener("click", function (event) {
                if (event.target === finishConfirmBackdrop) {
                    finishConfirmBackdrop.style.display = "none";
                }
            });

            confirmFinishBtn.addEventListener("click", function () {
                confirmFinishBtn.disabled = true;
                ctx.finishRequestInFlight = true;
                ns.progress.syncMarkedQuestionInput(ctx);

                ns.draft.sendDraft(ctx, "finish").catch(function () {
                    ctx.finishRequestInFlight = false;
                    confirmFinishBtn.disabled = false;
                });
            });

            ctx.nextBtn.addEventListener("click", function () {
                if (ctx.currentIndex < ctx.totalSlides - 1) {
                    ns.navigation.navigateToSlide(ctx, ctx.currentIndex + 1);
                }
            });
            ctx.prevBtn.addEventListener("click", function () {
                if (ctx.currentIndex > 0) {
                    ns.navigation.navigateToSlide(ctx, ctx.currentIndex - 1);
                }
            });

            ctx.questionNavButtons.forEach(function (button) {
                button.addEventListener("click", function () {
                    var index = Number(button.dataset.targetIndex || 0);
                    if (index >= 0 && index < ctx.totalSlides) {
                        ns.navigation.navigateToSlide(ctx, index);
                    }
                });
            });

            ctx.markButtons.forEach(function (button) {
                button.addEventListener("click", function () {
                    ns.progress.toggleMarkedQuestion(ctx, button.dataset.questionId);
                });
            });

            ns.draft.restoreLocalDraft(ctx);

            var savedIndex = parseInt(localStorage.getItem(ctx.storageKey), 10);
            if (!isNaN(savedIndex) && savedIndex >= 0 && savedIndex < ctx.totalSlides) {
                ctx.currentIndex = savedIndex;
            } else {
                // Yeni kompüterdə localStorage yoxdur: DB-dən bərpa olunan
                // cavabları keç və ilk cavabsız sualdan davam et.
                ctx.currentIndex = Array.from(ctx.slides).findIndex(function (slide) {
                    return !ns.progress.isSlideAnswered(slide);
                });
                if (ctx.currentIndex < 0) {
                    ctx.currentIndex = Math.max(ctx.totalSlides - 1, 0);
                }
            }
            ns.navigation.showSlide(ctx, ctx.currentIndex);
            if (ctx.loadingScreen) {
                window.setTimeout(function () {
                    ctx.loadingScreen.classList.add("is-hidden");
                }, 420);
            }
        }
    };
})(window.EMSTakeExam = window.EMSTakeExam || {}, window, document);
