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

    // Language-specific hint helper name. CodeMirror lookups go through this
    // so that adding a language only requires registering a matching helper.
    function hintHelperFor(language) {
        switch (language) {
            case "python":
                return "python";
            case "javascript":
                return "javascript";
            case "cpp":
                return "cpp";
            case "java":
                return "java";
            case "html":
                return "html";
            case "css":
                return "css";
            default:
                return "anyword";
        }
    }

    // Detect how many stdin reads the current code is likely to perform so we
    // can render a clear hint to the student before they run. This is a static
    // heuristic (regex over the main file), not a perfect parse — see
    // coding_runtime.execute_code for the actual sandboxed execution.
    function detectStdinReadCount(language, mainContent) {
        return detectStdinPrompts(language, mainContent).length;
    }

    // Pull each stdin read from the main file together with its prompt text
    // when one is available. The result feeds the pre-run input dialog so the
    // student sees exactly what each value is for. We intentionally use simple
    // regexes — anything more invasive would need a per-language parser, which
    // is overkill for the heuristic UX we are building here.
    function detectStdinPrompts(language, mainContent) {
        var content = String(mainContent || "");
        if (!content) return [];

        // Strip comments so we don't pick up commented-out reads.
        // Quick and language-agnostic: line and block comments.
        var sanitized = content
            .replace(/\/\*[\s\S]*?\*\//g, " ")
            .replace(/\/\/[^\n]*/g, "")
            .replace(/#[^\n]*/g, function (match) {
                // Keep "#include" headers etc. that are not comments in C++/Java.
                return /^#\s*(include|define|pragma|ifdef|ifndef|endif|else|elif|undef)/.test(match) ? match : "";
            });

        var prompts = [];

        function addPrompt(rawPrompt, fallbackLabel) {
            var prompt = String(rawPrompt || "").trim();
            // Strip surrounding quotes.
            prompt = prompt.replace(/^[\s,]*['"`]/, "").replace(/['"`][\s,]*$/, "");
            prompts.push({
                prompt: prompt,
                label: prompt || fallbackLabel,
                index: prompts.length
            });
        }

        if (language === "python") {
            // input("prompt") and input()
            var pyRe = /\binput\s*\(([^)]*)\)/g;
            var m;
            while ((m = pyRe.exec(sanitized))) {
                addPrompt(m[1], "input()");
            }
            return prompts;
        }

        if (language === "javascript") {
            // prompt("..."), readline(), readlineSync()
            var jsRe = /\b(?:prompt|readline|readlineSync)\s*\(([^)]*)\)/g;
            var m;
            while ((m = jsRe.exec(sanitized))) {
                addPrompt(m[1], "prompt()");
            }
            return prompts;
        }

        if (language === "cpp") {
            // For C++ the prompt isn't an argument; it's almost always a
            // preceding cout << "..." statement. Walk top-to-bottom and pair
            // them up.
            var lastPromptText = "";
            var lineRe = /[^\n]+/g;
            var lines = sanitized.split("\n");
            for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                // Pull literal strings from a cout chain.
                var coutMatch = line.match(/cout\s*<<\s*([\s\S]*?);?$/);
                if (coutMatch) {
                    var strings = coutMatch[1].match(/"([^"\\]|\\.)*"/g);
                    if (strings && strings.length) {
                        lastPromptText = strings.map(function (s) { return s.slice(1, -1); }).join("");
                    }
                }
                // Count one prompt per cin>>x or getline(cin, x).
                var cinTokens = line.match(/\bcin\s*>>\s*\w+/g) || [];
                cinTokens.forEach(function () {
                    addPrompt(lastPromptText, "cin >>");
                    lastPromptText = "";
                });
                var getlineTokens = line.match(/\bgetline\s*\(\s*cin\s*,\s*\w+\s*\)/g) || [];
                getlineTokens.forEach(function () {
                    addPrompt(lastPromptText, "getline(cin, ...)");
                    lastPromptText = "";
                });
            }
            return prompts;
        }

        if (language === "java") {
            var lines = sanitized.split("\n");
            var lastPromptText = "";
            for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                var printMatch = line.match(/(System\.out\.(?:print|println)|printf)\s*\(([\s\S]*?)\)/);
                if (printMatch) {
                    var strings = printMatch[2].match(/"([^"\\]|\\.)*"/g);
                    if (strings && strings.length) {
                        lastPromptText = strings.map(function (s) { return s.slice(1, -1); }).join("");
                    }
                }
                var scannerCalls = line.match(/\b\w+\s*\.\s*(?:nextLine|next|nextInt|nextDouble|nextLong|nextFloat|nextBoolean|hasNext\w*)\s*\(/g) || [];
                scannerCalls.forEach(function () {
                    addPrompt(lastPromptText, "Scanner.next…");
                    lastPromptText = "";
                });
                var readerCalls = line.match(/\.readLine\s*\(/g) || [];
                readerCalls.forEach(function () {
                    addPrompt(lastPromptText, "readLine()");
                    lastPromptText = "";
                });
            }
            return prompts;
        }

        return prompts;
    }

    function countNonEmptyLines(value) {
        return String(value || "")
            .split("\n")
            .map(function (line) {
                return line.trim();
            })
            .filter(Boolean).length;
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
        var makeMainFileBtn = document.getElementById("codingMakeMainFileBtn");
        var renameFileBtn = document.getElementById("codingRenameFileBtn");
        var deleteFileBtn = document.getElementById("codingDeleteFileBtn");
        var fullscreenBtn = document.getElementById("codingFullscreenBtn");
        var toggleFilesBtn = document.getElementById("codingToggleFilesBtn");
        var themeToggle = document.getElementById("codingThemeToggle");
        var fontSizeSelect = document.getElementById("codingFontSize");
        var timerNode = document.getElementById("codingTimer");
        var timerValue = document.getElementById("codingTimerValue");
        var previewFrame = document.getElementById("codingPreviewFrame");
        var previewConsoleNode = document.getElementById("codingPreviewConsole");
        var browserReloadBtn = document.getElementById("codingBrowserReload");
        var browserTabTitleNode = document.querySelector(".coding-browser-tab__title");
        var browserUrlNode = document.getElementById("codingBrowserUrl");
        var currentQuestionNumNode = document.getElementById("codingCurrentQuestionNum");
        var totalQuestionCountNode = document.getElementById("codingTotalQuestionCount");
        var answeredCountNode = document.getElementById("codingAnsweredCount");
        var answeredTotalCountNode = document.getElementById("codingAnsweredTotalCount");
        var sidebarAnsweredCountNode = document.getElementById("codingSidebarAnsweredCount");
        var unansweredCountNode = document.getElementById("codingUnansweredCount");
        var progressFillNode = document.getElementById("codingProgressFill");
        var questionLabelNode = document.getElementById("codingQuestionLabel");
        var questionTextNode = document.getElementById("codingQuestionText");
        var prevQuestionBtn = document.getElementById("codingPrevQuestionBtn");
        var nextQuestionBtn = document.getElementById("codingNextQuestionBtn");
        var questionNavButtons = document.querySelectorAll("[data-coding-question-nav]");
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
        var timeWarning = window.ExamTimeWarning
            ? window.ExamTimeWarning.init({
                storageKey: "coding_exam_" + String(config.examId || "") + "_attempt_" + String(config.attemptId || "") + "_five_minute_warning",
                thresholdSeconds: 300,
                autoCloseMs: 5000
            })
            : null;

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
                latestSubmission: rawQuestion.latest_submission || null,
                stdin: ""
            };
        }

        var questionStates = (Array.isArray(rawQuestions) && rawQuestions.length ? rawQuestions : [buildFallbackQuestion()])
            .map(normalizeQuestion);
        var files = questionStates[0].files;

        var consoleMetaNode = document.getElementById("codingConsoleMeta");
        var consoleClearBtn = document.getElementById("codingConsoleClear");
        var stdinHintNode = document.getElementById("codingStdinHint");

        var editor = CodeMirror.fromTextArea(editorTextArea, {
            lineNumbers: true,
            indentUnit: 4,
            tabSize: 4,
            indentWithTabs: false,
            matchBrackets: true,
            autoCloseBrackets: true,
            theme: "monokai",
            mode: modeForLanguage(questionStates[0].selectedLanguage || "html", languageModes),
            viewportMargin: Infinity,
            styleActiveLine: true,
            // VS Code-style keyboard shortcuts. Defined here (rather than via
            // extraKeys per-call) so the bindings live with the editor and can
            // be reasoned about as a single block.
            extraKeys: {
                "Ctrl-Space": triggerAutocomplete,
                "Cmd-Space": triggerAutocomplete,
                "Ctrl-Enter": function () { runCode(); },
                "Cmd-Enter": function () { runCode(); },
                "Ctrl-S": function () { autosave(); },
                "Cmd-S": function () { autosave(); },
                "Ctrl-/": function (cm) { cm.toggleComment(); },
                "Cmd-/": function (cm) { cm.toggleComment(); },
                "F11": function () {
                    if (workspace) {
                        workspace.classList.toggle("is-fullscreen");
                        setTimeout(function () { editor.refresh(); }, 30);
                    }
                },
                "Esc": function () {
                    if (workspace && workspace.classList.contains("is-fullscreen")) {
                        workspace.classList.remove("is-fullscreen");
                        setTimeout(function () { editor.refresh(); }, 30);
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

        // Trigger autocomplete using the helper appropriate for the current
        // file's language. This indirection keeps add-language work small:
        // register a helper, list it in hintHelperFor, done.
        function triggerAutocomplete(cm) {
            if (!CodeMirror.showHint) {
                return;
            }
            var language = getActiveFileLanguage();
            var helperName = hintHelperFor(language);
            var helper = CodeMirror.helpers && CodeMirror.helpers.hint && CodeMirror.helpers.hint[helperName];
            cm.showHint({
                hint: helper || CodeMirror.hint.anyword,
                completeSingle: false,
                closeOnUnfocus: true
            });
        }

        // Open the hint widget as the user types alpha-numeric identifiers.
        // We skip whitespace and punctuation to avoid noisy popups; cm.state
        // gating prevents recursive triggers while a hint is already open.
        editor.on("inputRead", function (cm, change) {
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
            setTimeout(function () { triggerAutocomplete(cm); }, 50);
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

        function syncStdinToQuestion() {
            var question = currentQuestion();
            if (question && stdinNode) {
                question.stdin = stdinNode.value || "";
            }
            updateStdinHint();
        }

        // Inline coaching for the stdin box. Compares input lines provided by
        // the student with the static count of stdin reads the program looks
        // like it performs. Mirrors what the backend Docker sandbox will see.
        function updateStdinHint() {
            if (!stdinHintNode) {
                return;
            }
            var question = currentQuestion();
            if (!question) {
                stdinHintNode.textContent = "";
                stdinHintNode.className = "coding-console-input-hint";
                return;
            }
            var language = getSelectedLanguage();
            // Use the executable file (not necessarily the question's main
            // file) so the hint reflects what the runner will actually see.
            var execFile = resolveExecutionFile();
            var requiredReads = detectStdinReadCount(language, execFile && execFile.content);
            var providedLines = countNonEmptyLines(stdinNode ? stdinNode.value : "");

            if (requiredReads === 0) {
                stdinHintNode.textContent = "";
                stdinHintNode.className = "coding-console-input-hint";
                return;
            }
            if (providedLines < requiredReads) {
                stdinHintNode.textContent = (i18n.stdinNeeded || "Program expects {count} input value(s).").replace("{count}", String(requiredReads));
                stdinHintNode.className = "coding-console-input-hint coding-console-input-hint--warn";
                return;
            }
            var extra = providedLines - requiredReads;
            if (extra > 0) {
                stdinHintNode.textContent = (i18n.stdinExtra || "{extra} extra input line(s) will be ignored.").replace("{extra}", String(extra));
                stdinHintNode.className = "coding-console-input-hint coding-console-input-hint--muted";
                return;
            }
            stdinHintNode.textContent = (i18n.stdinReady || "Stdin ready ({count} line(s)).").replace("{count}", String(providedLines));
            stdinHintNode.className = "coding-console-input-hint coding-console-input-hint--ok";
        }

        function setConsoleMeta(text) {
            if (consoleMetaNode) {
                consoleMetaNode.textContent = text || "";
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
                    syncLanguageToCurrentFile();
                    renderFiles();
                    setEditorForCurrentFile();
                    updateLanguagePreviewVisibility();
                });
                fileList.appendChild(btn);
            });
            updateFileActionButtons();
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

        function updateQuestionNav() {
            questionNavButtons.forEach(function (button) {
                var index = parseInt(button.getAttribute("data-target-index"), 10) || 0;
                var question = questionStates[index];
                var isCurrent = index === currentQuestionIndex;
                var isAnswered = isQuestionAnswered(question);

                button.classList.toggle("is-current", isCurrent);
                button.classList.toggle("is-answered", isAnswered);
                button.setAttribute("aria-current", isCurrent ? "step" : "false");
            });
        }

        function questionBodyText(question) {
            var lines = [];
            if (question.problemStatement) {
                lines.push(question.problemStatement);
            }
            if (question.inputDescription) {
                lines.push((i18n.inputDescription || "Input description") + ":\n" + question.inputDescription);
            }
            if (question.outputDescription) {
                lines.push((i18n.outputDescription || "Output description") + ":\n" + question.outputDescription);
            }
            if (question.exampleInput) {
                lines.push((i18n.exampleInput || "Example input") + ":\n" + question.exampleInput);
            }
            if (question.exampleOutput) {
                lines.push((i18n.exampleOutput || "Example output") + ":\n" + question.exampleOutput);
            }
            return lines.join("\n\n");
        }

        function updateProgress() {
            var total = questionStates.length || 1;
            var answered = questionStates.filter(isQuestionAnswered).length;
            var unanswered = Math.max(total - answered, 0);
            if (currentQuestionNumNode) currentQuestionNumNode.textContent = String(currentQuestionIndex + 1);
            if (totalQuestionCountNode) totalQuestionCountNode.textContent = String(total);
            if (answeredCountNode) answeredCountNode.textContent = String(answered);
            if (answeredTotalCountNode) answeredTotalCountNode.textContent = String(total);
            if (sidebarAnsweredCountNode) sidebarAnsweredCountNode.textContent = String(answered);
            if (unansweredCountNode) unansweredCountNode.textContent = String(unanswered);
            if (progressFillNode) {
                progressFillNode.style.width = total ? Math.round(((currentQuestionIndex + 1) / total) * 100) + "%" : "0%";
            }
            updateQuestionNav();
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
        }

        function renderProblem() {
            var question = currentQuestion();
            if (questionLabelNode) {
                questionLabelNode.textContent = "Q" + question.number;
            }
            if (questionTextNode) {
                questionTextNode.textContent = questionBodyText(question) || question.title || "";
            }
            updateProgress();
            updateQuestionControls();
        }

        function getSelectedLanguage() {
            return languageSelect ? languageSelect.value : currentQuestion().selectedLanguage;
        }

        function canSelectLanguage(value) {
            if (!languageSelect || !value) {
                return false;
            }
            return Array.prototype.some.call(languageSelect.options, function (option) {
                return option.value === value;
            });
        }

        function executionLanguageForFile(file, fallbackLanguage) {
            var inferred = file ? extensionLanguage(file.name, fallbackLanguage) : fallbackLanguage;
            if (inferred === "css") {
                inferred = "html";
            }
            return canSelectLanguage(inferred) ? inferred : (fallbackLanguage || getSelectedLanguage());
        }

        function syncLanguageToCurrentFile() {
            if (!languageSelect) {
                return getSelectedLanguage();
            }
            var nextLanguage = executionLanguageForFile(currentFile(), languageSelect.value);
            if (nextLanguage && languageSelect.value !== nextLanguage) {
                languageSelect.value = nextLanguage;
                syncBootstrapSelect(languageSelect);
            }
            currentQuestion().selectedLanguage = languageSelect.value;
            return languageSelect.value;
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

        function setMainFile(index) {
            if (!files[index]) {
                return;
            }
            files.forEach(function (file, fileIndex) {
                file.is_main = fileIndex === index;
            });
            currentQuestion().files = files;
        }

        function updateFileActionButtons() {
            var file = currentFile();
            if (makeMainFileBtn) {
                makeMainFileBtn.disabled = !file || Boolean(file.is_main);
            }
            if (renameFileBtn) {
                renameFileBtn.disabled = !file;
            }
            if (deleteFileBtn) {
                deleteFileBtn.disabled = !file || files.length <= 1;
            }
        }

        function setFilesCollapsed(collapsed) {
            var editorPane = document.querySelector(".coding-editor-pane");
            if (!editorPane || !toggleFilesBtn) {
                return;
            }
            var icon = toggleFilesBtn.querySelector("i");
            editorPane.classList.toggle("is-files-collapsed", collapsed);
            toggleFilesBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
            toggleFilesBtn.setAttribute("title", collapsed ? (i18n.showFiles || "Show files") : (i18n.hideFiles || "Hide files"));
            toggleFilesBtn.setAttribute("aria-label", collapsed ? (i18n.showFiles || "Show files") : (i18n.hideFiles || "Hide files"));
            if (icon) {
                icon.className = collapsed ? "fas fa-folder" : "fas fa-folder-open";
            }
            setTimeout(function () {
                editor.refresh();
            }, 230);
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
            syncStdinToQuestion();
            currentQuestionIndex = index;
            var question = currentQuestion();
            files = question.files;
            currentFileIndex = Math.min(question.fileIndex || 0, Math.max(files.length - 1, 0));
            if (languageSelect) {
                languageSelect.value = question.selectedLanguage || question.language || config.selectedLanguage;
                syncBootstrapSelect(languageSelect);
            }
            syncLanguageToCurrentFile();
            renderProblem();
            renderFiles();
            setEditorForCurrentFile();
            if (outputNode) outputNode.innerHTML = "";
            if (errorsNode) errorsNode.textContent = "";
            if (stdinNode) stdinNode.value = question.stdin || "";
            if (previewConsoleNode) previewConsoleNode.textContent = "";
            if (previewFrame) {
                previewFrame.removeAttribute("src");
                previewFrame.removeAttribute("srcdoc");
            }
            updateLanguagePreviewVisibility();
        }

        function collectPayload() {
            syncEditorToFile();
            syncStdinToQuestion();
            var activeFile = currentFile();
            var selectedLanguage = executionLanguageForFile(
                activeFile,
                languageSelect ? languageSelect.value : currentQuestion().selectedLanguage
            );
            if (languageSelect && languageSelect.value !== selectedLanguage) {
                languageSelect.value = selectedLanguage;
                syncBootstrapSelect(languageSelect);
            }
            currentQuestion().selectedLanguage = selectedLanguage;
            return {
                question_id: currentQuestion().id,
                selected_language: selectedLanguage,
                active_file_name: activeFile ? activeFile.name : "",
                files: files,
                stdin: currentQuestion().stdin || ""
            };
        }

        function collectSubmitPayload() {
            syncEditorToFile();
            return {
                questions: questionStates.map(function (question) {
                    var questionFiles = question.files || [];
                    var activeFile = questionFiles[question.fileIndex || 0] || questionFiles[0] || null;
                    var selectedLanguage = executionLanguageForFile(
                        activeFile,
                        question.selectedLanguage || question.language || config.selectedLanguage
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
        }

        function getUnansweredCount() {
            return Math.max(questionStates.length - questionStates.filter(isQuestionAnswered).length, 0);
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
                // Ensure a <pre> child exists so accumulated lines stay in a
                // single mono-spaced block matching the terminal style.
                var pre = outputNode.querySelector(".coding-terminal-history");
                if (!pre) {
                    outputNode.innerHTML = "";
                    pre = document.createElement("pre");
                    pre.className = "coding-terminal-history";
                    outputNode.appendChild(pre);
                }
                pre.textContent += (pre.textContent ? "\n" : "") + line;
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

        function consoleBridgeSource(runId, stdinValues) {
            // Pre-fed values for the in-iframe prompt() override. Stringify
            // here so we embed them as a JS literal in the bridge source.
            var queueLiteral = JSON.stringify(Array.isArray(stdinValues) ? stdinValues : []);
            return [
                "(function(){",
                "var runId=" + JSON.stringify(runId) + ";",
                "var __stdinQueue = " + queueLiteral + ".slice();",
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
                // ---- prompt()/alert()/confirm() virtualization ---------------
                // Previously the iframe fell through to the browser's native
                // dialogs, which re-asked for input the student had already
                // typed into the stdin panel. We intercept those calls here:
                //   - prompt() pops the next value from the pre-fed queue.
                //     If the queue runs out, we still call the native prompt
                //     so the student can answer interactively.
                //   - The prompt label and value are echoed to the console so
                //     the run transcript matches what Node-backed runs look
                //     like ("eded daxil et: 10").
                "var __nativePrompt = window.prompt;",
                "var __nativeAlert = window.alert;",
                "var __nativeConfirm = window.confirm;",
                "window.prompt = function(message, defaultValue){",
                " var label = (message == null ? '' : String(message));",
                " var value;",
                " if(__stdinQueue.length){",
                "  value = __stdinQueue.shift();",
                " } else if(typeof __nativePrompt === 'function'){",
                "  try{ value = __nativePrompt.call(window, label, defaultValue); }catch(e){ value = null; }",
                " } else {",
                "  value = defaultValue == null ? null : String(defaultValue);",
                " }",
                " send('log', [label + (value == null ? '' : String(value))]);",
                " return value;",
                "};",
                "window.alert = function(message){",
                " send('log', ['[alert] ' + (message == null ? '' : String(message))]);",
                " if(typeof __nativeAlert === 'function'){",
                "  try{ __nativeAlert.call(window, message); }catch(e){}",
                " }",
                "};",
                "window.confirm = function(message){",
                " var label = (message == null ? '' : String(message));",
                " var value;",
                " if(__stdinQueue.length){",
                "  var raw = String(__stdinQueue.shift()).trim().toLowerCase();",
                "  value = ['1','y','yes','true','ok'].indexOf(raw) !== -1;",
                " } else if(typeof __nativeConfirm === 'function'){",
                "  try{ value = __nativeConfirm.call(window, label); }catch(e){ value = false; }",
                " } else {",
                "  value = true;",
                " }",
                " send('log', [label + ' -> ' + (value ? 'OK' : 'Cancel')]);",
                " return value;",
                "};",
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

            // Pre-feed any stdin lines the student typed into the inline
            // terminal so the iframe's overridden prompt() returns them in
            // order, instead of re-prompting the user at the top of the page.
            var stdinValues = [];
            var rawStdin = (currentQuestion() && currentQuestion().stdin) || "";
            if (rawStdin) {
                stdinValues = String(rawStdin)
                    .replace(/\r\n/g, "\n")
                    .replace(/\r/g, "\n")
                    .split("\n")
                    .filter(function (line, index, all) {
                        // Strip the trailing empty line that .split() leaves
                        // when the stdin textarea ends with a newline.
                        return !(line === "" && index === all.length - 1);
                    });
            }
            var bridge = applyPreviewNonce(doc.createElement("script"));
            bridge.textContent = consoleBridgeSource(runId, stdinValues);
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

        function updateBrowserChromeForCurrentFile() {
            // Keep the fake browser chrome consistent with what's actually
            // being rendered: show the html filename as the tab title and a
            // plausible "URL" so students can intuit which file produced the
            // preview when they have multiple html files.
            if (!browserTabTitleNode && !browserUrlNode) return;
            var htmlFile = files.find(function (file) {
                return String(file.name || "").toLowerCase().match(/\.html?$/);
            });
            var name = htmlFile ? htmlFile.name : "preview.html";
            if (browserTabTitleNode) {
                browserTabTitleNode.textContent = name;
            }
            if (browserUrlNode) {
                browserUrlNode.textContent = "preview://" + name;
            }
        }

        function renderPreview(options) {
            if (!previewFrame) {
                return;
            }
            options = options || {};
            var runId = options.runId || ++previewRunId;
            updateBrowserChromeForCurrentFile();
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

        function normalizeConsoleText(value) {
            return String(value || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
        }

        // Build a VS Code–style terminal transcript that interleaves stdin
        // values with the program's own output. Output looks like:
        //
        //   eded daxil et: 10        <- prompt + value (joined on same line)
        //   15                        <- print/console.log between prompts
        //   eded daxil et2: 2
        //   30
        //
        // Strategy:
        //   1. If we know the explicit prompts the student answered (via the
        //      inline terminal), walk the output and split it AT EACH known
        //      prompt occurrence. Insert "prompt + value\n" exactly where the
        //      backend printed the prompt, replacing the prompt text itself.
        //   2. Fallback (no prompts known): treat any line that ends without
        //      a newline as a "trailing prompt" and append stdin to it.
        function outputWithInlineInput(output, stdin, fallback, knownPrompts, knownValues) {
            var text = normalizeConsoleText(output);
            var input = normalizeConsoleText(stdin).replace(/\n+$/g, "");
            if (!text) {
                return fallback || "";
            }
            if (!input) {
                return text;
            }

            var inputLines = input.split("\n");
            var prompts = Array.isArray(knownPrompts) ? knownPrompts : [];
            var values = Array.isArray(knownValues) ? knownValues : inputLines;

            // --- Path 1: we know the prompt texts. Splice each one in place.
            if (prompts.length) {
                var rendered = text;
                var stdinIdx = 0;
                for (var i = 0; i < prompts.length; i++) {
                    var promptText = prompts[i] && prompts[i].prompt;
                    var value = i < values.length ? values[i] : "";
                    if (!promptText) continue;

                    var idx = rendered.indexOf(promptText);
                    if (idx === -1) continue;

                    var before = rendered.slice(0, idx);
                    var after = rendered.slice(idx + promptText.length);
                    // The character immediately after the prompt in the raw
                    // backend output is what the program printed next (e.g.
                    // `15\n` for `print(a+b)`). We splice the answer between
                    // the prompt and that next character; if `after` does NOT
                    // already start with a newline, we also add one so the
                    // next print starts on its own line.
                    var needsBreak = after.length && after.charAt(0) !== "\n";
                    rendered = before + promptText + value + (needsBreak ? "\n" : "") + after;
                    stdinIdx = i + 1;
                }

                // Show any leftover stdin lines in a small footer.
                if (stdinIdx < values.length) {
                    rendered += (rendered.endsWith("\n") ? "" : "\n") + "\n[stdin] " + values.slice(stdinIdx).join(" · ");
                }
                return rendered;
            }

            // --- Path 2 fallback: walk segments, splice stdin into trailing
            //     prompt-style lines. Used when the runner emitted output we
            //     have not paired with explicit prompts (e.g. browser preview).
            var endedWithNewline = /\n$/.test(text);
            var raw = text.split("\n");
            var hasTrailingEmpty = raw[raw.length - 1] === "";
            var segments = hasTrailingEmpty ? raw.slice(0, -1) : raw;
            var renderedFallback = [];
            var idx2 = 0;
            for (var s = 0; s < segments.length; s++) {
                var seg = segments[s];
                var isLast = s === segments.length - 1;
                if (isLast && !endedWithNewline && idx2 < inputLines.length) {
                    renderedFallback.push(seg + inputLines[idx2]);
                    idx2 += 1;
                } else {
                    renderedFallback.push(seg);
                }
            }
            if (idx2 < inputLines.length) {
                renderedFallback.push("");
                renderedFallback.push("[stdin] " + inputLines.slice(idx2).join(" · "));
            }
            return renderedFallback.join("\n");
        }

        // Wrapper that always renders the terminal as a single <pre> block
        // inside the output div. Used so plain text replaces any inline
        // <input> elements that the interactive terminal may have left.
        function setTerminalText(node, text) {
            if (!node) return;
            node.innerHTML = "";
            var pre = document.createElement("pre");
            pre.className = "coding-terminal-history";
            pre.textContent = String(text || "");
            node.appendChild(pre);
        }

        function applyRunResult(submission) {
            var outputText = submission.output || "";
            if (!outputText && submission.error) {
                outputText = submission.error;
            }
            if (!outputText && !submission.error) {
                outputText = i18n.noOutput || "Program finished with no output.";
            }
            if (outputNode) {
                var transcript = outputWithInlineInput(
                    outputText,
                    currentQuestion().stdin || "",
                    i18n.noOutput || "Program finished with no output.",
                    lastInteractivePrompts,
                    lastInteractiveValues
                );
                setTerminalText(outputNode, transcript);
            }
            if (errorsNode) {
                errorsNode.textContent = submission.error || "";
            }
            if (previewConsoleNode) {
                previewConsoleNode.textContent = submission.output || "";
            }
            // Render a compact metadata line in the console header so students
            // see exit status, runtime and memory at a glance — matches the
            // "Run finished in X ms" affordance VS Code shows.
            if (typeof submission.execution_time_ms === "number") {
                setConsoleMeta((i18n.runFinished || "Finished in {ms} ms").replace("{ms}", String(submission.execution_time_ms)));
            } else {
                setConsoleMeta("");
            }
            currentQuestion().latestSubmission = submission;
            updateProgress();
            // Auto-switch to the Errors tab whenever the run failed in a way
            // students need to see immediately:
            //   - sandbox_unavailable: the runner couldn't even start the
            //     program (Docker missing in prod, Piston unreachable). The
            //     output panel would otherwise just show "no output" and the
            //     real reason would stay hidden in the Errors panel.
            //   - runtime/compile errors with an error message: surface it.
            //   - timeout: same — students need to see the time-limit message.
            var status = submission.status || "";
            var failureStatuses = ["sandbox_unavailable", "compile_error", "runtime_error", "timeout"];
            var isFailure = failureStatuses.indexOf(status) !== -1;
            var hasErrorOnly = submission.error && !submission.output;
            switchTab(isFailure || hasErrorOnly ? "errors" : "output");
        }

        // Heuristic: code that touches browser globals (document, window,
        // alert, innerHTML, addEventListener, onclick, …) cannot run in the
        // Node sandbox — Node has no DOM. When we spot such usage AND the
        // question already ships an HTML file we can host it in, defer to
        // the iframe-based browser runner instead.
        function jsUsesBrowserGlobals(content) {
            if (!content) return false;
            var probe = String(content);
            // Strip line and block comments so commented-out DOM calls don't
            // count as real usage.
            probe = probe.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/[^\n]*/g, " ");
            return /\b(document|window|alert|confirm|navigator|location|history|localStorage|sessionStorage|getElementById|querySelector|querySelectorAll|innerHTML|innerText|textContent|addEventListener|onclick|onchange|onsubmit|onload|onkeydown|requestAnimationFrame|fetch)\b/.test(probe);
        }

        function activeJsFilesUseBrowserGlobals() {
            var question = currentQuestion();
            if (!question) return false;
            return (question.files || []).some(function (file) {
                var lower = String(file.name || "").toLowerCase();
                if (!lower.endsWith(".js")) return false;
                return jsUsesBrowserGlobals(file.content);
            });
        }

        function shouldRunInBrowser() {
            var selected = getSelectedLanguage();
            var activeLanguage = getActiveFileLanguage();
            if (selected === "html" || activeLanguage === "html" || activeLanguage === "css") {
                return true;
            }
            // JavaScript that uses DOM/browser APIs: only safe to host in the
            // iframe runner, which requires an HTML shell to attach to.
            if (selected === "javascript" || activeLanguage === "javascript") {
                if (hasHtmlFile() && activeJsFilesUseBrowserGlobals()) {
                    return true;
                }
            }
            return false;
        }

        function runBrowserCode() {
            clearTimeout(autosaveTimer);
            syncStdinToQuestion();
            browserRunHasOutput = false;
            previewRunId += 1;

            // Browser-run student code may pop alert()/confirm()/prompt(),
            // which momentarily blurs the parent window or exits fullscreen.
            // Open a short grace window so supervision does not count those
            // browser-native interactions as tab switches or escape attempts.
            if (window.ExamSupervision && typeof window.ExamSupervision.startPreviewGrace === "function") {
                window.ExamSupervision.startPreviewGrace(5000);
            }
            if (outputNode) outputNode.innerHTML = "";
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

        // Guard against double-run while a request is in flight. Previously the
        // Run button could trigger two backend requests (one from autosave +
        // one from runCode) and surface results out of order.
        var isRunInFlight = false;

        // Inline terminal state — when the program needs stdin we render each
        // prompt followed by an editable input directly inside the output
        // panel, so the student types the value next to the prompt text (like
        // a real terminal). This replaces the old modal dialog.
        var inlineTerminalActive = false;
        var inlineTerminalPrompts = [];
        var inlineTerminalValues = [];
        var inlineTerminalIndex = 0;

        // Helper: render the current "history" (already-answered prompts) and
        // the next prompt with an inline input. Always called when prompt
        // index advances so the DOM matches state.
        function renderInlineTerminal() {
            if (!outputNode) return;
            outputNode.innerHTML = "";

            // History block: previously-resolved prompts with the value the
            // student typed, monospace pre to match the rest of the terminal.
            var history = document.createElement("pre");
            history.className = "coding-terminal-history";
            for (var i = 0; i < inlineTerminalIndex; i++) {
                var p = inlineTerminalPrompts[i];
                var v = inlineTerminalValues[i] || "";
                history.appendChild(document.createTextNode((p.prompt || "") + v + "\n"));
            }
            outputNode.appendChild(history);

            // Active prompt line + inline input.
            if (inlineTerminalIndex < inlineTerminalPrompts.length) {
                var line = document.createElement("div");
                line.className = "coding-terminal-line";

                var promptSpan = document.createElement("span");
                promptSpan.className = "coding-terminal-prompt";
                promptSpan.textContent = inlineTerminalPrompts[inlineTerminalIndex].prompt || "";
                line.appendChild(promptSpan);

                var input = document.createElement("input");
                input.type = "text";
                input.className = "coding-terminal-input";
                input.setAttribute("autocomplete", "off");
                input.setAttribute("spellcheck", "false");
                input.setAttribute("autocapitalize", "off");
                input.setAttribute("autocorrect", "off");
                input.setAttribute("aria-label", inlineTerminalPrompts[inlineTerminalIndex].label || "stdin");
                line.appendChild(input);

                outputNode.appendChild(line);

                input.addEventListener("keydown", function (event) {
                    if (event.key !== "Enter") return;
                    event.preventDefault();
                    inlineTerminalValues[inlineTerminalIndex] = input.value;
                    inlineTerminalIndex += 1;
                    if (inlineTerminalIndex < inlineTerminalPrompts.length) {
                        renderInlineTerminal();
                    } else {
                        completeInlineTerminal();
                    }
                });

                // Defer focus so the input is in the DOM and visible.
                window.setTimeout(function () { input.focus(); }, 30);

                // Friendly hint for the very first prompt only.
                if (inlineTerminalIndex === 0) {
                    var hint = document.createElement("div");
                    hint.className = "coding-terminal-hint";
                    hint.textContent = (i18n.inlineTerminalHint || "Type the value here and press Enter.");
                    outputNode.appendChild(hint);
                }
            }
        }

        // Snapshot of prompts/values that backend output will be interleaved
        // against. Captured at the moment the inline terminal completes so
        // applyRunResult can still see them after inlineTerminal* state has
        // been cleared.
        var lastInteractivePrompts = [];
        var lastInteractiveValues = [];

        function completeInlineTerminal() {
            lastInteractivePrompts = inlineTerminalPrompts.slice();
            lastInteractiveValues = inlineTerminalValues.slice();
            inlineTerminalActive = false;
            // Render the full transcript (history) so the student sees what
            // was provided, then submit the assembled stdin to the backend.
            var stdin = inlineTerminalValues.join("\n");
            if (stdinNode) stdinNode.value = stdin;
            syncStdinToQuestion();
            performBackendRun();
        }

        function startInlineTerminal(prompts) {
            inlineTerminalActive = true;
            inlineTerminalPrompts = prompts;
            inlineTerminalValues = [];
            inlineTerminalIndex = 0;
            switchTab("output");
            setStatus(i18n.running || "Running...");
            setConsoleMeta("");
            renderInlineTerminal();
        }

        // The terminal short-circuits when: the student already wrote stdin
        // manually (so respect their choice), or the code doesn't actually
        // read stdin.
        // Returns the file the backend will actually execute. Mirrors the
        // logic the user sees on screen: prefer the file the student
        // currently has open in the editor, so a Python tab with input()
        // triggers the inline terminal even when an HTML index.html is the
        // question's main file. Falls back to a file matching the selected
        // language, then the explicit main file, then the first file.
        function resolveExecutionFile() {
            var question = currentQuestion();
            if (!question) return null;
            var allFiles = question.files || files || [];
            var selectedLang = getSelectedLanguage();
            var active = currentFile();
            if (active && extensionLanguage(active.name, selectedLang) === selectedLang) {
                return active;
            }
            var byLanguage = allFiles.find(function (f) {
                return extensionLanguage(f.name, selectedLang) === selectedLang;
            });
            if (byLanguage) return byLanguage;
            var explicitMain = allFiles.find(function (f) { return f.is_main; });
            return active || explicitMain || allFiles[0] || null;
        }

        // Pure backend run — extracted so we can call it both directly (when
        // no inline terminal is needed) and at the tail of an inline session.
        function performBackendRun() {
            isRunInFlight = true;
            clearTimeout(autosaveTimer);
            syncEditorToFile();
            syncStdinToQuestion();
            // Output node may currently hold the inline transcript — keep it.
            if (errorsNode) errorsNode.textContent = "";
            setStatus(i18n.running || "Running...");
            setConsoleMeta(i18n.runWaiting || "Waiting for runner...");
            if (runBtn) runBtn.disabled = true;

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
                    // Rate-limit / concurrency-limit response from the
                    // throttle service. Surface a clear message + countdown
                    // and offer a single auto-retry once the cooldown ends.
                    // Auto-retry only fires when we got a small retry_after,
                    // so a runaway loop on the student's side can't bypass
                    // the limit.
                    var payload = error.payload || {};
                    var retryAfter = parseInt(payload.retry_after_seconds, 10);
                    if (!isNaN(retryAfter) && retryAfter > 0 && retryAfter <= 5) {
                        var label = error.message || "Run failed";
                        setStatus(label + " (auto-retry in " + retryAfter + "s)");
                        if (errorsNode) errorsNode.textContent = label;
                        switchTab("errors");
                        window.setTimeout(function () {
                            // Re-enable run button BEFORE retrying so the
                            // user can also retry manually if they prefer.
                            isRunInFlight = false;
                            if (runBtn) runBtn.disabled = false;
                            performBackendRun();
                        }, retryAfter * 1000);
                        return;
                    }
                    setTerminalText(outputNode, error.message || "Run failed");
                    if (errorsNode) errorsNode.textContent = error.message || "Run failed";
                    setConsoleMeta("");
                    switchTab("errors");
                    setStatus(error.message || "Run failed");
                })
                .finally(function () {
                    // Only release the in-flight flag here when we did NOT
                    // schedule an auto-retry — the retry branch above clears
                    // it ahead of time so the timeout's performBackendRun
                    // call isn't blocked by `isRunInFlight`.
                    if (isRunInFlight) {
                        isRunInFlight = false;
                        if (runBtn) runBtn.disabled = false;
                    }
                });
        }

        function runCode() {
            if (isRunInFlight || inlineTerminalActive) {
                return;
            }
            // Browser-targeted code (HTML/CSS, or JS that touches the DOM)
            // skips the inline terminal entirely — its prompts cannot be
            // satisfied with the Node-style stdin pipe.
            if (shouldRunInBrowser()) {
                runBrowserCode();
                return;
            }
            // Each Run starts from a clean slate: clear stdin from the last
            // session so the inline terminal can re-prompt instead of silently
            // reusing stale values. Without this the second click on Run reuses
            // the previous answers and skips the interactive prompt loop.
            var execFile = resolveExecutionFile();
            var prompts = detectStdinPrompts(getSelectedLanguage(), execFile && execFile.content);
            if (prompts.length) {
                if (stdinNode) stdinNode.value = "";
                var question = currentQuestion();
                if (question) question.stdin = "";
                lastInteractivePrompts = [];
                lastInteractiveValues = [];
                updateStdinHint();
                startInlineTerminal(prompts);
                return;
            }

            // No interactive prompts — empty the terminal and submit.
            setTerminalText(outputNode, "");
            switchTab("output");
            performBackendRun();
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

        function openFinishConfirmModal() {
            syncEditorToFile();
            updateProgress();
            var unansweredCount = getUnansweredCount();
            var summary = unansweredCount > 0
                ? (i18n.finishUnansweredCount || "Unanswered questions: {count}.").replace("{count}", String(unansweredCount))
                : (i18n.finishAllAnswered || "All questions have been answered.");
            openConfirmModal({
                title: i18n.finishConfirmTitle || "Finish the exam?",
                body: (i18n.finishConfirmBody || "After you finish, you will not be able to return to this exam.") + " " + summary,
                confirmText: i18n.finishConfirmText || i18n.confirm || "Confirm",
                danger: true,
                onConfirm: submitCode
            });
        }

        editor.on("change", function () {
            if (isSettingEditorValue) {
                return;
            }
            syncEditorToFile();
            updateProgress();
            updateStdinHint();
            queueAutosave(2500);
        });

        if (languageSelect) {
            languageSelect.addEventListener("change", function () {
                var question = currentQuestion();
                question.selectedLanguage = languageSelect.value;
                editor.setOption("mode", modeForLanguage(extensionLanguage(currentFile() && currentFile().name, languageSelect.value), languageModes));
                updateLanguagePreviewVisibility();
                updateProgress();
                updateStdinHint();
                queueAutosave(500);
            });
        }

        if (stdinNode) {
            stdinNode.addEventListener("input", syncStdinToQuestion);
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
            submitBtn.addEventListener("click", openFinishConfirmModal);
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
        questionNavButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                var index = parseInt(button.getAttribute("data-target-index"), 10) || 0;
                switchQuestion(index);
            });
        });
        if (resetBtn) {
            // "Reset code" now only clears the run-result side (output, errors,
            // preview, stdin, status pill). It does NOT delete student files
            // or rewind their code — that surprised students who lost their
            // work mid-exam. The Make-Main / Delete-File buttons remain the
            // explicit ways to manage files; this button is for resetting the
            // *run state* between attempts.
            resetBtn.addEventListener("click", function () {
                if (outputNode) outputNode.innerHTML = "";
                if (errorsNode) errorsNode.textContent = "";
                if (previewConsoleNode) previewConsoleNode.textContent = "";
                if (previewFrame) {
                    previewFrame.removeAttribute("src");
                    previewFrame.removeAttribute("srcdoc");
                }
                if (stdinNode) stdinNode.value = "";
                var question = currentQuestion();
                if (question) question.stdin = "";
                inlineTerminalActive = false;
                inlineTerminalPrompts = [];
                inlineTerminalValues = [];
                inlineTerminalIndex = 0;
                lastInteractivePrompts = [];
                lastInteractiveValues = [];
                browserRunHasOutput = false;
                setConsoleMeta("");
                updateStdinHint();
                setStatus(i18n.consoleCleared || "Console cleared.");
                switchTab("output");
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
                        syncLanguageToCurrentFile();
                        renderFiles();
                        setEditorForCurrentFile();
                        updateLanguagePreviewVisibility();
                        updateProgress();
                        queueAutosave(100);
                    }
                });
            });
        }
        if (makeMainFileBtn) {
            makeMainFileBtn.addEventListener("click", function () {
                setMainFile(currentFileIndex);
                renderFiles();
                setEditorForCurrentFile();
                updateProgress();
                queueAutosave(100);
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
                        syncLanguageToCurrentFile();
                        renderFiles();
                        setEditorForCurrentFile();
                        updateLanguagePreviewVisibility();
                        updateProgress();
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
                        syncLanguageToCurrentFile();
                        renderFiles();
                        setEditorForCurrentFile();
                        updateLanguagePreviewVisibility();
                        updateProgress();
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
        if (toggleFilesBtn) {
            toggleFilesBtn.addEventListener("click", function () {
                var editorPane = document.querySelector(".coding-editor-pane");
                setFilesCollapsed(!(editorPane && editorPane.classList.contains("is-files-collapsed")));
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

        if (browserReloadBtn) {
            // The reload button on the fake browser chrome re-renders the
            // preview from the current files (just like hitting refresh in a
            // real browser would). It does NOT call autosave or the run
            // endpoint — it's a local-only re-render so students can iterate
            // on HTML/CSS without burning a server roundtrip.
            browserReloadBtn.addEventListener("click", function () {
                previewRunId += 1;
                if (previewConsoleNode) previewConsoleNode.textContent = "";
                renderPreview({
                    runId: previewRunId,
                    executeCurrentJavaScriptOnly: shouldExecuteCurrentJavaScriptOnly()
                });
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
                if (timeWarning) {
                    timeWarning.maybeShow(remaining);
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
        // Console "Clear" button — wipe output/errors and re-show the empty
        // state placeholder. Doesn't touch stdin or the editor, since those
        // are independent of run output.
        if (consoleClearBtn) {
            consoleClearBtn.addEventListener("click", function () {
                if (outputNode) outputNode.innerHTML = "";
                if (errorsNode) errorsNode.textContent = "";
                if (previewConsoleNode) previewConsoleNode.textContent = "";
                // Reset stdin so a subsequent Run starts from scratch.
                // (runCode also clears stdin before opening the inline
                // terminal, but Clear gives the student an explicit way to
                // wipe everything without triggering a run.)
                if (stdinNode) stdinNode.value = "";
                var question = currentQuestion();
                if (question) question.stdin = "";
                updateStdinHint();
                // Reset any in-flight inline terminal session so the next Run
                // starts from a clean slate.
                inlineTerminalActive = false;
                inlineTerminalPrompts = [];
                inlineTerminalValues = [];
                inlineTerminalIndex = 0;
                lastInteractivePrompts = [];
                lastInteractiveValues = [];
                setConsoleMeta("");
                setStatus(i18n.consoleCleared || "Console cleared.");
            });
        }

        // Show a one-time tip about shortcuts so students discover Ctrl+Enter.
        if (i18n.shortcutHint) {
            setStatus(i18n.shortcutHint);
        }

        syncLanguageToCurrentFile();
        renderProblem();
        renderFiles();
        setEditorForCurrentFile();
        if (stdinNode) {
            stdinNode.value = currentQuestion().stdin || "";
        }
        updateStdinHint();
        updateLanguagePreviewVisibility();
    });
})();
