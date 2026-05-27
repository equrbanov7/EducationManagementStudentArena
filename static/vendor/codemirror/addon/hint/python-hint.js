// CodeMirror 5 Python hint — keywords, builtins, common stdlib members.
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
    var WORD = /[\w]+/;

    var keywords = (
        "False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield match case"
    ).split(" ");

    var builtins = (
        "abs all any ascii bin bool breakpoint bytearray bytes callable chr classmethod compile complex delattr dict dir divmod enumerate eval exec filter float format frozenset getattr globals hasattr hash help hex id input int isinstance issubclass iter len list locals map max memoryview min next object oct open ord pow print property range repr reversed round set setattr slice sorted staticmethod str sum super tuple type vars zip __import__"
    ).split(" ");

    var commonModules = ["math", "os", "sys", "re", "json", "random", "datetime", "time", "collections", "itertools", "functools", "typing", "pathlib", "subprocess", "urllib", "http"];

    var memberMap = {
        os: ["path", "getenv", "environ", "listdir", "mkdir", "makedirs", "remove", "rename", "walk", "system", "getcwd", "chdir", "rmdir"],
        sys: ["argv", "exit", "stdin", "stdout", "stderr", "version", "platform", "path", "maxsize", "modules"],
        math: ["pi", "e", "tau", "inf", "nan", "sqrt", "pow", "log", "log2", "log10", "ceil", "floor", "factorial", "gcd", "isnan", "isinf", "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "degrees", "radians", "fabs"],
        re: ["match", "search", "findall", "finditer", "sub", "subn", "compile", "split", "fullmatch", "escape"],
        json: ["dumps", "loads", "dump", "load"],
        random: ["random", "randint", "choice", "choices", "shuffle", "sample", "uniform", "seed", "randrange"],
        datetime: ["datetime", "date", "time", "timedelta", "now", "today", "fromtimestamp", "strptime"],
        collections: ["Counter", "defaultdict", "OrderedDict", "deque", "namedtuple", "ChainMap"],
        itertools: ["chain", "count", "cycle", "product", "permutations", "combinations", "groupby", "islice", "takewhile", "dropwhile", "starmap", "tee", "zip_longest"],
        // Built-in type prototypes — surface them when the student types
        // something like `name.<TAB>` and we cannot infer the type. The hint
        // helper falls back to this list before showing buffer identifiers.
        str: ["upper", "lower", "title", "capitalize", "strip", "lstrip", "rstrip", "split", "rsplit", "join", "replace", "startswith", "endswith", "find", "rfind", "index", "count", "format", "encode", "isdigit", "isalpha", "isalnum", "isspace", "zfill", "center", "ljust", "rjust"],
        list: ["append", "extend", "insert", "remove", "pop", "clear", "index", "count", "sort", "reverse", "copy"],
        dict: ["keys", "values", "items", "get", "pop", "popitem", "update", "setdefault", "clear", "copy"],
        set: ["add", "remove", "discard", "pop", "clear", "copy", "union", "intersection", "difference", "symmetric_difference", "issubset", "issuperset"],
        tuple: ["count", "index"]
    };

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
            line: line
        };
    }

    function dotMember(line, fromCh) {
        if (fromCh <= 0 || line.charAt(fromCh - 1) !== ".") return null;
        var end = fromCh - 1;
        var start = end;
        while (start && /[\w]/.test(line.charAt(start - 1))) --start;
        return line.slice(start, end);
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

    CodeMirror.registerHelper("hint", "python", function (cm) {
        var ctx = getCurrentWord(cm);
        var owner = dotMember(ctx.line, ctx.from.ch);

        var list = [];
        var seen = Object.create(null);
        function push(item) {
            if (!item || seen[item.text]) return;
            if (ctx.term && item.text.lastIndexOf(ctx.term, 0) !== 0) return;
            seen[item.text] = true;
            list.push(item);
        }

        if (owner && memberMap[owner]) {
            memberMap[owner].forEach(function (m) {
                push(entry(m, "member"));
            });
            return { list: list, from: ctx.from, to: ctx.to };
        }

        keywords.forEach(function (kw) {
            push(entry(kw, "keyword"));
        });
        builtins.forEach(function (b) {
            push(entry(b, "builtin"));
        });
        commonModules.forEach(function (m) {
            push(entry(m, "module"));
        });
        collectIdentifiers(cm).forEach(function (id) {
            push(entry(id, "word"));
        });

        if (!list.length) return null;
        return { list: list, from: ctx.from, to: ctx.to };
    });
});
