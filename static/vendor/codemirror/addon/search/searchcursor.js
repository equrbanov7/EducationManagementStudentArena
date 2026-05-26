// CodeMirror 5 SearchCursor addon — minimal vendored version for in-editor find.
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

    function regexpFlags(regexp) {
        var flags = regexp.flags;
        return flags !== null && flags !== undefined
            ? flags
            : (regexp.ignoreCase ? "i" : "") + (regexp.global ? "g" : "") + (regexp.multiline ? "m" : "");
    }

    function ensureGlobal(regexp, caseFold) {
        var flags = regexpFlags(regexp);
        if (flags.indexOf("g") === -1) flags += "g";
        if (caseFold && flags.indexOf("i") === -1) flags += "i";
        return new RegExp(regexp.source, flags);
    }

    function SearchCursor(doc, query, pos, options) {
        this.atOccurrence = false;
        this.afterEmptyMatch = false;
        this.doc = doc;
        pos = pos ? doc.clipPos(pos) : Pos(0, 0);
        this.pos = { from: pos, to: pos };

        var caseFold = options && options.caseFold !== undefined ? options.caseFold : false;
        if (typeof query === "string") {
            if (caseFold) query = query.toLowerCase();
            var origQuery = query;
            this.matches = function (reverse, position) {
                if (reverse) {
                    var line = doc.getLine(position.line).slice(0, position.ch);
                    if (caseFold) line = line.toLowerCase();
                    var match = line.lastIndexOf(query);
                    if (match === -1) return;
                    return {
                        from: Pos(position.line, match),
                        to: Pos(position.line, match + query.length)
                    };
                } else {
                    var lineText = doc.getLine(position.line).slice(position.ch);
                    if (caseFold) lineText = lineText.toLowerCase();
                    var idx = lineText.indexOf(query);
                    if (idx === -1) return;
                    return {
                        from: Pos(position.line, position.ch + idx),
                        to: Pos(position.line, position.ch + idx + query.length)
                    };
                }
            };
        } else {
            var regex = ensureGlobal(query, caseFold);
            this.matches = function (reverse, position) {
                var line = doc.getLine(position.line);
                if (caseFold) line = line.toLowerCase();
                regex.lastIndex = reverse ? 0 : position.ch;
                var m = regex.exec(line);
                if (!m) return;
                return {
                    from: Pos(position.line, m.index),
                    to: Pos(position.line, m.index + m[0].length)
                };
            };
        }
    }

    SearchCursor.prototype = {
        findNext: function () {
            return this.find(false);
        },
        findPrevious: function () {
            return this.find(true);
        },
        find: function (reverse) {
            var doc = this.doc;
            var pos = reverse ? this.pos.from : this.pos.to;
            var lineCount = doc.lineCount();
            var line = pos.line;
            while (line >= 0 && line < lineCount) {
                var match = this.matches(reverse, { line: line, ch: pos.ch });
                if (match) {
                    this.pos = match;
                    this.atOccurrence = true;
                    return match;
                }
                line += reverse ? -1 : 1;
                pos = { line: line, ch: reverse ? doc.getLine(line) ? doc.getLine(line).length : 0 : 0 };
            }
            this.atOccurrence = false;
            return false;
        },
        from: function () {
            return this.atOccurrence ? this.pos.from : null;
        },
        to: function () {
            return this.atOccurrence ? this.pos.to : null;
        },
        replace: function (newText) {
            if (!this.atOccurrence) return;
            this.doc.replaceRange(newText, this.pos.from, this.pos.to);
        }
    };

    CodeMirror.defineExtension("getSearchCursor", function (query, pos, options) {
        return new SearchCursor(this.doc, query, pos, options);
    });
});
