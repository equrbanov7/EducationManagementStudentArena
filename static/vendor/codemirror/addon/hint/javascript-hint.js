// CodeMirror 5 JavaScript hint — vendored for EMSArena.
// Provides keyword + browser/Node global completions plus current-buffer identifiers.
(function (mod) {
    if (typeof exports === "object" && typeof module === "object") {
        mod(require("../../lib/codemirror"));
    } else if (typeof define === "function" && define.amd) {
        define(["../../lib/codemirror"], mod);
    } else {
        mod(CodeMirror);
    }
})(function (CodeMirror) {
    "use strict";

    var Pos = CodeMirror.Pos;
    var WORD = /[\w$]+/;

    var javascriptKeywords = (
        "break case catch class const continue debugger default delete do else export extends false finally for function if import in instanceof let new null of return super switch this throw true try typeof var void while with yield async await async of static get set"
    ).split(" ");

    var browserGlobals = (
        "window document console alert prompt confirm fetch JSON Math Object Array String Number Boolean Date RegExp Promise Map Set WeakMap WeakSet Symbol setTimeout setInterval clearTimeout clearInterval requestAnimationFrame cancelAnimationFrame URL URLSearchParams localStorage sessionStorage navigator location history Image Audio Video Event KeyboardEvent MouseEvent HTMLElement Node NodeList FormData Blob File FileReader Headers Request Response WebSocket EventSource Worker Notification IntersectionObserver MutationObserver ResizeObserver Intl"
    ).split(" ");

    var nodeGlobals = (
        "process require module exports Buffer __dirname __filename setImmediate clearImmediate global"
    ).split(" ");

    var consoleMethods = ["log", "info", "warn", "error", "debug", "trace", "table", "group", "groupEnd", "time", "timeEnd", "assert", "clear", "count", "dir"];

    // Dotted member completions — when the student types `owner.`, we offer
    // the methods/properties most commonly used on that built-in. Keeps the
    // popup focused on what is actually relevant for the cursor context.
    var memberMap = {
        console: consoleMethods,
        Math: ["PI", "E", "LN2", "LN10", "LOG2E", "LOG10E", "SQRT2", "abs", "ceil", "floor", "round", "trunc", "sign", "max", "min", "pow", "sqrt", "cbrt", "exp", "log", "log2", "log10", "random", "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "hypot"],
        JSON: ["parse", "stringify"],
        Object: ["keys", "values", "entries", "assign", "freeze", "isFrozen", "create", "defineProperty", "defineProperties", "getPrototypeOf", "setPrototypeOf", "fromEntries", "hasOwn"],
        Array: ["isArray", "from", "of"],
        String: ["fromCharCode", "raw"],
        Number: ["isInteger", "isFinite", "isNaN", "isSafeInteger", "parseInt", "parseFloat", "MAX_SAFE_INTEGER", "MIN_SAFE_INTEGER", "EPSILON"],
        Promise: ["resolve", "reject", "all", "allSettled", "race", "any"],
        document: [
            "getElementById", "getElementsByClassName", "getElementsByTagName", "getElementsByName",
            "querySelector", "querySelectorAll",
            "createElement", "createTextNode", "createDocumentFragment", "createEvent",
            "body", "head", "title", "documentElement", "URL", "location", "cookie", "readyState",
            "addEventListener", "removeEventListener", "dispatchEvent",
            "write", "writeln", "execCommand", "getSelection",
            "activeElement", "fullscreenElement", "hidden", "visibilityState",
            "forms", "images", "links", "scripts", "styleSheets"
        ],
        window: [
            "document", "console", "location", "history", "navigator", "screen",
            "innerWidth", "innerHeight", "outerWidth", "outerHeight", "scrollX", "scrollY",
            "alert", "confirm", "prompt",
            "setTimeout", "setInterval", "clearTimeout", "clearInterval",
            "requestAnimationFrame", "cancelAnimationFrame",
            "localStorage", "sessionStorage", "fetch",
            "addEventListener", "removeEventListener", "dispatchEvent",
            "open", "close", "focus", "blur", "scrollTo", "scrollBy",
            "getComputedStyle", "matchMedia", "atob", "btoa"
        ],
        location: ["href", "hostname", "host", "pathname", "search", "hash", "protocol", "port", "origin", "assign", "reload", "replace"],
        navigator: ["userAgent", "language", "languages", "platform", "onLine", "cookieEnabled", "clipboard", "geolocation", "mediaDevices"],
        history: ["length", "state", "back", "forward", "go", "pushState", "replaceState"],
        localStorage: ["getItem", "setItem", "removeItem", "clear", "key", "length"],
        sessionStorage: ["getItem", "setItem", "removeItem", "clear", "key", "length"]
    };

    // Generic "this looks like a DOM element" properties — applied as a
    // fallback when the dotted owner is an unknown identifier (e.g. a
    // variable holding the result of getElementById). Better than showing
    // nothing.
    var domElementMembers = [
        "innerHTML", "innerText", "textContent", "outerHTML",
        "value", "checked", "disabled", "selected", "readOnly", "hidden",
        "id", "className", "classList", "style", "dataset", "title", "tabIndex",
        "children", "childNodes", "firstChild", "lastChild", "parentNode", "parentElement", "nextElementSibling", "previousElementSibling",
        "appendChild", "removeChild", "replaceChild", "insertBefore", "append", "prepend", "remove",
        "querySelector", "querySelectorAll", "getElementsByClassName", "getElementsByTagName",
        "addEventListener", "removeEventListener", "dispatchEvent",
        "getAttribute", "setAttribute", "removeAttribute", "hasAttribute", "getBoundingClientRect",
        "focus", "blur", "click", "scrollIntoView",
        "offsetWidth", "offsetHeight", "offsetTop", "offsetLeft", "scrollTop", "scrollLeft", "scrollHeight", "scrollWidth"
    ];

    function collectIdentifiers(cm) {
        var seen = Object.create(null);
        var re = /[A-Za-z_$][\w$]*/g;
        for (var line = cm.firstLine(); line <= cm.lastLine(); ++line) {
            var text = cm.getLine(line);
            var match;
            while ((match = re.exec(text))) {
                seen[match[0]] = true;
            }
        }
        return Object.keys(seen);
    }

    function getCurrentWord(cm) {
        var cur = cm.getCursor();
        var line = cm.getLine(cur.line);
        var end = cur.ch;
        var start = end;
        while (start && WORD.test(line.charAt(start - 1))) --start;
        return {
            term: line.slice(start, end),
            from: Pos(cur.line, start),
            to: cur,
            line: line,
            cur: cur
        };
    }

    function dotMember(cm, context) {
        var cur = context.cur;
        var line = context.line;
        var idx = context.from.ch;
        if (idx <= 0 || line.charAt(idx - 1) !== ".") return null;
        var end = idx - 1;
        var start = end;
        while (start && /[\w$]/.test(line.charAt(start - 1))) --start;
        return line.slice(start, end);
    }

    function buildEntry(text, kind) {
        return { text: text, displayText: text, kind: kind };
    }

    function pushMembers(push, owner, members) {
        members.forEach(function (name) {
            push(buildEntry(name, owner));
        });
    }

    CodeMirror.registerHelper("hint", "javascript", function (cm) {
        var ctx = getCurrentWord(cm);
        var owner = dotMember(cm, ctx);

        var list = [];
        var seen = Object.create(null);
        function push(entry) {
            if (!entry || seen[entry.text]) return;
            if (ctx.term && entry.text.lastIndexOf(ctx.term, 0) !== 0) return;
            seen[entry.text] = true;
            list.push(entry);
        }

        // Dotted access: prefer a curated member list when we recognise the
        // owner; otherwise fall back to "DOM element" members because the
        // owner is most likely a variable holding an Element.
        if (owner) {
            if (memberMap[owner]) {
                pushMembers(push, owner, memberMap[owner]);
                if (!list.length) return null;
                return { list: list, from: ctx.from, to: ctx.to };
            }
            // Unknown owner — likely an Element / Node / array / string.
            // Offer DOM element members PLUS any identifier already used
            // in the buffer that follows a dot, so the popup is still useful.
            pushMembers(push, "member", domElementMembers);
            collectIdentifiers(cm).forEach(function (id) {
                push(buildEntry(id, "word"));
            });
            if (!list.length) return null;
            return { list: list, from: ctx.from, to: ctx.to };
        }

        javascriptKeywords.forEach(function (kw) {
            push(buildEntry(kw, "keyword"));
        });
        browserGlobals.forEach(function (g) {
            push(buildEntry(g, "global"));
        });
        nodeGlobals.forEach(function (g) {
            push(buildEntry(g, "node"));
        });
        collectIdentifiers(cm).forEach(function (id) {
            push(buildEntry(id, "word"));
        });

        if (!list.length) return null;
        return { list: list, from: ctx.from, to: ctx.to };
    });
});
