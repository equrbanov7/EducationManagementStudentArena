// CodeMirror 5 comment addon — toggleComment / lineComment / blockComment.
// Vendored for EMSArena; uses mode metadata to comment lines or blocks.
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

    var noOptions = {};
    var nonWS = /[^\s ]/;
    var Pos = CodeMirror.Pos;
    var cmp = CodeMirror.cmpPos;

    function probablyInsideString(cm, pos, line) {
        return /\bstring\b/.test(cm.getTokenTypeAt(Pos(pos.line, 0))) && !/^[\'\"`]/.test(line);
    }

    function getMode(cm, pos) {
        var mode = cm.getMode();
        return mode.useInnerComments === false || !mode.innerMode ? mode : cm.getModeAt(pos);
    }

    CodeMirror.commands.toggleComment = function (cm) {
        cm.toggleComment();
    };

    CodeMirror.defineExtension("toggleComment", function (options) {
        if (!options) options = noOptions;
        var cm = this;
        var minLine = Infinity,
            ranges = this.listSelections(),
            mode = null;
        for (var i = ranges.length - 1; i >= 0; i--) {
            var from = ranges[i].from(),
                to = ranges[i].to();
            if (from.line >= minLine) continue;
            if (to.line >= minLine) to = Pos(minLine, 0);
            minLine = from.line;
            if (mode === null) {
                if (cm.uncomment(from, to, options)) mode = "un";
                else {
                    cm.lineComment(from, to, options);
                    mode = "line";
                }
            } else if (mode === "un") {
                cm.uncomment(from, to, options);
            } else {
                cm.lineComment(from, to, options);
            }
        }
    });

    function commentExtras(cm, options) {
        var commentBlankLines = options.commentBlankLines || cm.somethingSelected();
        return commentBlankLines;
    }

    function lineCommentString(mode) {
        return mode.lineComment || (mode.helperType === "text/x-csrc" ? "//" : null);
    }

    CodeMirror.defineExtension("lineComment", function (from, to, options) {
        if (!options) options = noOptions;
        var self = this;
        var mode = getMode(self, from);
        var firstLine = self.getLine(from.line);
        if (firstLine === null || probablyInsideString(self, from, firstLine)) return;
        var commentString = options.lineComment || lineCommentString(mode);
        if (!commentString) {
            if (options.blockCommentStart || mode.blockCommentStart) {
                options.fullLines = true;
                self.blockComment(from, to, options);
            }
            return;
        }
        var end = Math.min(to.ch !== 0 || to.line === from.line ? to.line + 1 : to.line, self.lastLine() + 1);
        var pad = options.padding === undefined ? " " : options.padding;
        var blankLines = commentExtras(self, options);
        self.operation(function () {
            if (options.indent) {
                var baseString = null;
                for (var i = from.line; i < end; ++i) {
                    var line = self.getLine(i);
                    var whitespace = line.search(nonWS);
                    var current = whitespace === -1 ? line : line.slice(0, whitespace);
                    if (baseString === null || baseString.length > current.length) {
                        baseString = current;
                    }
                }
                for (var i = from.line; i < end; ++i) {
                    var line = self.getLine(i),
                        cut = baseString.length;
                    if (!blankLines && !nonWS.test(line)) continue;
                    if (line.slice(0, cut) !== baseString) cut = line.search(nonWS);
                    self.replaceRange(baseString + commentString + pad, Pos(i, 0), Pos(i, cut));
                }
            } else {
                for (var i = from.line; i < end; ++i) {
                    if (blankLines || nonWS.test(self.getLine(i))) self.replaceRange(commentString + pad, Pos(i, 0));
                }
            }
        });
    });

    CodeMirror.defineExtension("blockComment", function (from, to, options) {
        if (!options) options = noOptions;
        var self = this,
            mode = getMode(self, from);
        var startString = options.blockCommentStart || mode.blockCommentStart;
        var endString = options.blockCommentEnd || mode.blockCommentEnd;
        if (!startString || !endString) {
            if ((options.lineComment || mode.lineComment) && options.fullLines !== false) self.lineComment(from, to, options);
            return;
        }
        if (/comment/.test(self.getTokenTypeAt(Pos(from.line, 0)))) return;
        var end = Math.min(to.line, self.lastLine());
        if (end !== from.line && to.ch === 0 && nonWS.test(self.getLine(end))) --end;
        var pad = options.padding === undefined ? " " : options.padding;
        if (from.line > end) return;
        self.operation(function () {
            if (options.fullLines !== false) {
                var lastLineHasText = nonWS.test(self.getLine(end));
                self.replaceRange(pad + endString, Pos(end));
                self.replaceRange(startString + pad, Pos(from.line, 0));
                var lead = options.blockCommentLead || mode.blockCommentLead;
                if (lead !== null && lead !== undefined) {
                    for (var i = from.line + 1; i <= end; ++i) {
                        if (i !== end || lastLineHasText) self.replaceRange(lead + pad, Pos(i, 0));
                    }
                }
            } else {
                var fromLine = cmp(self.getCursor("to"), to) === 0,
                    multi = !self.somethingSelected();
                self.replaceRange(endString, to);
                if (fromLine) self.setSelection(multi ? to : self.getCursor("from"), to);
                self.replaceRange(startString, from);
            }
        });
    });

    CodeMirror.defineExtension("uncomment", function (from, to, options) {
        if (!options) options = noOptions;
        var self = this,
            mode = getMode(self, from);
        var end = Math.min(to.ch !== 0 || to.line === from.line ? to.line : to.line - 1, self.lastLine()),
            start = Math.min(from.line, end);
        var lineString = options.lineComment || lineCommentString(mode);
        var lines = [];
        var pad = options.padding === undefined ? " " : options.padding;
        var didSomething;
        lineComment: {
            if (!lineString) break lineComment;
            for (var i = start; i <= end; ++i) {
                var line = self.getLine(i),
                    found = line.indexOf(lineString);
                if (found > -1 && !/comment/.test(self.getTokenTypeAt(Pos(i, found + 1)))) found = -1;
                if (found === -1 && nonWS.test(line)) break lineComment;
                if (found > -1 && nonWS.test(line.slice(0, found))) break lineComment;
                lines.push(line);
            }
            self.operation(function () {
                for (var i = start; i <= end; ++i) {
                    var line = lines[i - start];
                    var pos = line.indexOf(lineString),
                        endPos = pos + lineString.length;
                    if (pos < 0) continue;
                    if (line.slice(endPos, endPos + pad.length) === pad) endPos += pad.length;
                    didSomething = true;
                    self.replaceRange("", Pos(i, pos), Pos(i, endPos));
                }
            });
            if (didSomething) return true;
        }
        return false;
    });
});
