import { extensionLanguage, safeFileName } from './utils.js';

export function installUi(ctx) {
    ctx.setStatus = function setStatus(message) {
        if (ctx.statusNode) {
            ctx.statusNode.textContent = message || "";
        }
    };

    ctx.setConsoleMeta = function setConsoleMeta(text) {
        if (ctx.consoleMetaNode) {
            ctx.consoleMetaNode.textContent = text || "";
        }
    };

    ctx.setEditorForCurrentFile = function setEditorForCurrentFile() {
        var file = ctx.currentFile();
        if (!file) {
            return;
        }
        ctx.isSettingEditorValue = true;
        try {
            ctx.editor.setValue(file.content || "");
        } finally {
            ctx.isSettingEditorValue = false;
        }
        ctx.editor.setOption("mode", ctx.modeForLanguage(extensionLanguage(file.name, ctx.languageSelect.value), ctx.languageModes));
        if (ctx.currentFileName) {
            ctx.currentFileName.textContent = file.name + (file.is_main ? " · " + (ctx.i18n.mainFile || "Main File") : "");
        }
        setTimeout(function () {
            ctx.editor.refresh();
        }, 20);
    };

    ctx.renderFiles = function renderFiles() {
        if (!ctx.fileList) {
            return;
        }
        ctx.fileList.innerHTML = "";
        ctx.files.forEach(function (file, index) {
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "coding-file-item" + (index === ctx.currentFileIndex ? " is-active" : "");

            var icon = document.createElement("i");
            icon.className = file.is_main ? "fas fa-star" : "far fa-file-code";
            btn.appendChild(icon);

            var label = document.createElement("span");
            label.textContent = file.name;
            btn.appendChild(label);

            if (file.is_main) {
                var badge = document.createElement("small");
                badge.textContent = ctx.i18n.mainFile || "Main File";
                btn.appendChild(badge);
            }

            btn.addEventListener("click", function () {
                ctx.syncEditorToFile();
                ctx.currentFileIndex = index;
                ctx.syncLanguageToCurrentFile();
                ctx.renderFiles();
                ctx.setEditorForCurrentFile();
                ctx.updateLanguagePreviewVisibility();
            });
            ctx.fileList.appendChild(btn);
        });
        ctx.updateFileActionButtons();
    };

    ctx.fileSnapshot = function fileSnapshot(filesToSnapshot) {
        return JSON.stringify((Array.isArray(filesToSnapshot) ? filesToSnapshot : []).map(function (file) {
            return {
                name: file.name || "",
                content: file.content || "",
                is_main: Boolean(file.is_main)
            };
        }));
    };

    ctx.isQuestionAnswered = function isQuestionAnswered(question) {
        if (!question) {
            return false;
        }
        var starterSnapshot = ctx.fileSnapshot(question.starterFiles);
        var currentSnapshot = ctx.fileSnapshot(question.files);
        if (starterSnapshot && starterSnapshot !== currentSnapshot) {
            return true;
        }
        if (!starterSnapshot) {
            return (question.files || []).some(function (file) {
                return String(file.content || "").trim() !== "";
            });
        }
        return false;
    };

    ctx.updateQuestionNav = function updateQuestionNav() {
        ctx.questionNavButtons.forEach(function (button) {
            var index = parseInt(button.getAttribute("data-target-index"), 10) || 0;
            var question = ctx.questionStates[index];
            var isCurrent = index === ctx.currentQuestionIndex;
            var isAnswered = ctx.isQuestionAnswered(question);

            button.classList.toggle("is-current", isCurrent);
            button.classList.toggle("is-answered", isAnswered);
            button.setAttribute("aria-current", isCurrent ? "step" : "false");
        });
    };

    ctx.questionBodyText = function questionBodyText(question) {
        var lines = [];
        if (question.problemStatement) {
            lines.push(question.problemStatement);
        }
        if (question.inputDescription) {
            lines.push((ctx.i18n.inputDescription || "Input description") + ":\n" + question.inputDescription);
        }
        if (question.outputDescription) {
            lines.push((ctx.i18n.outputDescription || "Output description") + ":\n" + question.outputDescription);
        }
        if (question.exampleInput) {
            lines.push((ctx.i18n.exampleInput || "Example input") + ":\n" + question.exampleInput);
        }
        if (question.exampleOutput) {
            lines.push((ctx.i18n.exampleOutput || "Example output") + ":\n" + question.exampleOutput);
        }
        return lines.join("\n\n");
    };

    ctx.updateProgress = function updateProgress() {
        var total = ctx.questionStates.length || 1;
        var answered = ctx.questionStates.filter(ctx.isQuestionAnswered).length;
        var unanswered = Math.max(total - answered, 0);
        if (ctx.currentQuestionNumNode) ctx.currentQuestionNumNode.textContent = String(ctx.currentQuestionIndex + 1);
        if (ctx.totalQuestionCountNode) ctx.totalQuestionCountNode.textContent = String(total);
        if (ctx.answeredCountNode) ctx.answeredCountNode.textContent = String(answered);
        if (ctx.answeredTotalCountNode) ctx.answeredTotalCountNode.textContent = String(total);
        if (ctx.sidebarAnsweredCountNode) ctx.sidebarAnsweredCountNode.textContent = String(answered);
        if (ctx.unansweredCountNode) ctx.unansweredCountNode.textContent = String(unanswered);
        if (ctx.progressFillNode) {
            ctx.progressFillNode.style.width = total ? Math.round(((ctx.currentQuestionIndex + 1) / total) * 100) + "%" : "0%";
        }
        ctx.updateQuestionNav();
    };

    ctx.updateQuestionControls = function updateQuestionControls() {
        var isFirst = ctx.currentQuestionIndex === 0;
        var isLast = ctx.currentQuestionIndex >= ctx.questionStates.length - 1;
        if (ctx.prevQuestionBtn) {
            ctx.prevQuestionBtn.disabled = isFirst;
        }
        if (ctx.nextQuestionBtn) {
            ctx.nextQuestionBtn.hidden = isLast;
        }
    };

    ctx.renderProblem = function renderProblem() {
        var question = ctx.currentQuestion();
        if (ctx.questionLabelNode) {
            ctx.questionLabelNode.textContent = "Q" + question.number;
        }
        if (ctx.questionTextNode) {
            ctx.questionTextNode.textContent = ctx.questionBodyText(question) || question.title || "";
        }
        ctx.updateProgress();
        ctx.updateQuestionControls();
    };

    ctx.setMainFile = function setMainFile(index) {
        if (!ctx.files[index]) {
            return;
        }
        ctx.files.forEach(function (file, fileIndex) {
            file.is_main = fileIndex === index;
        });
        ctx.currentQuestion().files = ctx.files;
    };

    ctx.updateFileActionButtons = function updateFileActionButtons() {
        var file = ctx.currentFile();
        if (ctx.makeMainFileBtn) {
            ctx.makeMainFileBtn.disabled = !file || Boolean(file.is_main);
        }
        if (ctx.renameFileBtn) {
            ctx.renameFileBtn.disabled = !file;
        }
        if (ctx.deleteFileBtn) {
            ctx.deleteFileBtn.disabled = !file || ctx.files.length <= 1;
        }
    };

    ctx.setFilesCollapsed = function setFilesCollapsed(collapsed) {
        var editorPane = document.querySelector(".coding-editor-pane");
        if (!editorPane || !ctx.toggleFilesBtn) {
            return;
        }
        var icon = ctx.toggleFilesBtn.querySelector("i");
        editorPane.classList.toggle("is-files-collapsed", collapsed);
        ctx.toggleFilesBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
        ctx.toggleFilesBtn.setAttribute("title", collapsed ? (ctx.i18n.showFiles || "Show files") : (ctx.i18n.hideFiles || "Hide files"));
        ctx.toggleFilesBtn.setAttribute("aria-label", collapsed ? (ctx.i18n.showFiles || "Show files") : (ctx.i18n.hideFiles || "Hide files"));
        if (icon) {
            icon.className = collapsed ? "fas fa-folder" : "fas fa-folder-open";
        }
        setTimeout(function () {
            ctx.editor.refresh();
        }, 230);
    };

    ctx.updateLanguagePreviewVisibility = function updateLanguagePreviewVisibility() {
        var previewAllowed = ctx.canPreviewCurrentQuestion();
        document.querySelectorAll("[data-preview-tab]").forEach(function (tab) {
            tab.hidden = !previewAllowed;
        });
        if (!previewAllowed && document.querySelector('[data-coding-panel="preview"].active')) {
            ctx.switchTab("output");
        }
    };

    ctx.switchQuestion = function switchQuestion(index) {
        if (index === ctx.currentQuestionIndex || !ctx.questionStates[index]) {
            return;
        }
        if (ctx.hasUnsavedChanges) {
            ctx.autosave();
        }
        ctx.syncEditorToFile();
        ctx.syncStdinToQuestion();
        ctx.currentQuestionIndex = index;
        var question = ctx.currentQuestion();
        ctx.files = question.files;
        ctx.currentFileIndex = Math.min(question.fileIndex || 0, Math.max(ctx.files.length - 1, 0));
        if (ctx.languageSelect) {
            ctx.languageSelect.value = question.selectedLanguage || question.language || ctx.config.selectedLanguage;
            ctx.syncBootstrapSelect(ctx.languageSelect);
        }
        ctx.syncLanguageToCurrentFile();
        ctx.renderProblem();
        ctx.renderFiles();
        ctx.setEditorForCurrentFile();
        if (ctx.outputNode) ctx.outputNode.innerHTML = "";
        if (ctx.errorsNode) ctx.errorsNode.textContent = "";
        if (ctx.stdinNode) ctx.stdinNode.value = question.stdin || "";
        if (ctx.previewConsoleNode) ctx.previewConsoleNode.textContent = "";
        if (ctx.previewFrame) {
            ctx.previewFrame.removeAttribute("src");
            ctx.previewFrame.removeAttribute("srcdoc");
        }
        ctx.updateLanguagePreviewVisibility();
    };

    ctx.getUnansweredCount = function getUnansweredCount() {
        return Math.max(ctx.questionStates.length - ctx.questionStates.filter(ctx.isQuestionAnswered).length, 0);
    };

    ctx.queueAutosave = function queueAutosave(delay) {
        ctx.hasUnsavedChanges = true;
        clearTimeout(ctx.autosaveTimer);
        ctx.autosaveTimer = setTimeout(function () {
            ctx.autosave();
        }, delay || 2500);
    };

    ctx.switchTab = function switchTab(tabName) {
        document.querySelectorAll("[data-coding-tab]").forEach(function (tab) {
            tab.classList.toggle("active", tab.getAttribute("data-coding-tab") === tabName);
        });
        document.querySelectorAll("[data-coding-panel]").forEach(function (panel) {
            panel.classList.toggle("active", panel.getAttribute("data-coding-panel") === tabName);
        });
    };

    ctx.bootstrapModal = function bootstrapModal(node) {
        if (!node || !window.bootstrap || !window.bootstrap.Modal) {
            return null;
        }
        return window.bootstrap.Modal.getOrCreateInstance(node);
    };

    ctx.hideBootstrapModal = function hideBootstrapModal(node) {
        var modal = ctx.bootstrapModal(node);
        if (modal) {
            modal.hide();
        }
    };

    ctx.pendingConfirmAction = null;
    ctx.openConfirmModal = function openConfirmModal(options) {
        options = options || {};
        if (!ctx.confirmModalNode || !ctx.confirmModalConfirm || !ctx.bootstrapModal(ctx.confirmModalNode)) {
            if (window.confirm(options.body || options.title || "")) {
                if (options.onConfirm) options.onConfirm();
            }
            return;
        }
        ctx.pendingConfirmAction = options.onConfirm || null;
        if (ctx.confirmModalTitle) ctx.confirmModalTitle.textContent = options.title || "";
        if (ctx.confirmModalBody) ctx.confirmModalBody.textContent = options.body || "";
        ctx.confirmModalConfirm.textContent = options.confirmText || ctx.i18n.confirm || "Confirm";
        ctx.confirmModalConfirm.classList.toggle("btn-danger", options.danger !== false);
        ctx.confirmModalConfirm.classList.toggle("btn-primary", options.danger === false);
        ctx.bootstrapModal(ctx.confirmModalNode).show();
    };

    ctx.pendingFileNameAction = null;
    ctx.pendingFileNameAllowedIndex = -1;
    ctx.openFileNameModal = function openFileNameModal(options) {
        options = options || {};
        if (!ctx.fileNameModalNode || !ctx.fileNameInput || !ctx.fileNameForm || !ctx.bootstrapModal(ctx.fileNameModalNode)) {
            var fallbackName = safeFileName(window.prompt(options.title || ctx.i18n.fileNamePrompt || "File name", options.initialValue || ""));
            if (fallbackName && options.onConfirm) {
                options.onConfirm(fallbackName);
            }
            return;
        }
        ctx.pendingFileNameAction = options.onConfirm || null;
        ctx.pendingFileNameAllowedIndex = Number.isInteger(options.allowedIndex) ? options.allowedIndex : -1;
        if (ctx.fileNameModalTitle) ctx.fileNameModalTitle.textContent = options.title || ctx.i18n.fileNamePrompt || "File name";
        if (ctx.fileNameModalConfirm) ctx.fileNameModalConfirm.textContent = options.confirmText || ctx.i18n.save || "Save";
        if (ctx.fileNameError) ctx.fileNameError.textContent = "";
        ctx.fileNameInput.value = options.initialValue || "";
        ctx.bootstrapModal(ctx.fileNameModalNode).show();
        window.setTimeout(function () {
            ctx.fileNameInput.focus();
            ctx.fileNameInput.select();
        }, 150);
    };
}
