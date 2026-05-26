// CodeMirror 5 HTML/CSS hint bundle — tags, attributes, common values.
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

    var htmlTags = (
        "a abbr address area article aside audio b base bdi bdo blockquote body br button canvas caption cite code col colgroup data datalist dd del details dfn dialog div dl dt em embed fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 head header hr html i iframe img input ins kbd label legend li link main map mark menu meta meter nav noscript object ol optgroup option output p param picture pre progress q rb rp rt rtc ruby s samp script section select slot small source span strong style sub summary sup table tbody td template textarea tfoot th thead time title tr track u ul var video wbr"
    ).split(" ");

    var commonAttrs = (
        "class id style title role href src alt name type value placeholder for action method target rel data-* aria-label aria-hidden aria-controls aria-expanded tabindex disabled readonly required checked selected multiple"
    ).split(" ");

    var cssProperties = (
        "align-items align-content align-self animation appearance background background-color background-image background-position background-repeat background-size border border-radius border-color border-style border-width box-shadow box-sizing color cursor display flex flex-direction flex-grow flex-shrink flex-wrap font font-family font-size font-style font-weight gap grid grid-area grid-template grid-template-columns grid-template-rows height justify-content justify-items justify-self letter-spacing line-height list-style margin margin-top margin-right margin-bottom margin-left max-height max-width min-height min-width object-fit opacity outline overflow padding padding-top padding-right padding-bottom padding-left pointer-events position resize text-align text-decoration text-overflow text-transform top right bottom left transform transition transition-property transition-duration transition-timing-function user-select vertical-align visibility white-space width word-break word-spacing z-index"
    ).split(" ");

    var cssValues = ["auto", "none", "block", "flex", "grid", "inline", "inline-block", "absolute", "relative", "fixed", "sticky", "center", "left", "right", "wrap", "nowrap", "row", "column", "space-between", "space-around", "pointer", "default", "100%", "0", "1rem", "1em", "transparent", "inherit", "initial"];

    function getCurrentWord(cm, allowed) {
        var cur = cm.getCursor();
        var line = cm.getLine(cur.line);
        var end = cur.ch;
        var start = end;
        while (start && allowed.test(line.charAt(start - 1))) --start;
        return {
            term: line.slice(start, end),
            from: Pos(cur.line, start),
            to: cur,
            line: line,
            cur: cur
        };
    }

    function entry(text, kind) {
        return { text: text, displayText: text, kind: kind };
    }

    function htmlContext(line, fromCh) {
        // detect if we are inside <...>
        var openIdx = line.lastIndexOf("<", fromCh - 1);
        var closeIdx = line.lastIndexOf(">", fromCh - 1);
        if (openIdx === -1) return "text";
        if (closeIdx > openIdx) return "text";
        // Inside a tag. Check whether we are typing a tag name (right after "<").
        if (fromCh - 1 === openIdx) return "tag";
        return "attr";
    }

    CodeMirror.registerHelper("hint", "html", function (cm) {
        var ctx = getCurrentWord(cm, /[\w-]/);
        var location = htmlContext(ctx.line, ctx.from.ch);

        var list = [];
        var seen = Object.create(null);
        function push(item) {
            if (!item || seen[item.text]) return;
            if (ctx.term && item.text.lastIndexOf(ctx.term, 0) !== 0) return;
            seen[item.text] = true;
            list.push(item);
        }

        if (location === "tag") {
            htmlTags.forEach(function (tag) {
                push(entry(tag, "tag"));
            });
        } else if (location === "attr") {
            commonAttrs.forEach(function (a) {
                push(entry(a, "attr"));
            });
        } else {
            htmlTags.forEach(function (tag) {
                push(entry("<" + tag + ">", "tag"));
            });
        }

        if (!list.length) return null;
        return { list: list, from: ctx.from, to: ctx.to };
    });

    CodeMirror.registerHelper("hint", "css", function (cm) {
        var ctx = getCurrentWord(cm, /[\w-]/);

        var list = [];
        var seen = Object.create(null);
        function push(item) {
            if (!item || seen[item.text]) return;
            if (ctx.term && item.text.lastIndexOf(ctx.term, 0) !== 0) return;
            seen[item.text] = true;
            list.push(item);
        }

        cssProperties.forEach(function (p) {
            push(entry(p, "property"));
        });
        cssValues.forEach(function (v) {
            push(entry(v, "value"));
        });

        if (!list.length) return null;
        return { list: list, from: ctx.from, to: ctx.to };
    });
});
