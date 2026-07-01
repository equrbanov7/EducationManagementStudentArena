import { assetName, escapeScriptText } from './utils.js';

export function installPreview(ctx) {
    ctx.appendConsoleLine = function appendConsoleLine(kind, message) {
        var prefix = kind === "warn" ? "[warn] " : kind === "error" ? "[error] " : "";
        var line = prefix + (message || "");
        ctx.browserRunHasOutput = true;
        if (ctx.outputNode) {
            // Ensure a <pre> child exists so accumulated lines stay in a
            // single mono-spaced block matching the terminal style.
            var pre = ctx.outputNode.querySelector(".coding-terminal-history");
            if (!pre) {
                ctx.outputNode.innerHTML = "";
                pre = document.createElement("pre");
                pre.className = "coding-terminal-history";
                ctx.outputNode.appendChild(pre);
            }
            pre.textContent += (pre.textContent ? "\n" : "") + line;
        }
        if (ctx.previewConsoleNode) {
            ctx.previewConsoleNode.textContent += (ctx.previewConsoleNode.textContent ? "\n" : "") + line;
        }
        if (kind === "error" && ctx.errorsNode) {
            ctx.errorsNode.textContent += (ctx.errorsNode.textContent ? "\n" : "") + line;
        }
    };

    ctx.applyPreviewNonce = function applyPreviewNonce(element) {
        if (ctx.previewNonce) {
            element.setAttribute("nonce", ctx.previewNonce);
        }
        return element;
    };

    ctx.consoleBridgeSource = function consoleBridgeSource(runId, stdinValues) {
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
    };

    ctx.buildPreviewDocument = function buildPreviewDocument(runId, options) {
        options = options || {};
        ctx.syncEditorToFile();
        var htmlFile = ctx.files.find(function (file) {
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
        ctx.files.forEach(function (file) {
            var name = assetName(file.name).toLowerCase();
            if (name.endsWith(".css")) cssFiles[name] = file;
            if (name.endsWith(".js")) jsFiles[name] = file;
        });

        Array.prototype.slice.call(doc.querySelectorAll('link[rel~="stylesheet"][href]')).forEach(function (link) {
            var file = cssFiles[assetName(link.getAttribute("href")).toLowerCase()];
            if (!file) return;
            var style = ctx.applyPreviewNonce(doc.createElement("style"));
            style.setAttribute("data-file", file.name);
            style.textContent = file.content || "";
            link.parentNode.replaceChild(style, link);
        });

        Array.prototype.slice.call(doc.querySelectorAll("style")).forEach(function (style) {
            ctx.applyPreviewNonce(style);
        });

        Array.prototype.slice.call(doc.querySelectorAll("script[src]")).forEach(function (script) {
            var file = jsFiles[assetName(script.getAttribute("src")).toLowerCase()];
            if (!file) return;
            var replacement = ctx.applyPreviewNonce(doc.createElement("script"));
            replacement.setAttribute("data-file", file.name);
            replacement.textContent = escapeScriptText(file.content || "");
            script.parentNode.replaceChild(replacement, script);
        });

        Array.prototype.slice.call(doc.querySelectorAll("script:not([src])")).forEach(function (script) {
            ctx.applyPreviewNonce(script);
        });

        // Pre-feed any stdin lines the student typed into the inline
        // terminal so the iframe's overridden prompt() returns them in
        // order, instead of re-prompting the user at the top of the page.
        var stdinValues = [];
        var rawStdin = (ctx.currentQuestion() && ctx.currentQuestion().stdin) || "";
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
        var bridge = ctx.applyPreviewNonce(doc.createElement("script"));
        bridge.textContent = ctx.consoleBridgeSource(runId, stdinValues);
        doc.head.insertBefore(bridge, doc.head.firstChild);

        if (options.executeCurrentJavaScriptOnly) {
            var active = ctx.currentFile();
            var main = ctx.files.find(function (file) { return file.is_main && String(file.name).toLowerCase().endsWith(".js"); });
            var jsFile = String(active && active.name).toLowerCase().endsWith(".js") ? active : main;
            if (jsFile) {
                var runScript = ctx.applyPreviewNonce(doc.createElement("script"));
                runScript.setAttribute("data-file", jsFile.name);
                runScript.textContent = escapeScriptText(jsFile.content || "");
                doc.body.appendChild(runScript);
            }
        }

        return "<!doctype html>\n" + doc.documentElement.outerHTML;
    };

    ctx.updateBrowserChromeForCurrentFile = function updateBrowserChromeForCurrentFile() {
        // Keep the fake browser chrome consistent with what's actually
        // being rendered: show the html filename as the tab title and a
        // plausible "URL" so students can intuit which file produced the
        // preview when they have multiple html files.
        if (!ctx.browserTabTitleNode && !ctx.browserUrlNode) return;
        var htmlFile = ctx.files.find(function (file) {
            return String(file.name || "").toLowerCase().match(/\.html?$/);
        });
        var name = htmlFile ? htmlFile.name : "preview.html";
        if (ctx.browserTabTitleNode) {
            ctx.browserTabTitleNode.textContent = name;
        }
        if (ctx.browserUrlNode) {
            ctx.browserUrlNode.textContent = "preview://" + name;
        }
    };

    ctx.renderPreview = function renderPreview(options) {
        if (!ctx.previewFrame) {
            return;
        }
        options = options || {};
        var runId = options.runId || ++ctx.previewRunId;
        ctx.updateBrowserChromeForCurrentFile();
        ctx.previewFrame.removeAttribute("src");
        ctx.previewFrame.removeAttribute("srcdoc");
        window.requestAnimationFrame(function () {
            ctx.previewFrame.srcdoc = ctx.buildPreviewDocument(runId, options);
        });
    };

    ctx.handlePreviewMessage = function handlePreviewMessage(event) {
        if (!ctx.previewFrame || event.source !== ctx.previewFrame.contentWindow) {
            return;
        }
        var data = event.data || {};
        if (!data.__codingPreviewConsole || data.runId !== ctx.previewRunId) {
            return;
        }
        ctx.appendConsoleLine(data.kind, data.message);
    };

    // Heuristic: code that touches browser globals (document, window,
    // alert, innerHTML, addEventListener, onclick, ...) cannot run in the
    // Node sandbox because Node has no DOM. When we spot such usage AND the
    // question already ships an HTML file we can host it in, defer to the
    // iframe-based browser runner instead.
    ctx.jsUsesBrowserGlobals = function jsUsesBrowserGlobals(content) {
        if (!content) return false;
        var probe = String(content);
        // Strip line and block comments so commented-out DOM calls don't
        // count as real usage.
        probe = probe.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/[^\n]*/g, " ");
        return /\b(document|window|alert|confirm|navigator|location|history|localStorage|sessionStorage|getElementById|querySelector|querySelectorAll|innerHTML|innerText|textContent|addEventListener|onclick|onchange|onsubmit|onload|onkeydown|requestAnimationFrame|fetch)\b/.test(probe);
    };

    ctx.activeJsFilesUseBrowserGlobals = function activeJsFilesUseBrowserGlobals() {
        var question = ctx.currentQuestion();
        if (!question) return false;
        return (question.files || []).some(function (file) {
            var lower = String(file.name || "").toLowerCase();
            if (!lower.endsWith(".js")) return false;
            return ctx.jsUsesBrowserGlobals(file.content);
        });
    };

    ctx.shouldRunInBrowser = function shouldRunInBrowser() {
        var selected = ctx.getSelectedLanguage();
        var activeLanguage = ctx.getActiveFileLanguage();
        if (selected === "html" || activeLanguage === "html" || activeLanguage === "css") {
            return true;
        }
        // JavaScript that uses DOM/browser APIs: only safe to host in the
        // iframe runner, which requires an HTML shell to attach to.
        if (selected === "javascript" || activeLanguage === "javascript") {
            if (ctx.hasHtmlFile() && ctx.activeJsFilesUseBrowserGlobals()) {
                return true;
            }
        }
        return false;
    };
}
