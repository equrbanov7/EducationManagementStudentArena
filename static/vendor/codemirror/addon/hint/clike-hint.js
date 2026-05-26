// CodeMirror 5 C/C++/Java hint — vendored for EMSArena.
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
    var WORD = /[\w]/;

    var cppKeywords = (
        "auto break case catch char class const constexpr continue default delete do double else enum explicit extern false float for friend goto if inline int long mutable namespace new noexcept nullptr operator private protected public register return short signed sizeof static struct switch template this throw true try typedef typeid typename union unsigned using virtual void volatile while"
    ).split(" ");

    var cppStd = ["std", "cin", "cout", "cerr", "endl", "string", "vector", "map", "set", "pair", "make_pair", "to_string", "stoi", "stod", "size_t", "uint32_t", "int64_t", "printf", "scanf", "include", "iostream", "vector", "algorithm", "sort", "reverse", "min", "max", "abs", "pow", "sqrt", "memset", "getline"];

    var javaKeywords = (
        "abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for goto if implements import instanceof int interface long native new package private protected public return short static strictfp super switch synchronized this throw throws transient try void volatile while true false null var record sealed permits"
    ).split(" ");

    var javaStd = ["System", "String", "Integer", "Double", "Float", "Boolean", "Math", "Object", "ArrayList", "HashMap", "HashSet", "LinkedList", "Scanner", "BufferedReader", "InputStreamReader", "PrintWriter", "List", "Map", "Set", "Collections", "Arrays", "Comparator", "Optional", "Stream", "Files", "Path", "Paths", "Exception", "RuntimeException", "IOException", "out", "println", "print", "in", "nextInt", "nextLine", "next", "nextDouble", "hasNext"];

    function getCurrentWord(cm) {
        var cur = cm.getCursor();
        var line = cm.getLine(cur.line);
        var end = cur.ch;
        var start = end;
        while (start && WORD.test(line.charAt(start - 1))) --start;
        return {
            term: line.slice(start, end),
            from: Pos(cur.line, start),
            to: cur
        };
    }

    function collectIdentifiers(cm) {
        var seen = Object.create(null);
        var re = /[A-Za-z_][\w]*/g;
        for (var line = cm.firstLine(); line <= cm.lastLine(); ++line) {
            var text = cm.getLine(line);
            var match;
            while ((match = re.exec(text))) seen[match[0]] = true;
        }
        return Object.keys(seen);
    }

    function entry(text, kind) {
        return { text: text, displayText: text, kind: kind };
    }

    function build(keywords, std) {
        return function (cm) {
            var ctx = getCurrentWord(cm);
            var list = [];
            var seen = Object.create(null);
            function push(item) {
                if (!item || seen[item.text]) return;
                if (ctx.term && item.text.lastIndexOf(ctx.term, 0) !== 0) return;
                seen[item.text] = true;
                list.push(item);
            }
            keywords.forEach(function (kw) {
                push(entry(kw, "keyword"));
            });
            std.forEach(function (s) {
                push(entry(s, "std"));
            });
            collectIdentifiers(cm).forEach(function (id) {
                push(entry(id, "word"));
            });
            if (!list.length) return null;
            return { list: list, from: ctx.from, to: ctx.to };
        };
    }

    CodeMirror.registerHelper("hint", "clike", build(cppKeywords, cppStd));
    CodeMirror.registerHelper("hint", "cpp", build(cppKeywords, cppStd));
    CodeMirror.registerHelper("hint", "java", build(javaKeywords, javaStd));
});
