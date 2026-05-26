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

    var consoleMethods = ["log", "info", "warn", "error", "debug", "trace", "table", "group", "groupEnd", "time", "timeEnd"];

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

        if (owner === "console") {
            consoleMethods.forEach(function (name) {
                push(buildEntry(name, "method"));
            });
            return { list: list, from: ctx.from, to: ctx.to };
        }

        if (owner === "Math") {
            ["PI", "E", "abs", "ceil", "floor", "round", "max", "min", "pow", "sqrt", "random", "sign", "trunc", "log", "log10", "log2"].forEach(
                function (name) {
                    push(buildEntry(name, name === "PI" || name === "E" ? "constant" : "method"));
                }
            );
            return { list: list, from: ctx.from, to: ctx.to };
        }

        if (owner === "JSON") {
            ["parse", "stringify"].forEach(function (name) {
                push(buildEntry(name, "method"));
            });
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
