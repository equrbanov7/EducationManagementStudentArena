import { cloneFiles, modeForLanguage, readJsonScript } from './utils.js';

function buildFallbackQuestion(ctx) {
    return {
        id: null,
        number: 1,
        title: "",
        problem_statement: "",
        input_description: "",
        output_description: "",
        example_input: "",
        example_output: "",
        language: ctx.config.selectedLanguage || "html",
        language_display: "",
        max_score: "",
        time_limit_seconds: "",
        memory_limit_mb: "",
        initial_files: ctx.fallbackFiles,
        starter_files: ctx.fallbackStarterFiles,
        visible_test_cases: ctx.fallbackVisibleTests,
        selected_language: ctx.config.selectedLanguage || "html"
    };
}

function normalizeQuestion(ctx, rawQuestion, index) {
    var starterFiles = cloneFiles(rawQuestion.starter_files || ctx.fallbackStarterFiles);
    var initialFiles = cloneFiles(rawQuestion.initial_files || starterFiles || ctx.fallbackFiles);
    if (!initialFiles.length) {
        initialFiles = [{ name: "index.html", content: "", language: "html", is_main: true }];
    }
    if (!starterFiles.length) {
        starterFiles = cloneFiles(initialFiles);
    }
    return {
        id: rawQuestion.id || null,
        number: rawQuestion.number || index + 1,
        title: rawQuestion.title || "",
        problemStatement: rawQuestion.problem_statement || "",
        inputDescription: rawQuestion.input_description || "",
        outputDescription: rawQuestion.output_description || "",
        exampleInput: rawQuestion.example_input || "",
        exampleOutput: rawQuestion.example_output || "",
        language: rawQuestion.language || ctx.config.selectedLanguage || "html",
        languageDisplay: rawQuestion.language_display || rawQuestion.language || "",
        maxScore: rawQuestion.max_score,
        timeLimitSeconds: rawQuestion.time_limit_seconds,
        memoryLimitMb: rawQuestion.memory_limit_mb,
        files: initialFiles,
        starterFiles: starterFiles,
        visibleTests: Array.isArray(rawQuestion.visible_test_cases) ? rawQuestion.visible_test_cases : [],
        selectedLanguage: rawQuestion.selected_language || rawQuestion.language || ctx.config.selectedLanguage || "html",
        fileIndex: 0,
        latestSubmission: rawQuestion.latest_submission || null,
        stdin: ""
    };
}

export function createCodingExamContext() {
    var ctx = {
        config: window.CODING_EXAM_CONFIG || {}
    };
    ctx.modeForLanguage = modeForLanguage;
    ctx.i18n = ctx.config.i18n || {};
    ctx.fallbackFiles = readJsonScript("coding-initial-files", []);
    ctx.fallbackStarterFiles = readJsonScript("coding-starter-files", []);
    ctx.fallbackVisibleTests = readJsonScript("coding-visible-test-cases", []);
    ctx.rawQuestions = readJsonScript("coding-questions", []);
    ctx.languageModes = readJsonScript("coding-language-modes", {});
    ctx.currentQuestionIndex = 0;
    ctx.currentFileIndex = 0;
    ctx.autosaveTimer = null;
    ctx.hasUnsavedChanges = false;
    ctx.isSubmitting = false;
    ctx.isDark = true;
    ctx.isSettingEditorValue = false;
    ctx.previewRunId = 0;
    ctx.browserRunHasOutput = false;
    ctx.previewNonce = ctx.config.cspNonce || "";

    ctx.shell = document.getElementById("codingExamShell");
    ctx.workspace = document.getElementById("codingWorkspace");
    ctx.editorTextArea = document.getElementById("codingEditor");
    ctx.fileList = document.getElementById("codingFileList");
    ctx.currentFileName = document.getElementById("codingCurrentFileName");
    ctx.statusNode = document.getElementById("codingStatus");
    ctx.outputNode = document.getElementById("codingOutput");
    ctx.errorsNode = document.getElementById("codingErrors");
    ctx.stdinNode = document.getElementById("codingStdin");
    ctx.languageSelect = document.getElementById("codingLanguageSelect");
    ctx.runBtn = document.getElementById("codingRunBtn");
    ctx.submitBtn = document.getElementById("codingSubmitBtn");
    ctx.resetBtn = document.getElementById("codingResetBtn");
    ctx.createFileBtn = document.getElementById("codingCreateFileBtn");
    ctx.makeMainFileBtn = document.getElementById("codingMakeMainFileBtn");
    ctx.renameFileBtn = document.getElementById("codingRenameFileBtn");
    ctx.deleteFileBtn = document.getElementById("codingDeleteFileBtn");
    ctx.fullscreenBtn = document.getElementById("codingFullscreenBtn");
    ctx.toggleFilesBtn = document.getElementById("codingToggleFilesBtn");
    ctx.themeToggle = document.getElementById("codingThemeToggle");
    ctx.fontSizeSelect = document.getElementById("codingFontSize");
    ctx.timerNode = document.getElementById("codingTimer");
    ctx.timerValue = document.getElementById("codingTimerValue");
    ctx.previewFrame = document.getElementById("codingPreviewFrame");
    ctx.previewConsoleNode = document.getElementById("codingPreviewConsole");
    ctx.browserReloadBtn = document.getElementById("codingBrowserReload");
    ctx.browserTabTitleNode = document.querySelector(".coding-browser-tab__title");
    ctx.browserUrlNode = document.getElementById("codingBrowserUrl");
    ctx.currentQuestionNumNode = document.getElementById("codingCurrentQuestionNum");
    ctx.totalQuestionCountNode = document.getElementById("codingTotalQuestionCount");
    ctx.answeredCountNode = document.getElementById("codingAnsweredCount");
    ctx.answeredTotalCountNode = document.getElementById("codingAnsweredTotalCount");
    ctx.sidebarAnsweredCountNode = document.getElementById("codingSidebarAnsweredCount");
    ctx.unansweredCountNode = document.getElementById("codingUnansweredCount");
    ctx.progressFillNode = document.getElementById("codingProgressFill");
    ctx.questionLabelNode = document.getElementById("codingQuestionLabel");
    ctx.questionTextNode = document.getElementById("codingQuestionText");
    ctx.prevQuestionBtn = document.getElementById("codingPrevQuestionBtn");
    ctx.nextQuestionBtn = document.getElementById("codingNextQuestionBtn");
    ctx.questionNavButtons = document.querySelectorAll("[data-coding-question-nav]");
    ctx.confirmModalNode = document.getElementById("codingConfirmModal");
    ctx.confirmModalTitle = document.getElementById("codingConfirmModalTitle");
    ctx.confirmModalBody = document.getElementById("codingConfirmModalBody");
    ctx.confirmModalConfirm = document.getElementById("codingConfirmModalConfirm");
    ctx.fileNameModalNode = document.getElementById("codingFileNameModal");
    ctx.fileNameForm = document.getElementById("codingFileNameForm");
    ctx.fileNameModalTitle = document.getElementById("codingFileNameModalTitle");
    ctx.fileNameInput = document.getElementById("codingFileNameInput");
    ctx.fileNameError = document.getElementById("codingFileNameError");
    ctx.fileNameModalConfirm = document.getElementById("codingFileNameModalConfirm");
    ctx.consoleMetaNode = document.getElementById("codingConsoleMeta");
    ctx.consoleClearBtn = document.getElementById("codingConsoleClear");
    ctx.stdinHintNode = document.getElementById("codingStdinHint");
    ctx.timeWarning = window.ExamTimeWarning
        ? window.ExamTimeWarning.init({
            storageKey: "coding_exam_" + String(ctx.config.examId || "") + "_attempt_" + String(ctx.config.attemptId || "") + "_five_minute_warning",
            thresholdSeconds: 300,
            autoCloseMs: 5000
        })
        : null;

    if (!ctx.editorTextArea || typeof CodeMirror === "undefined") {
        return null;
    }

    ctx.questionStates = (Array.isArray(ctx.rawQuestions) && ctx.rawQuestions.length ? ctx.rawQuestions : [buildFallbackQuestion(ctx)])
        .map(function (rawQuestion, index) { return normalizeQuestion(ctx, rawQuestion, index); });
    ctx.files = ctx.questionStates[0].files;

    ctx.editor = CodeMirror.fromTextArea(ctx.editorTextArea, {
        lineNumbers: true,
        indentUnit: 4,
        tabSize: 4,
        indentWithTabs: false,
        matchBrackets: true,
        autoCloseBrackets: true,
        theme: "monokai",
        mode: modeForLanguage(ctx.questionStates[0].selectedLanguage || "html", ctx.languageModes),
        viewportMargin: Infinity,
        styleActiveLine: true,
        extraKeys: {
            "Ctrl-Space": function (cm) { ctx.triggerAutocomplete(cm); },
            "Cmd-Space": function (cm) { ctx.triggerAutocomplete(cm); },
            "Ctrl-Enter": function () { ctx.runCode(); },
            "Cmd-Enter": function () { ctx.runCode(); },
            "Ctrl-S": function () { ctx.autosave(); },
            "Cmd-S": function () { ctx.autosave(); },
            "Ctrl-/": function (cm) { cm.toggleComment(); },
            "Cmd-/": function (cm) { cm.toggleComment(); },
            "F11": function () {
                if (ctx.workspace) {
                    ctx.workspace.classList.toggle("is-fullscreen");
                    setTimeout(function () { ctx.editor.refresh(); }, 30);
                }
            },
            "Esc": function () {
                if (ctx.workspace && ctx.workspace.classList.contains("is-fullscreen")) {
                    ctx.workspace.classList.remove("is-fullscreen");
                    setTimeout(function () { ctx.editor.refresh(); }, 30);
                }
            },
            "Tab": function (cm) {
                if (cm.somethingSelected()) {
                    cm.indentSelection("add");
                } else {
                    cm.replaceSelection(Array(cm.getOption("indentUnit") + 1).join(" "), "end", "+input");
                }
            }
        },
        hintOptions: {
            completeSingle: false,
            closeOnUnfocus: true,
            alignWithWord: true
        }
    });

    return ctx;
}
