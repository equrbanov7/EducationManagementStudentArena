import { extensionLanguage, safeFileName } from './utils.js';

export function bindCodingExamEvents(ctx) {
    // Open the hint widget as the user types alpha-numeric identifiers.
    // We skip whitespace and punctuation to avoid noisy popups; cm.state
    // gating prevents recursive triggers while a hint is already open.
    ctx.editor.on("inputRead", function (cm, change) {
        if (!CodeMirror.showHint || cm.state.completionActive) {
            return;
        }
        var text = change.text && change.text[0];
        if (!text || text.length !== 1) {
            return;
        }
        if (!/[A-Za-z_<.\-]/.test(text)) {
            return;
        }
        // Defer so the change is committed first.
        setTimeout(function () { ctx.triggerAutocomplete(cm); }, 50);
    });

    ctx.editor.on("change", function () {
        if (ctx.isSettingEditorValue) {
            return;
        }
        ctx.syncEditorToFile();
        ctx.updateProgress();
        ctx.updateStdinHint();
        ctx.queueAutosave(2500);
    });

    if (ctx.languageSelect) {
        ctx.languageSelect.addEventListener("change", function () {
            var question = ctx.currentQuestion();
            question.selectedLanguage = ctx.languageSelect.value;
            ctx.editor.setOption("mode", ctx.modeForLanguage(extensionLanguage(ctx.currentFile() && ctx.currentFile().name, ctx.languageSelect.value), ctx.languageModes));
            ctx.updateLanguagePreviewVisibility();
            ctx.updateProgress();
            ctx.updateStdinHint();
            ctx.queueAutosave(500);
        });
    }

    if (ctx.stdinNode) {
        ctx.stdinNode.addEventListener("input", ctx.syncStdinToQuestion);
    }

    document.querySelectorAll("[data-coding-tab]").forEach(function (tab) {
        tab.addEventListener("click", function () {
            ctx.switchTab(tab.getAttribute("data-coding-tab"));
            if (tab.getAttribute("data-coding-tab") === "preview") {
                ctx.browserRunHasOutput = false;
                ctx.previewRunId += 1;
                if (ctx.previewConsoleNode) ctx.previewConsoleNode.textContent = "";
                ctx.renderPreview({
                    runId: ctx.previewRunId,
                    executeCurrentJavaScriptOnly: ctx.shouldExecuteCurrentJavaScriptOnly()
                });
            }
        });
    });

    if (ctx.confirmModalConfirm) {
        ctx.confirmModalConfirm.addEventListener("click", function () {
            var action = ctx.pendingConfirmAction;
            ctx.pendingConfirmAction = null;
            ctx.hideBootstrapModal(ctx.confirmModalNode);
            if (action) {
                action();
            }
        });
    }

    if (ctx.fileNameForm) {
        ctx.fileNameForm.addEventListener("submit", function (event) {
            event.preventDefault();
            var name = safeFileName(ctx.fileNameInput ? ctx.fileNameInput.value : "");
            if (!name) {
                if (ctx.fileNameError) ctx.fileNameError.textContent = ctx.i18n.invalidFileName || "Invalid file name.";
                return;
            }
            if (ctx.files.some(function (file, index) {
                return file.name === name && index !== ctx.pendingFileNameAllowedIndex;
            })) {
                if (ctx.fileNameError) ctx.fileNameError.textContent = ctx.i18n.duplicateFileName || "Duplicate file name.";
                return;
            }
            var action = ctx.pendingFileNameAction;
            ctx.pendingFileNameAction = null;
            ctx.pendingFileNameAllowedIndex = -1;
            ctx.hideBootstrapModal(ctx.fileNameModalNode);
            if (action) {
                action(name);
            }
        });
    }

    if (ctx.runBtn) {
        ctx.runBtn.addEventListener("click", ctx.runCode);
    }
    if (ctx.submitBtn) {
        ctx.submitBtn.addEventListener("click", ctx.openFinishConfirmModal);
    }
    if (ctx.prevQuestionBtn) {
        ctx.prevQuestionBtn.addEventListener("click", function () {
            ctx.switchQuestion(ctx.currentQuestionIndex - 1);
        });
    }
    if (ctx.nextQuestionBtn) {
        ctx.nextQuestionBtn.addEventListener("click", function () {
            ctx.switchQuestion(ctx.currentQuestionIndex + 1);
        });
    }
    ctx.questionNavButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            var index = parseInt(button.getAttribute("data-target-index"), 10) || 0;
            ctx.switchQuestion(index);
        });
    });
    if (ctx.resetBtn) {
        // "Reset code" now only clears the run-result side (output, errors,
        // preview, stdin, status pill). It does NOT delete student files
        // or rewind their code.
        ctx.resetBtn.addEventListener("click", function () {
            if (ctx.outputNode) ctx.outputNode.innerHTML = "";
            if (ctx.errorsNode) ctx.errorsNode.textContent = "";
            if (ctx.previewConsoleNode) ctx.previewConsoleNode.textContent = "";
            if (ctx.previewFrame) {
                ctx.previewFrame.removeAttribute("src");
                ctx.previewFrame.removeAttribute("srcdoc");
            }
            if (ctx.stdinNode) ctx.stdinNode.value = "";
            var question = ctx.currentQuestion();
            if (question) question.stdin = "";
            ctx.inlineTerminalActive = false;
            ctx.inlineTerminalPrompts = [];
            ctx.inlineTerminalValues = [];
            ctx.inlineTerminalIndex = 0;
            ctx.lastInteractivePrompts = [];
            ctx.lastInteractiveValues = [];
            ctx.browserRunHasOutput = false;
            ctx.setConsoleMeta("");
            ctx.updateStdinHint();
            ctx.setStatus(ctx.i18n.consoleCleared || "Console cleared.");
            ctx.switchTab("output");
        });
    }
    if (ctx.createFileBtn) {
        ctx.createFileBtn.addEventListener("click", function () {
            ctx.openFileNameModal({
                title: ctx.i18n.createFile || "Create File",
                initialValue: "new_file.txt",
                confirmText: ctx.i18n.save || "Save",
                onConfirm: function (name) {
                    if (ctx.files.some(function (file) { return file.name === name; })) {
                        return;
                    }
                    ctx.syncEditorToFile();
                    ctx.files.push({ name: name, content: "", language: extensionLanguage(name, ctx.languageSelect.value), is_main: false });
                    ctx.currentFileIndex = ctx.files.length - 1;
                    ctx.syncLanguageToCurrentFile();
                    ctx.renderFiles();
                    ctx.setEditorForCurrentFile();
                    ctx.updateLanguagePreviewVisibility();
                    ctx.updateProgress();
                    ctx.queueAutosave(100);
                }
            });
        });
    }
    if (ctx.makeMainFileBtn) {
        ctx.makeMainFileBtn.addEventListener("click", function () {
            ctx.setMainFile(ctx.currentFileIndex);
            ctx.renderFiles();
            ctx.setEditorForCurrentFile();
            ctx.updateProgress();
            ctx.queueAutosave(100);
        });
    }
    if (ctx.renameFileBtn) {
        ctx.renameFileBtn.addEventListener("click", function () {
            var file = ctx.currentFile();
            if (!file) return;
            ctx.openFileNameModal({
                title: ctx.i18n.renameFile || "Rename File",
                initialValue: file.name,
                confirmText: ctx.i18n.save || "Save",
                allowedIndex: ctx.currentFileIndex,
                onConfirm: function (name) {
                    if (ctx.files.some(function (item, index) { return index !== ctx.currentFileIndex && item.name === name; })) {
                        return;
                    }
                    file.name = name;
                    file.language = extensionLanguage(name, ctx.languageSelect.value);
                    ctx.syncLanguageToCurrentFile();
                    ctx.renderFiles();
                    ctx.setEditorForCurrentFile();
                    ctx.updateLanguagePreviewVisibility();
                    ctx.updateProgress();
                    ctx.queueAutosave(100);
                }
            });
        });
    }
    if (ctx.deleteFileBtn) {
        ctx.deleteFileBtn.addEventListener("click", function () {
            if (ctx.files.length <= 1) {
                return;
            }
            var file = ctx.currentFile();
            ctx.openConfirmModal({
                title: ctx.i18n.deleteConfirmTitle || "Delete file?",
                body: (ctx.i18n.deleteConfirmBody || "This file will be removed.") + (file ? " (" + file.name + ")" : ""),
                confirmText: ctx.i18n.confirm || "Confirm",
                danger: true,
                onConfirm: function () {
                    var wasMain = ctx.currentFile() && ctx.currentFile().is_main;
                    ctx.files.splice(ctx.currentFileIndex, 1);
                    ctx.currentFileIndex = Math.max(0, ctx.currentFileIndex - 1);
                    if (wasMain && ctx.files[0]) {
                        ctx.files[0].is_main = true;
                    }
                    ctx.syncLanguageToCurrentFile();
                    ctx.renderFiles();
                    ctx.setEditorForCurrentFile();
                    ctx.updateLanguagePreviewVisibility();
                    ctx.updateProgress();
                    ctx.queueAutosave(100);
                }
            });
        });
    }
    if (ctx.fullscreenBtn) {
        ctx.fullscreenBtn.addEventListener("click", function () {
            ctx.workspace.classList.toggle("is-fullscreen");
            setTimeout(function () {
                ctx.editor.refresh();
            }, 30);
        });
    }
    if (ctx.toggleFilesBtn) {
        ctx.toggleFilesBtn.addEventListener("click", function () {
            var editorPane = document.querySelector(".coding-editor-pane");
            ctx.setFilesCollapsed(!(editorPane && editorPane.classList.contains("is-files-collapsed")));
        });
    }
    if (ctx.themeToggle) {
        ctx.themeToggle.addEventListener("click", function () {
            ctx.isDark = !ctx.isDark;
            ctx.editor.setOption("theme", ctx.isDark ? "monokai" : "eclipse");
            if (ctx.shell) {
                ctx.shell.classList.toggle("is-light-editor", !ctx.isDark);
            }
        });
    }
    if (ctx.fontSizeSelect) {
        ctx.fontSizeSelect.addEventListener("change", function () {
            var wrapper = ctx.editor.getWrapperElement();
            wrapper.style.fontSize = ctx.fontSizeSelect.value + "px";
            ctx.editor.refresh();
        });
    }

    if (ctx.browserReloadBtn) {
        ctx.browserReloadBtn.addEventListener("click", function () {
            ctx.previewRunId += 1;
            if (ctx.previewConsoleNode) ctx.previewConsoleNode.textContent = "";
            ctx.renderPreview({
                runId: ctx.previewRunId,
                executeCurrentJavaScriptOnly: ctx.shouldExecuteCurrentJavaScriptOnly()
            });
        });
    }

    window.addEventListener("message", ctx.handlePreviewMessage);

    window.addEventListener("beforeunload", function (event) {
        if (!ctx.hasUnsavedChanges || ctx.isSubmitting) {
            return;
        }
        event.preventDefault();
        event.returnValue = "";
    });

    // Console "Clear" button — wipe output/errors and re-show the empty
    // state placeholder. Doesn't touch stdin or the editor, since those
    // are independent of run output.
    if (ctx.consoleClearBtn) {
        ctx.consoleClearBtn.addEventListener("click", function () {
            if (ctx.outputNode) ctx.outputNode.innerHTML = "";
            if (ctx.errorsNode) ctx.errorsNode.textContent = "";
            if (ctx.previewConsoleNode) ctx.previewConsoleNode.textContent = "";
            // Reset stdin so a subsequent Run starts from scratch.
            if (ctx.stdinNode) ctx.stdinNode.value = "";
            var question = ctx.currentQuestion();
            if (question) question.stdin = "";
            ctx.updateStdinHint();
            ctx.inlineTerminalActive = false;
            ctx.inlineTerminalPrompts = [];
            ctx.inlineTerminalValues = [];
            ctx.inlineTerminalIndex = 0;
            ctx.lastInteractivePrompts = [];
            ctx.lastInteractiveValues = [];
            ctx.setConsoleMeta("");
            ctx.setStatus(ctx.i18n.consoleCleared || "Console cleared.");
        });
    }
}
