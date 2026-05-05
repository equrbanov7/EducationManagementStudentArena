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

    document.addEventListener("DOMContentLoaded", function () {
        var config = window.CODING_EXAM_CONFIG || {};
        var i18n = config.i18n || {};
        var files = readJsonScript("coding-initial-files", []);
        var visibleTests = readJsonScript("coding-visible-test-cases", []);
        var languageModes = readJsonScript("coding-language-modes", {});
        var currentIndex = 0;
        var autosaveTimer = null;
        var hasUnsavedChanges = false;
        var isSubmitting = false;
        var isDark = true;

        var shell = document.getElementById("codingExamShell");
        var workspace = document.getElementById("codingWorkspace");
        var editorTextArea = document.getElementById("codingEditor");
        var fileList = document.getElementById("codingFileList");
        var currentFileName = document.getElementById("codingCurrentFileName");
        var statusNode = document.getElementById("codingStatus");
        var outputNode = document.getElementById("codingOutput");
        var errorsNode = document.getElementById("codingErrors");
        var submissionNode = document.getElementById("codingSubmissionResult");
        var testCasesNode = document.getElementById("codingTestCases");
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

        if (!editorTextArea || typeof CodeMirror === "undefined") {
            return;
        }

        if (!files.length) {
            files = [{ name: "main.txt", content: "", language: "text", is_main: true }];
        }

        var editor = CodeMirror.fromTextArea(editorTextArea, {
            lineNumbers: true,
            indentUnit: 4,
            tabSize: 4,
            indentWithTabs: false,
            matchBrackets: true,
            autoCloseBrackets: true,
            theme: "monokai",
            mode: modeForLanguage(config.selectedLanguage || "python", languageModes),
            viewportMargin: Infinity
        });

        function setStatus(message) {
            if (statusNode) {
                statusNode.textContent = message || "";
            }
        }

        function currentFile() {
            return files[currentIndex] || files[0];
        }

        function syncEditorToFile() {
            var file = currentFile();
            if (file) {
                file.content = editor.getValue();
            }
        }

        function setEditorForCurrentFile() {
            var file = currentFile();
            if (!file) {
                return;
            }
            editor.setValue(file.content || "");
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
                btn.className = "coding-file-item" + (index === currentIndex ? " is-active" : "");

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
                    currentIndex = index;
                    renderFiles();
                    setEditorForCurrentFile();
                });
                fileList.appendChild(btn);
            });
        }

        function collectPayload() {
            syncEditorToFile();
            return {
                selected_language: languageSelect ? languageSelect.value : config.selectedLanguage,
                files: files,
                stdin: stdinNode ? stdinNode.value : ""
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

        function renderPreview() {
            if (!previewFrame) {
                return;
            }
            syncEditorToFile();
            var htmlFile = files.find(function (file) {
                return String(file.name).toLowerCase().match(/\.html?$/);
            }) || currentFile();
            var css = files
                .filter(function (file) {
                    return String(file.name).toLowerCase().endsWith(".css");
                })
                .map(function (file) {
                    return file.content || "";
                })
                .join("\n");
            var js = files
                .filter(function (file) {
                    return String(file.name).toLowerCase().endsWith(".js");
                })
                .map(function (file) {
                    return file.content || "";
                })
                .join("\n");
            previewFrame.srcdoc = (htmlFile ? htmlFile.content : "") + "\n<style>" + css + "</style>\n<script>" + js + "<\/script>";
        }

        function renderTestCases(results) {
            if (!testCasesNode) {
                return;
            }
            var rows = results && results.length ? results : visibleTests.map(function (item) {
                return {
                    input: item.input,
                    expected: item.expected,
                    points: item.points,
                    passed: null,
                    actual: ""
                };
            });
            testCasesNode.innerHTML = "";
            rows.forEach(function (item, index) {
                var card = document.createElement("article");
                var stateClass = item.passed === true ? " is-passed" : item.passed === false ? " is-failed" : "";
                card.className = "coding-test-case" + stateClass;

                var title = document.createElement("strong");
                title.textContent =
                    "Case " +
                    (index + 1) +
                    " · " +
                    (item.passed === true ? i18n.passed || "Passed" : item.passed === false ? i18n.failed || "Failed" : item.points + " pts");
                card.appendChild(title);

                if (item.input !== undefined) {
                    var input = document.createElement("pre");
                    input.textContent = "Input:\n" + (item.input || "");
                    card.appendChild(input);
                }
                if (item.expected !== undefined) {
                    var expected = document.createElement("pre");
                    expected.textContent = "Expected:\n" + (item.expected || "");
                    card.appendChild(expected);
                }
                if (item.actual) {
                    var actual = document.createElement("pre");
                    actual.textContent = "Actual:\n" + item.actual;
                    card.appendChild(actual);
                }
                if (item.error) {
                    var error = document.createElement("pre");
                    error.textContent = item.error;
                    card.appendChild(error);
                }
                testCasesNode.appendChild(card);
            });
        }

        function renderSubmission(submission) {
            if (!submissionNode || !submission) {
                return;
            }
            submissionNode.innerHTML = "";
            var heading = document.createElement("h3");
            heading.textContent = submission.status || "";
            submissionNode.appendChild(heading);
            if (submission.score !== null && submission.score !== undefined) {
                var score = document.createElement("p");
                score.textContent = "Score: " + submission.score;
                submissionNode.appendChild(score);
            }
            if (submission.execution_time_ms) {
                var timing = document.createElement("p");
                timing.textContent = "Execution time: " + submission.execution_time_ms + "ms";
                submissionNode.appendChild(timing);
            }
        }

        function applyRunResult(submission) {
            outputNode.textContent = submission.output || "";
            errorsNode.textContent = submission.error || "";
            renderTestCases(submission.test_results || []);
            renderSubmission(submission);
            switchTab(submission.error ? "errors" : "output");
        }

        function runCode() {
            clearTimeout(autosaveTimer);
            setStatus(i18n.running || "Running...");
            runBtn.disabled = true;

            if (languageSelect && languageSelect.value === "html") {
                renderPreview();
                outputNode.textContent = "Preview updated.";
                errorsNode.textContent = "";
                switchTab("preview");
            }

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
                    errorsNode.textContent = error.message || "Run failed";
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
            setStatus(i18n.submitting || "Submitting...");
            submitBtn.disabled = true;
            runBtn.disabled = true;
            requestJson(config.submitUrl, collectPayload())
                .then(function (body) {
                    hasUnsavedChanges = false;
                    renderSubmission(body.submission || {});
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
                    errorsNode.textContent = error.message || "Submit failed";
                    switchTab("errors");
                    setStatus(error.message || "Submit failed");
                });
        }

        editor.on("change", function () {
            queueAutosave(2500);
        });

        if (languageSelect) {
            languageSelect.addEventListener("change", function () {
                editor.setOption("mode", modeForLanguage(languageSelect.value, languageModes));
                document.querySelectorAll("[data-preview-tab]").forEach(function (tab) {
                    tab.hidden = languageSelect.value !== "html";
                });
                queueAutosave(500);
            });
        }

        document.querySelectorAll("[data-coding-tab]").forEach(function (tab) {
            tab.addEventListener("click", function () {
                switchTab(tab.getAttribute("data-coding-tab"));
                if (tab.getAttribute("data-coding-tab") === "preview") {
                    renderPreview();
                }
            });
        });

        if (runBtn) {
            runBtn.addEventListener("click", runCode);
        }
        if (submitBtn) {
            submitBtn.addEventListener("click", submitCode);
        }
        if (resetBtn) {
            resetBtn.addEventListener("click", function () {
                files = readJsonScript("coding-starter-files", files);
                currentIndex = 0;
                renderFiles();
                setEditorForCurrentFile();
                queueAutosave(100);
            });
        }
        if (createFileBtn) {
            createFileBtn.addEventListener("click", function () {
                if (!config.allowMultipleFiles && files.length >= 1) {
                    return;
                }
                var name = safeFileName(window.prompt(i18n.fileNamePrompt || "File name", "new_file.txt"));
                if (!name || files.some(function (file) { return file.name === name; })) {
                    return;
                }
                syncEditorToFile();
                files.push({ name: name, content: "", language: extensionLanguage(name, languageSelect.value), is_main: false });
                currentIndex = files.length - 1;
                renderFiles();
                setEditorForCurrentFile();
                queueAutosave(100);
            });
        }
        if (renameFileBtn) {
            renameFileBtn.addEventListener("click", function () {
                var file = currentFile();
                if (!file) return;
                var name = safeFileName(window.prompt(i18n.fileNamePrompt || "File name", file.name));
                if (!name || files.some(function (item, index) { return index !== currentIndex && item.name === name; })) {
                    return;
                }
                file.name = name;
                file.language = extensionLanguage(name, languageSelect.value);
                renderFiles();
                setEditorForCurrentFile();
                queueAutosave(100);
            });
        }
        if (deleteFileBtn) {
            deleteFileBtn.addEventListener("click", function () {
                if (files.length <= 1) {
                    return;
                }
                var wasMain = currentFile() && currentFile().is_main;
                files.splice(currentIndex, 1);
                currentIndex = Math.max(0, currentIndex - 1);
                if (wasMain && files[0]) {
                    files[0].is_main = true;
                }
                renderFiles();
                setEditorForCurrentFile();
                queueAutosave(100);
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

        renderFiles();
        setEditorForCurrentFile();
        renderTestCases([]);
        if (languageSelect) {
            languageSelect.dispatchEvent(new Event("change"));
        }
    });
})();
