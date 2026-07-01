export function readJsonScript(id, fallback) {
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

export function navigateAway(url) {
    if (!url) return;
    window.EXAM_SUPERVISION_NAVIGATING = true;
    if (window.ExamSupervision && typeof window.ExamSupervision.destroy === "function") {
        window.ExamSupervision.destroy();
    }
    window.location.href = url;
}

export function formatTime(totalSeconds) {
    var value = Math.max(0, parseInt(totalSeconds, 10) || 0);
    var minutes = Math.floor(value / 60);
    var seconds = value % 60;
    return String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
}

export function modeForLanguage(language, languageModes) {
    return languageModes[language] || "text/plain";
}

export function extensionLanguage(name, fallback) {
    var lower = String(name || "").toLowerCase();
    if (lower.endsWith(".py")) return "python";
    if (lower.endsWith(".js")) return "javascript";
    if (lower.endsWith(".cpp") || lower.endsWith(".cc") || lower.endsWith(".cxx") || lower.endsWith(".h")) return "cpp";
    if (lower.endsWith(".java")) return "java";
    if (lower.endsWith(".html") || lower.endsWith(".htm")) return "html";
    if (lower.endsWith(".css")) return "css";
    return fallback || "text";
}

export function safeFileName(name) {
    var cleaned = String(name || "").trim().replace(/^.*[\\/]/, "");
    return /^[A-Za-z0-9_.-]{1,180}$/.test(cleaned) ? cleaned : "";
}

export function cloneFiles(files) {
    return (Array.isArray(files) ? files : []).map(function (file) {
        return {
            name: file.name,
            content: file.content || "",
            language: file.language || "text",
            is_main: Boolean(file.is_main)
        };
    });
}

export function assetName(value) {
    var clean = String(value || "").split("#")[0].split("?")[0].replace(/^\.?\//, "");
    return clean.split("/").pop();
}

export function escapeScriptText(value) {
    return String(value || "").replace(/<\/script/gi, "<\\/script");
}

// Language-specific hint helper name. CodeMirror lookups go through this
// so that adding a language only requires registering a matching helper.
export function hintHelperFor(language) {
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
export function detectStdinReadCount(language, mainContent) {
    return detectStdinPrompts(language, mainContent).length;
}

// Pull each stdin read from the main file together with its prompt text
// when one is available. The result feeds the pre-run input dialog so the
// student sees exactly what each value is for. We intentionally use simple
// regexes — anything more invasive would need a per-language parser, which
// is overkill for the heuristic UX we are building here.
export function detectStdinPrompts(language, mainContent) {
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

export function countNonEmptyLines(value) {
    return String(value || "")
        .split("\n")
        .map(function (line) {
            return line.trim();
        })
        .filter(Boolean).length;
}
