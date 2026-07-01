import {
    countNonEmptyLines,
    detectStdinReadCount,
    extensionLanguage,
    hintHelperFor,
} from './utils.js';

export function installStateHelpers(ctx) {
    // Trigger autocomplete using the helper appropriate for the current
    // file's language. This indirection keeps add-language work small:
    // register a helper, list it in hintHelperFor, done.
    ctx.triggerAutocomplete = function triggerAutocomplete(cm) {
        if (!CodeMirror.showHint) {
            return;
        }
        var language = ctx.getActiveFileLanguage();
        var helperName = hintHelperFor(language);
        var helper = CodeMirror.helpers && CodeMirror.helpers.hint && CodeMirror.helpers.hint[helperName];
        cm.showHint({
            hint: helper || CodeMirror.hint.anyword,
            completeSingle: false,
            closeOnUnfocus: true
        });
    };

    ctx.currentQuestion = function currentQuestion() {
        return ctx.questionStates[ctx.currentQuestionIndex] || ctx.questionStates[0];
    };

    ctx.currentFile = function currentFile() {
        return ctx.files[ctx.currentFileIndex] || ctx.files[0];
    };

    ctx.syncEditorToFile = function syncEditorToFile() {
        var file = ctx.currentFile();
        if (file) {
            file.content = ctx.editor.getValue();
        }
        var question = ctx.currentQuestion();
        if (question) {
            question.files = ctx.files;
            question.fileIndex = ctx.currentFileIndex;
            question.selectedLanguage = ctx.languageSelect ? ctx.languageSelect.value : question.selectedLanguage;
        }
    };

    ctx.syncStdinToQuestion = function syncStdinToQuestion() {
        var question = ctx.currentQuestion();
        if (question && ctx.stdinNode) {
            question.stdin = ctx.stdinNode.value || "";
        }
        ctx.updateStdinHint();
    };

    ctx.getSelectedLanguage = function getSelectedLanguage() {
        return ctx.languageSelect ? ctx.languageSelect.value : ctx.currentQuestion().selectedLanguage;
    };

    ctx.canSelectLanguage = function canSelectLanguage(value) {
        if (!ctx.languageSelect || !value) {
            return false;
        }
        return Array.prototype.some.call(ctx.languageSelect.options, function (option) {
            return option.value === value;
        });
    };

    ctx.executionLanguageForFile = function executionLanguageForFile(file, fallbackLanguage) {
        var inferred = file ? extensionLanguage(file.name, fallbackLanguage) : fallbackLanguage;
        if (inferred === "css") {
            inferred = "html";
        }
        return ctx.canSelectLanguage(inferred) ? inferred : (fallbackLanguage || ctx.getSelectedLanguage());
    };

    ctx.syncLanguageToCurrentFile = function syncLanguageToCurrentFile() {
        if (!ctx.languageSelect) {
            return ctx.getSelectedLanguage();
        }
        var nextLanguage = ctx.executionLanguageForFile(ctx.currentFile(), ctx.languageSelect.value);
        if (nextLanguage && ctx.languageSelect.value !== nextLanguage) {
            ctx.languageSelect.value = nextLanguage;
            ctx.syncBootstrapSelect(ctx.languageSelect);
        }
        ctx.currentQuestion().selectedLanguage = ctx.languageSelect.value;
        return ctx.languageSelect.value;
    };

    ctx.getActiveFileLanguage = function getActiveFileLanguage() {
        var active = ctx.currentFile();
        return active ? extensionLanguage(active.name, ctx.getSelectedLanguage()) : ctx.getSelectedLanguage();
    };

    ctx.hasHtmlFile = function hasHtmlFile() {
        return ctx.files.some(function (file) {
            return String(file.name || "").toLowerCase().match(/\.html?$/);
        });
    };

    ctx.canPreviewCurrentQuestion = function canPreviewCurrentQuestion() {
        var selected = ctx.getSelectedLanguage();
        var activeLanguage = ctx.getActiveFileLanguage();
        return selected === "html" || selected === "javascript" || activeLanguage === "html" || ctx.hasHtmlFile();
    };

    ctx.shouldExecuteCurrentJavaScriptOnly = function shouldExecuteCurrentJavaScriptOnly() {
        if (ctx.hasHtmlFile()) {
            return false;
        }
        var selected = ctx.getSelectedLanguage();
        var activeLanguage = ctx.getActiveFileLanguage();
        return selected === "javascript" || activeLanguage === "javascript";
    };

    ctx.shouldOpenPreviewAfterRun = function shouldOpenPreviewAfterRun() {
        return ctx.hasHtmlFile() || ctx.getSelectedLanguage() === "html" || ctx.getActiveFileLanguage() === "html";
    };

    ctx.syncBootstrapSelect = function syncBootstrapSelect(select) {
        if (window.EMSBootstrapSelect && select) {
            window.EMSBootstrapSelect.sync(select);
        }
    };

    ctx.collectPayload = function collectPayload() {
        ctx.syncEditorToFile();
        ctx.syncStdinToQuestion();
        var activeFile = ctx.currentFile();
        var selectedLanguage = ctx.executionLanguageForFile(
            activeFile,
            ctx.languageSelect ? ctx.languageSelect.value : ctx.currentQuestion().selectedLanguage
        );
        if (ctx.languageSelect && ctx.languageSelect.value !== selectedLanguage) {
            ctx.languageSelect.value = selectedLanguage;
            ctx.syncBootstrapSelect(ctx.languageSelect);
        }
        ctx.currentQuestion().selectedLanguage = selectedLanguage;
        return {
            question_id: ctx.currentQuestion().id,
            selected_language: selectedLanguage,
            active_file_name: activeFile ? activeFile.name : "",
            files: ctx.files,
            stdin: ctx.currentQuestion().stdin || ""
        };
    };

    ctx.collectSubmitPayload = function collectSubmitPayload() {
        ctx.syncEditorToFile();
        return {
            questions: ctx.questionStates.map(function (question) {
                var questionFiles = question.files || [];
                var activeFile = questionFiles[question.fileIndex || 0] || questionFiles[0] || null;
                var selectedLanguage = ctx.executionLanguageForFile(
                    activeFile,
                    question.selectedLanguage || question.language || ctx.config.selectedLanguage
                );
                return {
                    question_id: question.id,
                    selected_language: selectedLanguage,
                    active_file_name: activeFile ? activeFile.name : "",
                    files: questionFiles,
                    stdin: ""
                };
            })
        };
    };

    ctx.updateStdinHint = function updateStdinHint() {
        if (!ctx.stdinHintNode) {
            return;
        }
        var question = ctx.currentQuestion();
        if (!question) {
            ctx.stdinHintNode.textContent = "";
            ctx.stdinHintNode.className = "coding-console-input-hint";
            return;
        }
        var language = ctx.getSelectedLanguage();
        var execFile = ctx.resolveExecutionFile();
        var requiredReads = detectStdinReadCount(language, execFile && execFile.content);
        var providedLines = countNonEmptyLines(ctx.stdinNode ? ctx.stdinNode.value : "");

        if (requiredReads === 0) {
            ctx.stdinHintNode.textContent = "";
            ctx.stdinHintNode.className = "coding-console-input-hint";
            return;
        }
        if (providedLines < requiredReads) {
            ctx.stdinHintNode.textContent = (ctx.i18n.stdinNeeded || "Program expects {count} input value(s).").replace("{count}", String(requiredReads));
            ctx.stdinHintNode.className = "coding-console-input-hint coding-console-input-hint--warn";
            return;
        }
        var extra = providedLines - requiredReads;
        if (extra > 0) {
            ctx.stdinHintNode.textContent = (ctx.i18n.stdinExtra || "{extra} extra input line(s) will be ignored.").replace("{extra}", String(extra));
            ctx.stdinHintNode.className = "coding-console-input-hint coding-console-input-hint--muted";
            return;
        }
        ctx.stdinHintNode.textContent = (ctx.i18n.stdinReady || "Stdin ready ({count} line(s)).").replace("{count}", String(providedLines));
        ctx.stdinHintNode.className = "coding-console-input-hint coding-console-input-hint--ok";
    };
}
