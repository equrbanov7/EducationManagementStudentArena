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
            ns.progress.syncMarkedQuestionInput(ctx);
            ns.config.refreshFormCsrfToken(ctx);
            ctx.finishRequestInFlight = true;
            ns.draft.persistLocalDraft(ctx);
            ns.draft.sendDraft(ctx, "finish").catch(function () {
                ctx.finishRequestInFlight = false;
            });
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

        // EXAM-P1-04 strict delivery: server-dən gələn təhlükəsiz sual gövdəsini
        // yer tutucuya inject et və dinamik input/mark düymələrini yenidən bağla.
        injectServerDeliveredBody: function (ctx, slideElement, html) {
            if (!html || !slideElement || slideElement.getAttribute("data-server-delivery") !== "1") {
                return;
            }
            slideElement.innerHTML = html;
            slideElement.setAttribute("data-server-delivery", "hydrated");

            if (ns.draft && typeof ns.draft.bindAnswerInputs === "function") {
                ns.draft.bindAnswerInputs(ctx, slideElement);
            }

            var markButton = slideElement.querySelector("[data-mark-question]");
            if (markButton) {
                var questionId = String(markButton.dataset.questionId || "");
                var isMarked = ctx.markedQuestionIds && ctx.markedQuestionIds.has(questionId);
                markButton.classList.toggle("is-marked", !!isMarked);
                markButton.setAttribute("aria-pressed", isMarked ? "true" : "false");
                var icon = markButton.querySelector("i");
                var label = markButton.querySelector("[data-mark-label]");
                if (icon) { icon.className = isMarked ? "fas fa-bookmark" : "far fa-bookmark"; }
                if (label) { label.textContent = isMarked ? ctx.i18n.marked : ctx.i18n.mark; }
                markButton.addEventListener("click", function () {
                    ns.progress.toggleMarkedQuestion(ctx, markButton.dataset.questionId);
                });
            }

            ns.progress.updateProgress(ctx);
        },

        // EXAM-P1-04: serverə "sual göstərildi" siqnalı — server İLK göstərilməni
        // qeyd edir və countdown-un SERVER qalığını qaytarır; local deadline onunla
        // əvəzlənir (devtools ilə uzatma, reload-da sıfırlanma aradan qalxır).
        syncQuestionTimerWithServer: function (ctx, slideElement) {
            if (!ctx.questionSeenUrl || !window.fetch) {
                return Promise.resolve(null);
            }
            var questionId = slideElement ? slideElement.getAttribute("data-question-id") : "";
            if (!questionId) {
                return Promise.resolve(null);
            }
            var formData = new FormData();
            formData.append("question_id", questionId);
            formData.append("csrfmiddlewaretoken", ns.config.getCsrfToken(ctx));
            return fetch(ctx.questionSeenUrl, {
                method: "POST",
                body: formData,
                credentials: "same-origin"
            })
                .then(function (res) { return res.ok ? res.json() : null; })
                .then(function (data) {
                    if (!data || !data.success) {
                        return data;
                    }
                    // Strict delivery: təhlükəsiz gövdəni yer tutucuya inject et
                    // (slide görünür olmasa da — məzmun bir dəfə hidrat olunsun).
                    if (data.html) {
                        ns.timers.injectServerDeliveredBody(ctx, slideElement, data.html);
                    }
                    if (data.remaining_seconds === null || data.remaining_seconds === undefined) {
                        return data;
                    }
                    // Slide bu arada dəyişibsə köhnə countdown-u tətbiq etmə.
                    if (ctx.questionTimerSlide !== slideElement) {
                        return data;
                    }
                    ctx.questionTimerDeadlineMs = Date.now() + (data.remaining_seconds * 1000);
                    if (typeof ctx.questionTimerTick === "function") {
                        ctx.questionTimerTick();
                    }
                    return data;
                })
                .catch(function () {
                    // Şəbəkə xətasında local countdown davam edir (geriyə-uyğun).
                    return null;
                });
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
                ns.timers.syncQuestionTimerWithServer(ctx, slideElement);

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

                        var timeUpMsg = (ctx.i18n.timeUpMessage || "").trim();
                        if (!timeUpMsg) {
                            timeUpMsg = "\u23F0 Time is up!";
                        }
                        ns.notifications.show(timeUpMsg, "error", 0);

                        ns.progress.syncMarkedQuestionInput(ctx);
                        ns.config.refreshFormCsrfToken(ctx);
                        ns.draft.persistLocalDraft(ctx);

                        setTimeout(function () {
                            ctx.finishRequestInFlight = true;
                            ns.draft.sendDraft(ctx, "finish").catch(function () {
                                ctx.finishRequestInFlight = false;
                            });
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
