import { detectStdinPrompts, extensionLanguage, navigateAway } from './utils.js';

export function installRunner(ctx) {
    ctx.normalizeConsoleText = function normalizeConsoleText(value) {
        return String(value || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    };

    // Build a VS Code-style terminal transcript that interleaves stdin
    // values with the program's own output.
    ctx.outputWithInlineInput = function outputWithInlineInput(output, stdin, fallback, knownPrompts, knownValues) {
        var text = ctx.normalizeConsoleText(output);
        var input = ctx.normalizeConsoleText(stdin).replace(/\n+$/g, "");
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
    };

    // Wrapper that always renders the terminal as a single <pre> block
    // inside the output div. Used so plain text replaces any inline
    // <input> elements that the interactive terminal may have left.
    ctx.setTerminalText = function setTerminalText(node, text) {
        if (!node) return;
        node.innerHTML = "";
        var pre = document.createElement("pre");
        pre.className = "coding-terminal-history";
        pre.textContent = String(text || "");
        node.appendChild(pre);
    };

    ctx.applyRunResult = function applyRunResult(submission) {
        var outputText = submission.output || "";
        if (!outputText && submission.error) {
            outputText = submission.error;
        }
        if (!outputText && !submission.error) {
            outputText = ctx.i18n.noOutput || "Program finished with no output.";
        }
        if (ctx.outputNode) {
            var transcript = ctx.outputWithInlineInput(
                outputText,
                ctx.currentQuestion().stdin || "",
                ctx.i18n.noOutput || "Program finished with no output.",
                ctx.lastInteractivePrompts,
                ctx.lastInteractiveValues
            );
            ctx.setTerminalText(ctx.outputNode, transcript);
        }
        if (ctx.errorsNode) {
            ctx.errorsNode.textContent = submission.error || "";
        }
        if (ctx.previewConsoleNode) {
            ctx.previewConsoleNode.textContent = submission.output || "";
        }
        // Render a compact metadata line in the console header so students
        // see exit status, runtime and memory at a glance.
        if (typeof submission.execution_time_ms === "number") {
            ctx.setConsoleMeta((ctx.i18n.runFinished || "Finished in {ms} ms").replace("{ms}", String(submission.execution_time_ms)));
        } else {
            ctx.setConsoleMeta("");
        }
        ctx.currentQuestion().latestSubmission = submission;
        ctx.updateProgress();
        var status = submission.status || "";
        var failureStatuses = ["sandbox_unavailable", "compile_error", "runtime_error", "timeout"];
        var isFailure = failureStatuses.indexOf(status) !== -1;
        var hasErrorOnly = submission.error && !submission.output;
        ctx.switchTab(isFailure || hasErrorOnly ? "errors" : "output");
    };

    ctx.runBrowserCode = function runBrowserCode() {
        clearTimeout(ctx.autosaveTimer);
        ctx.syncStdinToQuestion();
        ctx.browserRunHasOutput = false;
        ctx.previewRunId += 1;

        // Browser-run student code may pop alert()/confirm()/prompt(),
        // which momentarily blurs the parent window or exits fullscreen.
        // Open a short grace window so supervision does not count those
        // browser-native interactions as tab switches or escape attempts.
        if (window.ExamSupervision && typeof window.ExamSupervision.startPreviewGrace === "function") {
            window.ExamSupervision.startPreviewGrace(5000);
        }
        if (ctx.outputNode) ctx.outputNode.innerHTML = "";
        if (ctx.errorsNode) ctx.errorsNode.textContent = "";
        if (ctx.previewConsoleNode) ctx.previewConsoleNode.textContent = "";
        ctx.setStatus(ctx.i18n.running || "Running...");
        ctx.runBtn.disabled = true;

        var openPreview = ctx.shouldOpenPreviewAfterRun();
        ctx.switchTab(openPreview ? "preview" : "output");
        ctx.renderPreview({
            runId: ctx.previewRunId,
            executeCurrentJavaScriptOnly: ctx.shouldExecuteCurrentJavaScriptOnly()
        });

        return ctx.autosave()
            .then(function () {
                ctx.setStatus(ctx.i18n.previewUpdated || "Preview updated.");
            })
            .finally(function () {
                ctx.runBtn.disabled = false;
            });
    };

    // Guard against double-run while a request is in flight. Previously the
    // Run button could trigger two backend requests (one from autosave +
    // one from runCode) and surface results out of order.
    ctx.isRunInFlight = false;

    // Inline terminal state — when the program needs stdin we render each
    // prompt followed by an editable input directly inside the output
    // panel, so the student types the value next to the prompt text (like
    // a real terminal). This replaces the old modal dialog.
    ctx.inlineTerminalActive = false;
    ctx.inlineTerminalPrompts = [];
    ctx.inlineTerminalValues = [];
    ctx.inlineTerminalIndex = 0;
    ctx.lastInteractivePrompts = [];
    ctx.lastInteractiveValues = [];

    // Helper: render the current "history" (already-answered prompts) and
    // the next prompt with an inline input. Always called when prompt
    // index advances so the DOM matches state.
    ctx.renderInlineTerminal = function renderInlineTerminal() {
        if (!ctx.outputNode) return;
        ctx.outputNode.innerHTML = "";

        var history = document.createElement("pre");
        history.className = "coding-terminal-history";
        for (var i = 0; i < ctx.inlineTerminalIndex; i++) {
            var p = ctx.inlineTerminalPrompts[i];
            var v = ctx.inlineTerminalValues[i] || "";
            history.appendChild(document.createTextNode((p.prompt || "") + v + "\n"));
        }
        ctx.outputNode.appendChild(history);

        if (ctx.inlineTerminalIndex < ctx.inlineTerminalPrompts.length) {
            var line = document.createElement("div");
            line.className = "coding-terminal-line";

            var promptSpan = document.createElement("span");
            promptSpan.className = "coding-terminal-prompt";
            promptSpan.textContent = ctx.inlineTerminalPrompts[ctx.inlineTerminalIndex].prompt || "";
            line.appendChild(promptSpan);

            var input = document.createElement("input");
            input.type = "text";
            input.className = "coding-terminal-input";
            input.setAttribute("autocomplete", "off");
            input.setAttribute("spellcheck", "false");
            input.setAttribute("autocapitalize", "off");
            input.setAttribute("autocorrect", "off");
            input.setAttribute("aria-label", ctx.inlineTerminalPrompts[ctx.inlineTerminalIndex].label || "stdin");
            line.appendChild(input);

            ctx.outputNode.appendChild(line);

            input.addEventListener("keydown", function (event) {
                if (event.key !== "Enter") return;
                event.preventDefault();
                ctx.inlineTerminalValues[ctx.inlineTerminalIndex] = input.value;
                ctx.inlineTerminalIndex += 1;
                if (ctx.inlineTerminalIndex < ctx.inlineTerminalPrompts.length) {
                    ctx.renderInlineTerminal();
                } else {
                    ctx.completeInlineTerminal();
                }
            });

            // Defer focus so the input is in the DOM and visible.
            window.setTimeout(function () { input.focus(); }, 30);

            if (ctx.inlineTerminalIndex === 0) {
                var hint = document.createElement("div");
                hint.className = "coding-terminal-hint";
                hint.textContent = (ctx.i18n.inlineTerminalHint || "Type the value here and press Enter.");
                ctx.outputNode.appendChild(hint);
            }
        }
    };

    ctx.completeInlineTerminal = function completeInlineTerminal() {
        ctx.lastInteractivePrompts = ctx.inlineTerminalPrompts.slice();
        ctx.lastInteractiveValues = ctx.inlineTerminalValues.slice();
        ctx.inlineTerminalActive = false;
        // Render the full transcript (history) so the student sees what
        // was provided, then submit the assembled stdin to the backend.
        var stdin = ctx.inlineTerminalValues.join("\n");
        if (ctx.stdinNode) ctx.stdinNode.value = stdin;
        ctx.syncStdinToQuestion();
        ctx.performBackendRun();
    };

    ctx.startInlineTerminal = function startInlineTerminal(prompts) {
        ctx.inlineTerminalActive = true;
        ctx.inlineTerminalPrompts = prompts;
        ctx.inlineTerminalValues = [];
        ctx.inlineTerminalIndex = 0;
        ctx.switchTab("output");
        ctx.setStatus(ctx.i18n.running || "Running...");
        ctx.setConsoleMeta("");
        ctx.renderInlineTerminal();
    };

    // Returns the file the backend will actually execute.
    ctx.resolveExecutionFile = function resolveExecutionFile() {
        var question = ctx.currentQuestion();
        if (!question) return null;
        var allFiles = question.files || ctx.files || [];
        var selectedLang = ctx.getSelectedLanguage();
        var active = ctx.currentFile();
        if (active && extensionLanguage(active.name, selectedLang) === selectedLang) {
            return active;
        }
        var byLanguage = allFiles.find(function (f) {
            return extensionLanguage(f.name, selectedLang) === selectedLang;
        });
        if (byLanguage) return byLanguage;
        var explicitMain = allFiles.find(function (f) { return f.is_main; });
        return active || explicitMain || allFiles[0] || null;
    };

    // Pure backend run — extracted so we can call it both directly (when
    // no inline terminal is needed) and at the tail of an inline session.
    ctx.performBackendRun = function performBackendRun() {
        ctx.isRunInFlight = true;
        clearTimeout(ctx.autosaveTimer);
        ctx.syncEditorToFile();
        ctx.syncStdinToQuestion();
        if (ctx.errorsNode) ctx.errorsNode.textContent = "";
        ctx.setStatus(ctx.i18n.running || "Running...");
        ctx.setConsoleMeta(ctx.i18n.runWaiting || "Waiting for runner...");
        if (ctx.runBtn) ctx.runBtn.disabled = true;

        ctx.requestJson(ctx.config.runUrl, ctx.collectPayload())
            .then(function (body) {
                ctx.hasUnsavedChanges = false;
                if (body.finished && body.redirect_url) {
                    navigateAway(body.redirect_url);
                    return;
                }
                ctx.applyRunResult(body.submission || {});
                ctx.setStatus(ctx.i18n.autoSaved || "Auto-saved");
            })
            .catch(function (error) {
                if (error.payload && error.payload.redirect_url) {
                    navigateAway(error.payload.redirect_url);
                    return;
                }
                var payload = error.payload || {};
                var retryAfter = parseInt(payload.retry_after_seconds, 10);
                if (!isNaN(retryAfter) && retryAfter > 0 && retryAfter <= 5) {
                    var label = error.message || "Run failed";
                    ctx.setStatus(label + " (auto-retry in " + retryAfter + "s)");
                    if (ctx.errorsNode) ctx.errorsNode.textContent = label;
                    ctx.switchTab("errors");
                    window.setTimeout(function () {
                        ctx.isRunInFlight = false;
                        if (ctx.runBtn) ctx.runBtn.disabled = false;
                        ctx.performBackendRun();
                    }, retryAfter * 1000);
                    return;
                }
                ctx.setTerminalText(ctx.outputNode, error.message || "Run failed");
                if (ctx.errorsNode) ctx.errorsNode.textContent = error.message || "Run failed";
                ctx.setConsoleMeta("");
                ctx.switchTab("errors");
                ctx.setStatus(error.message || "Run failed");
            })
            .finally(function () {
                if (ctx.isRunInFlight) {
                    ctx.isRunInFlight = false;
                    if (ctx.runBtn) ctx.runBtn.disabled = false;
                }
            });
    };

    ctx.runCode = function runCode() {
        if (ctx.isRunInFlight || ctx.inlineTerminalActive) {
            return;
        }
        if (ctx.shouldRunInBrowser()) {
            ctx.runBrowserCode();
            return;
        }
        // Each Run starts from a clean slate: clear stdin from the last
        // session so the inline terminal can re-prompt instead of silently
        // reusing stale values.
        var execFile = ctx.resolveExecutionFile();
        var prompts = detectStdinPrompts(ctx.getSelectedLanguage(), execFile && execFile.content);
        if (prompts.length) {
            if (ctx.stdinNode) ctx.stdinNode.value = "";
            var question = ctx.currentQuestion();
            if (question) question.stdin = "";
            ctx.lastInteractivePrompts = [];
            ctx.lastInteractiveValues = [];
            ctx.updateStdinHint();
            ctx.startInlineTerminal(prompts);
            return;
        }

        // No interactive prompts — empty the terminal and submit.
        ctx.setTerminalText(ctx.outputNode, "");
        ctx.switchTab("output");
        ctx.performBackendRun();
    };

    ctx.submitCode = function submitCode() {
        if (ctx.isSubmitting) {
            return;
        }
        ctx.isSubmitting = true;
        clearTimeout(ctx.autosaveTimer);
        ctx.syncEditorToFile();
        ctx.setStatus(ctx.i18n.submitting || "Submitting...");
        ctx.submitBtn.disabled = true;
        ctx.runBtn.disabled = true;
        ctx.requestJson(ctx.config.submitUrl, ctx.collectSubmitPayload())
            .then(function (body) {
                ctx.hasUnsavedChanges = false;
                ctx.setStatus(ctx.i18n.submitSuccess || "Submission successful");
                if (body.redirect_url) {
                    navigateAway(body.redirect_url);
                }
            })
            .catch(function (error) {
                if (error.payload && error.payload.redirect_url) {
                    navigateAway(error.payload.redirect_url);
                    return;
                }
                ctx.isSubmitting = false;
                ctx.submitBtn.disabled = false;
                ctx.runBtn.disabled = false;
                if (ctx.errorsNode) ctx.errorsNode.textContent = error.message || "Submit failed";
                ctx.switchTab("errors");
                ctx.setStatus(error.message || "Submit failed");
            });
    };

    ctx.openFinishConfirmModal = function openFinishConfirmModal() {
        ctx.syncEditorToFile();
        ctx.updateProgress();
        var unansweredCount = ctx.getUnansweredCount();
        var summary = unansweredCount > 0
            ? (ctx.i18n.finishUnansweredCount || "Unanswered questions: {count}.").replace("{count}", String(unansweredCount))
            : (ctx.i18n.finishAllAnswered || "All questions have been answered.");
        ctx.openConfirmModal({
            title: ctx.i18n.finishConfirmTitle || "Finish the exam?",
            body: (ctx.i18n.finishConfirmBody || "After you finish, you will not be able to return to this exam.") + " " + summary,
            confirmText: ctx.i18n.finishConfirmText || ctx.i18n.confirm || "Confirm",
            danger: true,
            onConfirm: ctx.submitCode
        });
    };
}
