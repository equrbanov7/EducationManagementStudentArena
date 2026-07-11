(function (ns, window, document) {
    "use strict";

    function disableSlideInputs(slideElement) {
        var inputs = slideElement.querySelectorAll("input, textarea");
        inputs.forEach(function (input) {
            input.disabled = true;
        });
        slideElement.style.opacity = "0.7";
        slideElement.style.pointerEvents = "none";
    }

    function syncQuestionTimerState(ctx) {
        if (!ctx.questionTimerSlide || !ctx.questionTimerDeadlineMs) {
            return 0;
        }

        var secondsLeft = ns.config.getSecondsUntil(ctx.questionTimerDeadlineMs);
        ctx.questionTimerSlide.setAttribute("data-time-limit", String(secondsLeft));
        return secondsLeft;
    }

    function handleQuestionTimerExpiry(ctx, slideElement) {
        ns.timers.stopQuestionTimer(ctx);
        slideElement.setAttribute("data-time-limit", "0");
        slideElement.setAttribute("data-time-expired", "true");
        ctx.qTimerContainer.style.display = "flex";
        ctx.qTimerValue.textContent = "00:00";
        ctx.qTimerContainer.classList.add("danger");
        disableSlideInputs(slideElement);

        if (ctx.currentIndex < ctx.totalSlides - 1) {
            ns.navigation.showSlide(ctx, ctx.currentIndex + 1);
        } else {
            var hiddenInput = document.createElement("input");
            hiddenInput.type = "hidden";
            hiddenInput.name = "submit_action";
            hiddenInput.value = "finish";
            ctx.examForm.appendChild(hiddenInput);
            ns.progress.syncMarkedQuestionInput(ctx);
            ns.config.refreshFormCsrfToken(ctx);
            // EXAM-P1-07: finish edərkən localStorage-dakı plaintext cavab
            // qaralamasını SAXLAMA — təmizlə (paylaşılan cihazda qalıq qalmasın).
            ns.draft.clearLocalDraft(ctx);
            localStorage.removeItem(ctx.storageKey);
            ctx.examForm.submit();
        }
        ns.progress.updateProgress(ctx);
    }

    function refreshVisibleTimers(ctx) {
        if (!document.hidden) {
            if (typeof ctx.questionTimerTick === "function") {
                ctx.questionTimerTick();
            }
            if (typeof ctx.examTimerTick === "function") {
                ctx.examTimerTick();
            }
        }
    }

    ns.timers = {
        initTimeWarning: function (ctx) {
            ctx.examTimeWarning = window.ExamTimeWarning
                ? window.ExamTimeWarning.init({
                    storageKey: ctx.timeWarningStorageKey,
                    thresholdSeconds: 300,
                    autoCloseMs: 5000
                })
                : null;
        },

        stopQuestionTimer: function (ctx) {
            syncQuestionTimerState(ctx);

            if (ctx.questionTimerInterval) {
                clearInterval(ctx.questionTimerInterval);
            }

            ctx.questionTimerInterval = null;
            ctx.questionTimerTick = null;
            ctx.questionTimerSlide = null;
            ctx.questionTimerDeadlineMs = null;
            ctx.qTimerContainer.classList.remove("danger");
        },

        startQuestionTimer: function (ctx, slideElement) {
            ns.timers.stopQuestionTimer(ctx);

            if (slideElement.getAttribute("data-time-expired") === "true") {
                ctx.qTimerContainer.style.display = "flex";
                ctx.qTimerValue.textContent = "00:00";
                ctx.qTimerContainer.classList.add("danger");
                disableSlideInputs(slideElement);
                return;
            }

            var timeLimit = parseInt(slideElement.getAttribute("data-time-limit"), 10) || 0;

            if (timeLimit > 0) {
                ctx.qTimerContainer.style.display = "flex";
                ctx.questionTimerSlide = slideElement;
                ctx.questionTimerDeadlineMs = Date.now() + (timeLimit * 1000);

                ctx.questionTimerTick = function () {
                    var secondsLeft = syncQuestionTimerState(ctx);
                    ctx.qTimerValue.textContent = ns.config.formatTime(secondsLeft);
                    ctx.qTimerContainer.classList.toggle("danger", secondsLeft > 0 && secondsLeft <= 10);

                    if (secondsLeft <= 0) {
                        handleQuestionTimerExpiry(ctx, slideElement);
                    }
                };

                ctx.questionTimerTick();
                if (ctx.questionTimerSlide) {
                    ctx.questionTimerInterval = setInterval(ctx.questionTimerTick, 1000);
                }
            } else {
                ctx.qTimerContainer.style.display = "none";
            }
        },

        initExamTimer: function (ctx) {
            if (ctx.remainingSeconds === null || ctx.remainingSeconds === undefined) {
                return;
            }

            var remainingSeconds = parseInt(ctx.remainingSeconds, 10);

            if (!isNaN(remainingSeconds) && remainingSeconds > 0) {
                var timerValueElement = document.getElementById("timer-value");
                var timerContainer = document.getElementById("exam-timer-container");
                var examTimerDeadlineMs = Date.now() + (remainingSeconds * 1000);

                ctx.examTimerTick = function () {
                    remainingSeconds = ns.config.getSecondsUntil(examTimerDeadlineMs);
                    timerValueElement.textContent = ns.config.formatTime(remainingSeconds);
                    if (ctx.examTimeWarning) {
                        ctx.examTimeWarning.maybeShow(remainingSeconds);
                    }

                    if (remainingSeconds <= 0) {
                        if (ctx.examTimerInterval) {
                            clearInterval(ctx.examTimerInterval);
                            ctx.examTimerInterval = null;
                        }
                        ns.timers.stopQuestionTimer(ctx);
                        timerValueElement.textContent = "00:00";

                        ns.navigation.prepareExamFinishNavigation(ctx);

                        var timeUpMsg = (ctx.i18n.timeUpMessage || "").trim();
                        if (!timeUpMsg) {
                            timeUpMsg = "\u23F0 Time is up!";
                        }
                        ns.notifications.show(timeUpMsg, "error", 0);

                        var hiddenInput = document.createElement("input");
                        hiddenInput.type = "hidden";
                        hiddenInput.name = "submit_action";
                        hiddenInput.value = "finish";
                        ctx.examForm.appendChild(hiddenInput);

                        ns.progress.syncMarkedQuestionInput(ctx);
                        ns.config.refreshFormCsrfToken(ctx);
                        ns.draft.persistLocalDraft(ctx);
                        localStorage.removeItem(ctx.storageKey);

                        setTimeout(function () {
                            ctx.examForm.submit();
                        }, 1500);
                        return;
                    }

                    if (remainingSeconds < 60) {
                        timerContainer.style.backgroundColor = "#fee2e2";
                        timerContainer.style.color = "#dc2626";
                    }
                };

                ctx.examTimerTick();
                ctx.examTimerInterval = setInterval(ctx.examTimerTick, 1000);
            } else {
                document.getElementById("timer-value").textContent = "00:00";
            }
        },

        initVisibilityRefresh: function (ctx) {
            document.addEventListener("visibilitychange", function () {
                refreshVisibleTimers(ctx);
            });
            window.addEventListener("focus", function () {
                refreshVisibleTimers(ctx);
            });
        }
    };
})(window.EMSTakeExam = window.EMSTakeExam || {}, window, document);
