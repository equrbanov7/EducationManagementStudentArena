(function (ns, window, document) {
    "use strict";

    var defaultI18n = {
        autosaveSaving: "autosave_saving",
        autosaveSaved: "autosave_saved",
        draftSaved: "draft_saved",
        draftSavedWithCheck: "draft_saved_with_check",
        saveError: "save_error",
        saveErrorRetry: "save_error_retry",
        btnSaving: "btn_saving",
        btnSaved: "btn_saved",
        btnDraftSaved: "btn_draft_saved",
        finishUnansweredCount: "confirm_finish_unanswered_count",
        finishAllAnswered: "confirm_finish_all_answered",
        timeUpMessage: "time_up_auto_submit",
        mark: "Mark",
        marked: "Marked"
    };

    function readScriptData() {
        var node = document.getElementById("take-exam-script-data");
        if (!node) {
            return {};
        }
        try {
            return JSON.parse(node.textContent || "{}");
        } catch (error) {
            return {};
        }
    }

    function autoSaveSpread(examId, attemptId, jitterMaxMs) {
        if (!jitterMaxMs) {
            return 0;
        }
        var seed = String(examId || "") + ":" + String(attemptId || "");
        var hash = 0;
        for (var index = 0; index < seed.length; index += 1) {
            hash = ((hash << 5) - hash) + seed.charCodeAt(index);
            hash |= 0;
        }
        return Math.abs(hash) % (jitterMaxMs + 1);
    }

    function getCookie(name) {
        // Faza 6.3: mərkəzi EMSCore.getCookie (core/csrf.js).
        return window.EMSCore.getCookie(name);
    }

    ns.config = {
        createContext: function () {
            var scriptData = readScriptData();
            var examForm = document.getElementById("exam-form");
            if (!examForm) {
                return null;
            }

            var examId = examForm.dataset.examId;
            var attemptId = examForm.dataset.attemptId;
            var defaultAutoSaveIntervalMs = 300000;
            var serverAutoSaveIntervalMs = Math.max(
                60000,
                parseInt(examForm.dataset.autosaveIntervalMs || String(defaultAutoSaveIntervalMs), 10) ||
                    defaultAutoSaveIntervalMs
            );
            var autoSaveJitterMaxMs = Math.max(
                0,
                parseInt(examForm.dataset.autosaveJitterMs || "0", 10) || 0
            );
            var autoSaveDelayMs = serverAutoSaveIntervalMs + autoSaveSpread(examId, attemptId, autoSaveJitterMaxMs);

            var slides = document.querySelectorAll(".question-slide");
            return {
                i18n: Object.assign({}, defaultI18n, scriptData.i18n || {}),
                remainingSeconds: scriptData.remainingSeconds,
                slides: slides,
                prevBtn: document.getElementById("prev-btn"),
                nextBtn: document.getElementById("next-btn"),
                finishBtn: document.getElementById("finish-btn"),
                currentQNum: document.getElementById("current-question-num"),
                answeredCountEl: document.getElementById("answered-count"),
                sidebarAnsweredCountEl: document.getElementById("sidebar-answered-count"),
                unansweredCountEl: document.getElementById("unanswered-count"),
                progressFill: document.getElementById("progress-fill"),
                examForm: examForm,
                saveDraftBtn: document.getElementById("save-draft-btn"),
                loadingScreen: document.getElementById("examLoadingScreen"),
                questionTransitionSkeleton: document.getElementById("questionTransitionSkeleton"),
                questionNavButtons: document.querySelectorAll("[data-question-nav]"),
                markButtons: document.querySelectorAll("[data-mark-question]"),
                markedQuestionIdsField: document.getElementById("marked-question-ids-field"),
                qTimerContainer: document.getElementById("question-timer-container"),
                qTimerValue: document.getElementById("question-timer-value"),
                questionTimerInterval: null,
                questionTimerTick: null,
                questionTimerSlide: null,
                questionTimerDeadlineMs: null,
                examTimerInterval: null,
                examTimerTick: null,
                currentIndex: 0,
                totalSlides: slides.length,
                hasUnsavedChanges: false,
                autoSaveTimer: null,
                autoSaveRequestInFlight: false,
                answerRevision: 0,
                questionTransitionTimer: null,
                questionTransitionHideTimer: null,
                dirtyQuestionIds: new Set(),
                binaryDirtyQuestionIds: new Set(),
                examType: examForm.dataset.examType,
                autoSaveBinaryUploadsEnabled: examForm.dataset.autosaveBinaryUploadsEnabled === "1",
                examId: examId,
                attemptId: attemptId,
                storageKey: "exam_" + examId + "_attempt_" + attemptId + "_currentIndex",
                draftStorageKey: "exam_" + examId + "_attempt_" + attemptId + "_draft",
                markedStorageKey: "exam_" + examId + "_attempt_" + attemptId + "_marked",
                timeWarningStorageKey: "exam_" + examId + "_attempt_" + attemptId + "_five_minute_warning",
                markedQuestionIds: new Set(),
                examTimeWarning: null,
                autoSaveDelayMs: autoSaveDelayMs,
                fileState: {},
                persistDraftTimer: null,
                progressUpdateTimer: null,
                isFinishingExam: false,
                finishRequestInFlight: false
            };
        },

        getCsrfToken: function (ctx) {
            var cookieToken = getCookie("csrftoken");
            if (cookieToken) {
                return cookieToken;
            }
            var input = ctx.examForm.querySelector('input[name="csrfmiddlewaretoken"]');
            return input ? input.value : "";
        },

        refreshFormCsrfToken: function (ctx) {
            var cookieToken = getCookie("csrftoken");
            var input = ctx.examForm.querySelector('input[name="csrfmiddlewaretoken"]');
            if (cookieToken && input && input.value !== cookieToken) {
                input.value = cookieToken;
            }
        },

        formatTime: function (totalSeconds) {
            var safeSeconds = totalSeconds < 0 ? 0 : totalSeconds;
            var minutes = Math.floor(safeSeconds / 60);
            var seconds = safeSeconds % 60;
            return String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
        },

        getSecondsUntil: function (deadlineMs) {
            if (!deadlineMs) {
                return 0;
            }
            return Math.max(0, Math.ceil((deadlineMs - Date.now()) / 1000));
        }
    };
})(window.EMSTakeExam = window.EMSTakeExam || {}, window, document);
