(function () {
    function readJsonScript(id, fallback) {
        var node = document.getElementById(id);
        if (!node) {
            return fallback;
        }
        try {
            return JSON.parse(node.textContent || "");
        } catch (error) {
            return fallback;
        }
    }

    function formatTime(totalSeconds) {
        var value = Math.max(0, parseInt(totalSeconds, 10) || 0);
        var minutes = Math.floor(value / 60);
        var seconds = value % 60;
        return String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
    }

    function modeForLanguage(language, languageModes) {
        return languageModes[language] || "text/plain";
    }

    function extensionLanguage(name, fallback) {
        var lower = String(name || "").toLowerCase();
        if (lower.endsWith(".py")) return "python";
        if (lower.endsWith(".js")) return "javascript";
        if (lower.endsWith(".cpp") || lower.endsWith(".cc") || lower.endsWith(".cxx") || lower.endsWith(".h")) return "cpp";
        if (lower.endsWith(".java")) return "java";
        if (lower.endsWith(".html") || lower.endsWith(".htm")) return "html";
        if (lower.endsWith(".css")) return "css";
        return fallback || "text";
    }

    function safeFileName(name) {
        var cleaned = String(name || "").trim().replace(/^.*[\\/]/, "");
        return /^[A-Za-z0-9_.-]{1,180}$/.test(cleaned) ? cleaned : "";
    }

    function cloneFiles(files) {
        return (Array.isArray(files) ? files : []).map(function (file) {
            return {
                name: file.name,
                content: file.content || "",
                language: file.language || "text",
                is_main: Boolean(file.is_main)
            };
        });
    }

    function assetName(value) {
        var clean = String(value || "").split("#")[0].split("?")[0].replace(/^\.?\//, "");
        return clean.split("/").pop();
    }

    function escapeScriptText(value) {
        return String(value || "").replace(/<\/script/gi, "<\\/script");
    }

    document.addEventListener("DOMContentLoaded", function () {
        var config = window.CODING_EXAM_CONFIG || {};
        var i18n = config.i18n || {};
        var fallbackFiles = readJsonScript("coding-initial-files", []);
        var fallbackStarterFiles = readJsonScript("coding-starter-files", []);
        var fallbackVisibleTests = readJsonScript("coding-visible-test-cases", []);
        var rawQuestions = readJsonScript("coding-questions", []);
        var languageModes = readJsonScript("coding-language-modes", {});
        var currentQuestionIndex = 0;
        var currentFileIndex = 0;
        var autosaveTimer = null;
        var hasUnsavedChanges = false;
        var isSubmitting = false;
        var isDark = true;
        var isSettingEditorValue = false;
        var previewRunId = 0;
        var browserRunHasOutput = false;
        var previewNonce = config.cspNonce || "";

        var shell = document.getElementById("codingExamShell");
        var workspace = document.getElementById("codingWorkspace");
        var editorTextArea = document.getElementById("codingEditor");
        var fileList = document.getElementById("codingFileList");
        var currentFileName = document.getElementById("codingCurrentFileName");
        var statusNode = document.getElementById("codingStatus");
        var outputNode = document.getElementById("codingOutput");
        var errorsNode = document.getElementById("codingErrors");
        var stdinNode = document.getElementById("codingStdin");
        var languageSelect = document.getElementById("codingLanguageSelect");
        var runBtn = document.getElementById("codingRunBtn");
        var submitBtn = document.getElementById("codingSubmitBtn");
        var resetBtn = document.getElementById("codingResetBtn");
        var createFileBtn = document.getElementById("codingCreateFileBtn");
        var renameFileBtn = document.getElementById("codingRenameFileBtn");
        var deleteFileBtn = document.getElementById("codingDeleteFileBtn");
        var fullscreenBtn = document.getElementById("codingFullscreenBtn");
        var themeToggle = document.getElementById("codingThemeToggle");
        var fontSizeSelect = document.getElementById("codingFontSize");
        var timerNode = document.getElementById("codingTimer");
        var timerValue = document.getElementById("codingTimerValue");
        var previewFrame = document.getElementById("codingPreviewFrame");
        var previewConsoleNode = document.getElementById("codingPreviewConsole");
        var questionNav = document.getElementById("codingQuestionNav");
        var currentQuestionTitleNode = document.getElementById("codingCurrentQuestionTitle");
        var currentQuestionNumNode = document.getElementById("codingCurrentQuestionNum");
        var totalQuestionCountNode = document.getElementById("codingTotalQuestionCount");
        var answeredCountNode = document.getElementById("codingAnsweredCount");
        var totalAnswerCountNode = document.getElementById("codingTotalAnswerCount");
        var progressFillNode = document.getElementById("codingProgressFill");
        var questionLabelNode = document.getElementById("codingQuestionLabel");
        var questionTextNode = document.getElementById("codingQuestionText");
        var prevQuestionBtn = document.getElementById("codingPrevQuestionBtn");
        var nextQuestionBtn = document.getElementById("codingNextQuestionBtn");
        var confirmModalNode = document.getElementById("codingConfirmModal");
        var confirmModalTitle = document.getElementById("codingConfirmModalTitle");
        var confirmModalBody = document.getElementById("codingConfirmModalBody");
        var confirmModalConfirm = document.getElementById("codingConfirmModalConfirm");
        var fileNameModalNode = document.getElementById("codingFileNameModal");
        var fileNameForm = document.getElementById("codingFileNameForm");
        var fileNameModalTitle = document.getElementById("codingFileNameModalTitle");
        var fileNameInput = document.getElementById("codingFileNameInput");
        var fileNameError = document.getElementById("codingFileNameError");
        var fileNameModalConfirm = document.getElementById("codingFileNameModalConfirm");

        if (!editorTextArea || typeof CodeMirror === "undefined") {
            return;
        }

        function buildFallbackQuestion() {
            return {
                id: null,
                number: 1,
                title: "",
                problem_statement: "",
                input_description: "",
                output_description: "",
                example_input: "",
                example_output: "",
                language: config.selectedLanguage || "html",
                language_display: "",
                max_score: "",
                time_limit_seconds: "",
                memory_limit_mb: "",
                initial_files: fallbackFiles,
                starter_files: fallbackStarterFiles,
                visible_test_cases: fallbackVisibleTests,
                selected_language: config.selectedLanguage || "html"
            };
        }

        function normalizeQuestion(rawQuestion, index) {
            var starterFiles = cloneFiles(rawQuestion.starter_files || fallbackStarterFiles);
            var initialFiles = cloneFiles(rawQuestion.initial_files || starterFiles || fallbackFiles);
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
                language: rawQuestion.language || config.selectedLanguage || "html",
                languageDisplay: rawQuestion.language_display || rawQuestion.language || "",
                maxScore: rawQuestion.max_score,
                timeLimitSeconds: rawQuestion.time_limit_seconds,
                memoryLimitMb: rawQuestion.memory_limit_mb,
                files: initialFiles,
                starterFiles: starterFiles,
                visibleTests: Array.isArray(rawQuestion.visible_test_cases) ? rawQuestion.visible_test_cases : [],
                selectedLanguage: rawQuestion.selected_language || rawQuestion.language || config.selectedLanguage || "html",
                fileIndex: 0,
                latestSubmission: rawQuestion.latest_submission || null
            };
        }

        var questionStates = (Array.isArray(rawQuestions) && rawQuestions.length ? rawQuestions : [buildFallbackQuestion()])
            .map(normalizeQuestion);
        var files = questionStates[0].files;

        var editor = CodeMirror.fromTextArea(editorTextArea, {
            lineNumbers: true,
            indentUnit: 4,
            tabSize: 4,
            indentWithTabs: false,
            matchBrackets: true,
            autoCloseBrackets: true,
            theme: "monokai",
            mode: modeForLanguage(questionStates[0].selectedLanguage || "html", languageModes),
            viewportMargin: Infinity
        });

        function currentQuestion() {
            return questionStates[currentQuestionIndex] || questionStates[0];
        }

        function setStatus(message) {
            if (statusNode) {
                statusNode.textContent = message || "";
            }
        }

        function currentFile() {
            return files[currentFileIndex] || files[0];
        }

        function syncEditorToFile() {
            var file = currentFile();
            if (file) {
                file.content = editor.getValue();
            }
            var question = currentQuestion();
            if (question) {
                question.files = files;
                question.fileIndex = currentFileIndex;
                question.selectedLanguage = languageSelect ? languageSelect.value : question.selectedLanguage;
            }
        }

        function setEditorForCurrentFile() {
            var file = currentFile();
            if (!file) {
                return;
            }
            isSettingEditorValue = true;
            try {
                editor.setValue(file.content || "");
            } finally {
                isSettingEditorValue = false;
            }
            editor.setOption("mode", modeForLanguage(extensionLanguage(file.name, languageSelect.value), languageModes));
            if (currentFileName) {
                currentFileName.textContent = file.name + (file.is_main ? " · " + (i18n.mainFile || "Main File") : "");
            }
            setTimeout(function () {
                editor.refresh();
            }, 20);
        }

        function renderFiles() {
            if (!fileList) {
                return;
            }
            fileList.innerHTML = "";
            files.forEach(function (file, index) {
                var btn = document.createElement("button");
                btn.type = "button";
                btn.className = "coding-file-item" + (index === currentFileIndex ? " is-active" : "");

                var icon = document.createElement("i");
                icon.className = file.is_main ? "fas fa-star" : "far fa-file-code";
                btn.appendChild(icon);

                var label = document.createElement("span");
                label.textContent = file.name;
                btn.appendChild(label);

                if (file.is_main) {
                    var badge = document.createElement("small");
                    badge.textContent = i18n.mainFile || "Main File";
                    btn.appendChild(badge);
                }

                btn.addEventListener("click", function () {
                    syncEditorToFile();
                    currentFileIndex = index;
                    renderFiles();
                    setEditorForCurrentFile();
                    updateLanguagePreviewVisibility();
                });
                fileList.appendChild(btn);
            });
        }

        function fileSnapshot(filesToSnapshot) {
            return JSON.stringify((Array.isArray(filesToSnapshot) ? filesToSnapshot : []).map(function (file) {
                return {
                    name: file.name || "",
                    content: file.content || "",
                    is_main: Boolean(file.is_main)
                };
            }));
        }

        function isQuestionAnswered(question) {
            if (!question) {
                return false;
            }
            var starterSnapshot = fileSnapshot(question.starterFiles);
            var currentSnapshot = fileSnapshot(question.files);
            if (starterSnapshot && starterSnapshot !== currentSnapshot) {
                return true;
            }
            if (!starterSnapshot) {
                return (question.files || []).some(function (file) {
                    return String(file.content || "").trim() !== "";
                });
            }
            return false;
        }

        function questionBodyText(question) {
            var lines = [];
            if (question.problemStatement) {
                lines.push(question.problemStatement);
            }
            if (question.inputDescription) {
                lines.push("Input description:\n" + question.inputDescription);
            }
            if (question.outputDescription) {
                lines.push("Output description:\n" + question.outputDescription);
            }
            if (question.exampleInput) {
                lines.push("Example input:\n" + question.exampleInput);
            }
            if (question.exampleOutput) {
                lines.push("Example output:\n" + question.exampleOutput);
            }
            return lines.join("\n\n");
        }

        function updateProgress() {
            var total = questionStates.length || 1;
            var answered = questionStates.filter(isQuestionAnswered).length;
            if (currentQuestionNumNode) currentQuestionNumNode.textContent = String(currentQuestionIndex + 1);
            if (totalQuestionCountNode) totalQuestionCountNode.textContent = String(total);
            if (answeredCountNode) answeredCountNode.textContent = String(answered);
            if (totalAnswerCountNode) totalAnswerCountNode.textContent = String(total);
            if (progressFillNode) {
                progressFillNode.style.width = total ? Math.round((answered / total) * 100) + "%" : "0%";
            }
        }

        function updateQuestionControls() {
            var isFirst = currentQuestionIndex === 0;
            var isLast = currentQuestionIndex >= questionStates.length - 1;
            if (prevQuestionBtn) {
                prevQuestionBtn.disabled = isFirst;
            }
            if (nextQuestionBtn) {
                nextQuestionBtn.hidden = isLast;
            }
            if (submitBtn) {
                submitBtn.hidden = !isLast;
            }
        }

        function renderProblem() {
            var question = currentQuestion();
            if (currentQuestionTitleNode) {
                currentQuestionTitleNode.textContent = question.title || "";
            }
            if (questionLabelNode) {
                questionLabelNode.textContent = (i18n.questionUpper || "QUESTION") + " " + question.number;
            }
            if (questionTextNode) {
                questionTextNode.textContent = questionBodyText(question) || question.title || "";
            }
            updateProgress();
            updateQuestionControls();
        }

        function renderQuestionNav() {
            if (!questionNav) {
                return;
            }
            questionNav.innerHTML = "";
            questionStates.forEach(function (question, index) {
                var btn = document.createElement("button");
                btn.type = "button";
                btn.className =
                    "coding-question-btn" +
                    (index === currentQuestionIndex ? " is-active" : "") +
                    (isQuestionAnswered(question) ? " is-answered" : "");
                btn.textContent = String(question.number);
                btn.title = question.title || btn.textContent;
                btn.addEventListener("click", function () {
                    switchQuestion(index);
                });
                questionNav.appendChild(btn);
            });
            questionNav.hidden = false;
        }

        function getSelectedLanguage() {
            return languageSelect ? languageSelect.value : currentQuestion().selectedLanguage;
        }

        function getActiveFileLanguage() {
            var active = currentFile();
            return active ? extensionLanguage(active.name, getSelectedLanguage()) : getSelectedLanguage();
        }

        function hasHtmlFile() {
            return files.some(function (file) {
                return String(file.name || "").toLowerCase().match(/\.html?$/);
            });
        }

        function canPreviewCurrentQuestion() {
            var selected = getSelectedLanguage();
            var activeLanguage = getActiveFileLanguage();
            return selected === "html" || selected === "javascript" || activeLanguage === "html" || hasHtmlFile();
        }

        function shouldExecuteCurrentJavaScriptOnly() {
            if (hasHtmlFile()) {
                return false;
            }
            var selected = getSelectedLanguage();
            var activeLanguage = getActiveFileLanguage();
            return selected === "javascript" || activeLanguage === "javascript";
        }

        function shouldOpenPreviewAfterRun() {
            return hasHtmlFile() || getSelectedLanguage() === "html" || getActiveFileLanguage() === "html";
        }

        function syncBootstrapSelect(select) {
            if (window.EMSBootstrapSelect && select) {
                window.EMSBootstrapSelect.sync(select);
            }
        }

        function updateLanguagePreviewVisibility() {
            var previewAllowed = canPreviewCurrentQuestion();
            document.querySelectorAll("[data-preview-tab]").forEach(function (tab) {
                tab.hidden = !previewAllowed;
            });
            if (!previewAllowed && document.querySelector('[data-coding-panel="preview"].active')) {
                switchTab("output");
            }
        }

        function switchQuestion(index) {
            if (index === currentQuestionIndex || !questionStates[index]) {
                return;
            }
            if (hasUnsavedChanges) {
                autosave();
            }
            syncEditorToFile();
            currentQuestionIndex = index;
            var question = currentQuestion();
            files = question.files;
            currentFileIndex = Math.min(question.fileIndex || 0, Math.max(files.length - 1, 0));
            if (languageSelect) {
                languageSelect.value = question.selectedLanguage || question.language || config.selectedLanguage;
                syncBootstrapSelect(languageSelect);
            }
            renderQuestionNav();
            renderProblem();
            renderFiles();
            setEditorForCurrentFile();
            if (outputNode) outputNode.textContent = "";
            if (errorsNode) errorsNode.textContent = "";
            if (previewConsoleNode) previewConsoleNode.textContent = "";
            if (previewFrame) {
                previewFrame.removeAttribute("src");
                previewFrame.removeAttribute("srcdoc");
            }
            updateLanguagePreviewVisibility();
        }

        function collectPayload() {
            syncEditorToFile();
            return {
                question_id: currentQuestion().id,
                selected_language: languageSelect ? languageSelect.value : currentQuestion().selectedLanguage,
                files: files,
                stdin: stdinNode ? stdinNode.value : ""
            };
        }

        function collectSubmitPayload() {
            syncEditorToFile();
            return {
                questions: questionStates.map(function (question) {
                    return {
                        question_id: question.id,
                        selected_language: question.selectedLanguage || question.language || config.selectedLanguage,
                        files: question.files || [],
                        stdin: ""
                    };
                })
            };
        }

        function queueAutosave(delay) {
            hasUnsavedChanges = true;
            clearTimeout(autosaveTimer);
            autosaveTimer = setTimeout(function () {
                autosave();
            }, delay || 2500);
        }

        function requestJson(url, payload) {
            return fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": config.csrfToken || "",
                    "X-Requested-With": "XMLHttpRequest"
                },
                body: JSON.stringify(payload || {})
            }).then(function (response) {
                return response.json().then(function (body) {
                    if (!response.ok) {
                        var error = new Error(body.error || "Request failed");
                        error.payload = body;
                        throw error;
                    }
                    return body;
                });
            });
        }

        function autosave() {
            if (!hasUnsavedChanges || isSubmitting) {
                return Promise.resolve();
            }
            setStatus(i18n.saving || "Saving...");
            return requestJson(config.autosaveUrl, collectPayload())
                .then(function (body) {
                    hasUnsavedChanges = false;
                    if (body.finished && body.redirect_url) {
                        window.location.href = body.redirect_url;
                        return;
                    }
                    currentQuestion().latestSubmission = body.submission || currentQuestion().latestSubmission;
                    setStatus(i18n.autoSaved || "Auto-saved");
                })
                .catch(function (error) {
                    if (error.payload && error.payload.redirect_url) {
                        window.location.href = error.payload.redirect_url;
                        return;
                    }
                    setStatus(error.message || "Save failed");
                });
        }

        function switchTab(tabName) {
            document.querySelectorAll("[data-coding-tab]").forEach(function (tab) {
                tab.classList.toggle("active", tab.getAttribute("data-coding-tab") === tabName);
            });
            document.querySelectorAll("[data-coding-panel]").forEach(function (panel) {
                panel.classList.toggle("active", panel.getAttribute("data-coding-panel") === tabName);
            });
        }

        function bootstrapModal(node) {
            if (!node || !window.bootstrap || !window.bootstrap.Modal) {
                return null;
            }
            return window.bootstrap.Modal.getOrCreateInstance(node);
        }

        function hideBootstrapModal(node) {
            var modal = bootstrapModal(node);
            if (modal) {
                modal.hide();
            }
        }

        var pendingConfirmAction = null;
        function openConfirmModal(options) {
            options = options || {};
            if (!confirmModalNode || !confirmModalConfirm || !bootstrapModal(confirmModalNode)) {
                if (window.confirm(options.body || options.title || "")) {
                    if (options.onConfirm) options.onConfirm();
                }
                return;
            }
            pendingConfirmAction = options.onConfirm || null;
            if (confirmModalTitle) confirmModalTitle.textContent = options.title || "";
            if (confirmModalBody) confirmModalBody.textContent = options.body || "";
            confirmModalConfirm.textContent = options.confirmText || i18n.confirm || "Confirm";
            confirmModalConfirm.classList.toggle("btn-danger", options.danger !== false);
            confirmModalConfirm.classList.toggle("btn-primary", options.danger === false);
            bootstrapModal(confirmModalNode).show();
        }

        var pendingFileNameAction = null;
        var pendingFileNameAllowedIndex = -1;
        function openFileNameModal(options) {
            options = options || {};
            if (!fileNameModalNode || !fileNameInput || !fileNameForm || !bootstrapModal(fileNameModalNode)) {
                var fallbackName = safeFileName(window.prompt(options.title || i18n.fileNamePrompt || "File name", options.initialValue || ""));
                if (fallbackName && options.onConfirm) {
                    options.onConfirm(fallbackName);
                }
                return;
            }
            pendingFileNameAction = options.onConfirm || null;
            pendingFileNameAllowedIndex = Number.isInteger(options.allowedIndex) ? options.allowedIndex : -1;
            if (fileNameModalTitle) fileNameModalTitle.textContent = options.title || i18n.fileNamePrompt || "File name";
            if (fileNameModalConfirm) fileNameModalConfirm.textContent = options.confirmText || i18n.save || "Save";
            if (fileNameError) fileNameError.textContent = "";
            fileNameInput.value = options.initialValue || "";
            bootstrapModal(fileNameModalNode).show();
            window.setTimeout(function () {
                fileNameInput.focus();
                fileNameInput.select();
            }, 150);
        }

        function appendConsoleLine(kind, message) {
            var prefix = kind === "warn" ? "[warn] " : kind === "error" ? "[error] " : "";
            var line = prefix + (message || "");
            browserRunHasOutput = true;
            if (outputNode) {
                outputNode.textContent += (outputNode.textContent ? "\n" : "") + line;
            }
            if (previewConsoleNode) {
                previewConsoleNode.textContent += (previewConsoleNode.textContent ? "\n" : "") + line;
            }
            if (kind === "error" && errorsNode) {
                errorsNode.textContent += (errorsNode.textContent ? "\n" : "") + line;
            }
        }

        function applyPreviewNonce(element) {
            if (previewNonce) {
                element.setAttribute("nonce", previewNonce);
            }
            return element;
        }

        function consoleBridgeSource(runId) {
            return [
                "(function(){",
                "var runId=" + JSON.stringify(runId) + ";",
                "function format(value){",
                " if(typeof value==='string') return value;",
                " try{return JSON.stringify(value);}catch(error){return String(value);}",
                "}",
                "function send(kind,args){",
                " try{parent.postMessage({__codingPreviewConsole:true,runId:runId,kind:kind,message:Array.prototype.slice.call(args).map(format).join(' ')},'*');}catch(error){}",
                "}",
                "['log','info','warn','error'].forEach(function(kind){",
                " var original=console[kind];",
                " console[kind]=function(){send(kind,arguments); if(original){original.apply(console,arguments);}};",
                "});",
                "window.addEventListener('error',function(event){send('error',[event.message || 'Script error']);});",
                "window.addEventListener('unhandledrejection',function(event){send('error',[event.reason || 'Unhandled promise rejection']);});",
                "})();"
            ].join("");
        }

        function buildPreviewDocument(runId, options) {
            options = options || {};
            syncEditorToFile();
            var htmlFile = files.find(function (file) {
                return String(file.name).toLowerCase().match(/\.html?$/);
            });
            var baseHtml = htmlFile
                ? htmlFile.content || ""
                : "<!doctype html><html><head><title>Preview</title></head><body></body></html>";
            var parser = new DOMParser();
            var doc = parser.parseFromString(baseHtml, "text/html");

            if (!doc.head) {
                doc.documentElement.insertBefore(doc.createElement("head"), doc.body || null);
            }
            if (!doc.body) {
                doc.documentElement.appendChild(doc.createElement("body"));
            }

            var cssFiles = {};
            var jsFiles = {};
            files.forEach(function (file) {
                var name = assetName(file.name).toLowerCase();
                if (name.endsWith(".css")) cssFiles[name] = file;
                if (name.endsWith(".js")) jsFiles[name] = file;
            });

            Array.prototype.slice.call(doc.querySelectorAll('link[rel~="stylesheet"][href]')).forEach(function (link) {
                var file = cssFiles[assetName(link.getAttribute("href")).toLowerCase()];
                if (!file) return;
                var style = applyPreviewNonce(doc.createElement("style"));
                style.setAttribute("data-file", file.name);
                style.textContent = file.content || "";
                link.parentNode.replaceChild(style, link);
            });

            Array.prototype.slice.call(doc.querySelectorAll("style")).forEach(function (style) {
                applyPreviewNonce(style);
            });

            Array.prototype.slice.call(doc.querySelectorAll("script[src]")).forEach(function (script) {
                var file = jsFiles[assetName(script.getAttribute("src")).toLowerCase()];
                if (!file) return;
                var replacement = applyPreviewNonce(doc.createElement("script"));
                replacement.setAttribute("data-file", file.name);
                replacement.textContent = escapeScriptText(file.content || "");
                script.parentNode.replaceChild(replacement, script);
            });

            Array.prototype.slice.call(doc.querySelectorAll("script:not([src])")).forEach(function (script) {
                applyPreviewNonce(script);
            });

            var bridge = applyPreviewNonce(doc.createElement("script"));
            bridge.textContent = consoleBridgeSource(runId);
            doc.head.insertBefore(bridge, doc.head.firstChild);

            if (options.executeCurrentJavaScriptOnly) {
                var active = currentFile();
                var main = files.find(function (file) { return file.is_main && String(file.name).toLowerCase().endsWith(".js"); });
                var jsFile = String(active && active.name).toLowerCase().endsWith(".js") ? active : main;
                if (jsFile) {
                    var runScript = applyPreviewNonce(doc.createElement("script"));
                    runScript.setAttribute("data-file", jsFile.name);
                    runScript.textContent = escapeScriptText(jsFile.content || "");
                    doc.body.appendChild(runScript);
                }
            }

            return "<!doctype html>\n" + doc.documentElement.outerHTML;
        }

        function renderPreview(options) {
            if (!previewFrame) {
                return;
            }
            options = options || {};
            var runId = options.runId || ++previewRunId;
            previewFrame.removeAttribute("src");
            previewFrame.removeAttribute("srcdoc");
            window.requestAnimationFrame(function () {
                previewFrame.srcdoc = buildPreviewDocument(runId, options);
            });
        }

        window.addEventListener("message", function (event) {
            if (!previewFrame || event.source !== previewFrame.contentWindow) {
                return;
            }
            var data = event.data || {};
            if (!data.__codingPreviewConsole || data.runId !== previewRunId) {
                return;
            }
            appendConsoleLine(data.kind, data.message);
        });

        function applyRunResult(submission) {
            var outputText = submission.output || "";
            if (!outputText && submission.error) {
                outputText = submission.error;
            }
            if (outputNode) outputNode.textContent = outputText;
            if (errorsNode) errorsNode.textContent = submission.error || "";
            if (previewConsoleNode) previewConsoleNode.textContent = submission.output || "";
            currentQuestion().latestSubmission = submission;
            updateProgress();
            renderQuestionNav();
            switchTab(submission.error && !submission.output ? "errors" : "output");
        }

        function shouldRunInBrowser() {
            return canPreviewCurrentQuestion();
        }

        function runBrowserCode() {
            clearTimeout(autosaveTimer);
            browserRunHasOutput = false;
            previewRunId += 1;
            if (outputNode) outputNode.textContent = "";
            if (errorsNode) errorsNode.textContent = "";
            if (previewConsoleNode) previewConsoleNode.textContent = "";
            setStatus(i18n.running || "Running...");
            runBtn.disabled = true;

            var openPreview = shouldOpenPreviewAfterRun();
            switchTab(openPreview ? "preview" : "output");
            renderPreview({
                runId: previewRunId,
                executeCurrentJavaScriptOnly: shouldExecuteCurrentJavaScriptOnly()
            });

            return autosave()
                .then(function () {
                    setStatus(i18n.previewUpdated || "Preview updated.");
                })
                .finally(function () {
                    runBtn.disabled = false;
                });
        }

        function runCode() {
            if (shouldRunInBrowser()) {
                runBrowserCode();
                return;
            }

            clearTimeout(autosaveTimer);
            setStatus(i18n.running || "Running...");
            runBtn.disabled = true;

            requestJson(config.runUrl, collectPayload())
                .then(function (body) {
                    hasUnsavedChanges = false;
                    if (body.finished && body.redirect_url) {
                        window.location.href = body.redirect_url;
                        return;
                    }
                    applyRunResult(body.submission || {});
                    setStatus(i18n.autoSaved || "Auto-saved");
                })
                .catch(function (error) {
                    if (error.payload && error.payload.redirect_url) {
                        window.location.href = error.payload.redirect_url;
                        return;
                    }
                    if (outputNode) outputNode.textContent = error.message || "Run failed";
                    if (errorsNode) errorsNode.textContent = error.message || "Run failed";
                    switchTab("errors");
                    setStatus(error.message || "Run failed");
                })
                .finally(function () {
                    runBtn.disabled = false;
                });
        }

        function submitCode() {
            if (isSubmitting) {
                return;
            }
            isSubmitting = true;
            clearTimeout(autosaveTimer);
            syncEditorToFile();
            setStatus(i18n.submitting || "Submitting...");
            submitBtn.disabled = true;
            runBtn.disabled = true;
            requestJson(config.submitUrl, collectSubmitPayload())
                .then(function (body) {
                    hasUnsavedChanges = false;
                    setStatus(i18n.submitSuccess || "Submission successful");
                    if (body.redirect_url) {
                        window.location.href = body.redirect_url;
                    }
                })
                .catch(function (error) {
                    if (error.payload && error.payload.redirect_url) {
                        window.location.href = error.payload.redirect_url;
                        return;
                    }
                    isSubmitting = false;
                    submitBtn.disabled = false;
                    runBtn.disabled = false;
                    if (errorsNode) errorsNode.textContent = error.message || "Submit failed";
                    switchTab("errors");
                    setStatus(error.message || "Submit failed");
                });
        }

        editor.on("change", function () {
            if (isSettingEditorValue) {
                return;
            }
            syncEditorToFile();
            updateProgress();
            renderQuestionNav();
            queueAutosave(2500);
        });

        if (languageSelect) {
            languageSelect.addEventListener("change", function () {
                var question = currentQuestion();
                question.selectedLanguage = languageSelect.value;
                editor.setOption("mode", modeForLanguage(extensionLanguage(currentFile() && currentFile().name, languageSelect.value), languageModes));
                updateLanguagePreviewVisibility();
                updateProgress();
                renderQuestionNav();
                queueAutosave(500);
            });
        }

        document.querySelectorAll("[data-coding-tab]").forEach(function (tab) {
            tab.addEventListener("click", function () {
                switchTab(tab.getAttribute("data-coding-tab"));
                if (tab.getAttribute("data-coding-tab") === "preview") {
                    browserRunHasOutput = false;
                    previewRunId += 1;
                    if (previewConsoleNode) previewConsoleNode.textContent = "";
                    renderPreview({
                        runId: previewRunId,
                        executeCurrentJavaScriptOnly: shouldExecuteCurrentJavaScriptOnly()
                    });
                }
            });
        });

        if (confirmModalConfirm) {
            confirmModalConfirm.addEventListener("click", function () {
                var action = pendingConfirmAction;
                pendingConfirmAction = null;
                hideBootstrapModal(confirmModalNode);
                if (action) {
                    action();
                }
            });
        }

        if (fileNameForm) {
            fileNameForm.addEventListener("submit", function (event) {
                event.preventDefault();
                var name = safeFileName(fileNameInput ? fileNameInput.value : "");
                if (!name) {
                    if (fileNameError) fileNameError.textContent = i18n.invalidFileName || "Invalid file name.";
                    return;
                }
                if (files.some(function (file, index) {
                    return file.name === name && index !== pendingFileNameAllowedIndex;
                })) {
                    if (fileNameError) fileNameError.textContent = i18n.duplicateFileName || "Duplicate file name.";
                    return;
                }
                var action = pendingFileNameAction;
                pendingFileNameAction = null;
                pendingFileNameAllowedIndex = -1;
                hideBootstrapModal(fileNameModalNode);
                if (action) {
                    action(name);
                }
            });
        }

        if (runBtn) {
            runBtn.addEventListener("click", runCode);
        }
        if (submitBtn) {
            submitBtn.addEventListener("click", submitCode);
        }
        if (prevQuestionBtn) {
            prevQuestionBtn.addEventListener("click", function () {
                switchQuestion(currentQuestionIndex - 1);
            });
        }
        if (nextQuestionBtn) {
            nextQuestionBtn.addEventListener("click", function () {
                switchQuestion(currentQuestionIndex + 1);
            });
        }
        if (resetBtn) {
            resetBtn.addEventListener("click", function () {
                openConfirmModal({
                    title: i18n.resetConfirmTitle || "Reset code?",
                    body: i18n.resetConfirmBody || "This will restore the starter code.",
                    confirmText: i18n.confirm || "Confirm",
                    danger: true,
                    onConfirm: function () {
                        var question = currentQuestion();
                        question.files = cloneFiles(question.starterFiles);
                        files = question.files;
                        currentFileIndex = 0;
                        question.fileIndex = 0;
                        renderFiles();
                        setEditorForCurrentFile();
                        updateLanguagePreviewVisibility();
                        updateProgress();
                        renderQuestionNav();
                        queueAutosave(100);
                    }
                });
            });
        }
        if (createFileBtn) {
            createFileBtn.addEventListener("click", function () {
                openFileNameModal({
                    title: i18n.createFile || "Create File",
                    initialValue: "new_file.txt",
                    confirmText: i18n.save || "Save",
                    onConfirm: function (name) {
                        if (files.some(function (file) { return file.name === name; })) {
                            return;
                        }
                        syncEditorToFile();
                        files.push({ name: name, content: "", language: extensionLanguage(name, languageSelect.value), is_main: false });
                        currentFileIndex = files.length - 1;
                        renderFiles();
                        setEditorForCurrentFile();
                        updateLanguagePreviewVisibility();
                        updateProgress();
                        renderQuestionNav();
                        queueAutosave(100);
                    }
                });
            });
        }
        if (renameFileBtn) {
            renameFileBtn.addEventListener("click", function () {
                var file = currentFile();
                if (!file) return;
                openFileNameModal({
                    title: i18n.renameFile || "Rename File",
                    initialValue: file.name,
                    confirmText: i18n.save || "Save",
                    allowedIndex: currentFileIndex,
                    onConfirm: function (name) {
                        if (files.some(function (item, index) { return index !== currentFileIndex && item.name === name; })) {
                            return;
                        }
                        file.name = name;
                        file.language = extensionLanguage(name, languageSelect.value);
                        renderFiles();
                        setEditorForCurrentFile();
                        updateLanguagePreviewVisibility();
                        updateProgress();
                        renderQuestionNav();
                        queueAutosave(100);
                    }
                });
            });
        }
        if (deleteFileBtn) {
            deleteFileBtn.addEventListener("click", function () {
                if (files.length <= 1) {
                    return;
                }
                var file = currentFile();
                openConfirmModal({
                    title: i18n.deleteConfirmTitle || "Delete file?",
                    body: (i18n.deleteConfirmBody || "This file will be removed.") + (file ? " (" + file.name + ")" : ""),
                    confirmText: i18n.confirm || "Confirm",
                    danger: true,
                    onConfirm: function () {
                        var wasMain = currentFile() && currentFile().is_main;
                        files.splice(currentFileIndex, 1);
                        currentFileIndex = Math.max(0, currentFileIndex - 1);
                        if (wasMain && files[0]) {
                            files[0].is_main = true;
                        }
                        renderFiles();
                        setEditorForCurrentFile();
                        updateLanguagePreviewVisibility();
                        updateProgress();
                        renderQuestionNav();
                        queueAutosave(100);
                    }
                });
            });
        }
        if (fullscreenBtn) {
            fullscreenBtn.addEventListener("click", function () {
                workspace.classList.toggle("is-fullscreen");
                setTimeout(function () {
                    editor.refresh();
                }, 30);
            });
        }
        if (themeToggle) {
            themeToggle.addEventListener("click", function () {
                isDark = !isDark;
                editor.setOption("theme", isDark ? "monokai" : "eclipse");
                if (shell) {
                    shell.classList.toggle("is-light-editor", !isDark);
                }
            });
        }
        if (fontSizeSelect) {
            fontSizeSelect.addEventListener("change", function () {
                var wrapper = editor.getWrapperElement();
                wrapper.style.fontSize = fontSizeSelect.value + "px";
                editor.refresh();
            });
        }

        window.addEventListener("beforeunload", function (event) {
            if (!hasUnsavedChanges || isSubmitting) {
                return;
            }
            event.preventDefault();
            event.returnValue = "";
        });

        if (timerValue && config.remainingSeconds !== null && config.remainingSeconds !== undefined) {
            var remaining = parseInt(config.remainingSeconds, 10) || 0;
            var timerId = window.setInterval(function () {
                timerValue.textContent = formatTime(remaining);
                if (timerNode) {
                    timerNode.classList.toggle("is-danger", remaining > 0 && remaining <= 60);
                }
                if (remaining <= 0) {
                    window.clearInterval(timerId);
                    setStatus(i18n.timeOver || "Time is over");
                    submitCode();
                    return;
                }
                remaining -= 1;
            }, 1000);
        }

        if (languageSelect) {
            languageSelect.value = currentQuestion().selectedLanguage || currentQuestion().language || config.selectedLanguage;
            syncBootstrapSelect(languageSelect);
        }
        renderQuestionNav();
        renderProblem();
        renderFiles();
        setEditorForCurrentFile();
        updateLanguagePreviewVisibility();
    });
})();
