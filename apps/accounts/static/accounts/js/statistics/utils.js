(function (window, document) {
  "use strict";

  var ns = window.EMSStatistics || (window.EMSStatistics = {});

  var COLORS = {
    primary: "#0d6efd",
    success: "#198754",
    warning: "#ffc107",
    danger: "#dc3545",
    info: "#0dcaf0",
    secondary: "#6c757d"
  };
  var CHART_PALETTE = [
    "#0d6efd", "#198754", "#ffc107", "#dc3545", "#0dcaf0",
    "#6f42c1", "#fd7e14", "#20c997", "#d63384", "#6c757d"
  ];

  function createContext() {
    var data = window.STATS_DATA;
    if (!data || !data.summary) {
      return null;
    }
    return {
      data: data,
      i18n: window.STATS_I18N || {},
      role: data.role || "student",
      COLORS: COLORS,
      CHART_PALETTE: CHART_PALETTE
    };
  }

  function pct(numerator, denominator) {
    if (!denominator) {
      return 0;
    }
    return Math.round((Number(numerator || 0) * 1000) / Number(denominator)) / 10;
  }

  function getCtx(id) {
    var el = document.getElementById(id);
    return el ? el.getContext("2d") : null;
  }

  function truncateLabel(value) {
    var text = String(value || "");
    return text.length > 22 ? text.slice(0, 22) + "..." : text;
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function renderInlineMarkdown(value) {
    return escapeHtml(value)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>");
  }

  function markdownToHtml(markdown) {
    if (!markdown) {
      return "";
    }

    var lines = String(markdown).replace(/\r\n?/g, "\n").split("\n");
    var html = [];
    var paragraph = [];
    var listItems = [];
    var listType = null;

    function flushParagraph() {
      if (!paragraph.length) {
        return;
      }
      html.push("<p>" + paragraph.map(renderInlineMarkdown).join("<br>") + "</p>");
      paragraph = [];
    }

    function flushList() {
      if (!listItems.length || !listType) {
        return;
      }
      html.push(
        "<" + listType + ">" +
        listItems.map(function (item) { return "<li>" + renderInlineMarkdown(item) + "</li>"; }).join("") +
        "</" + listType + ">"
      );
      listItems = [];
      listType = null;
    }

    lines.forEach(function (line) {
      var trimmed = line.trim();
      var headingMatch = trimmed.match(/^(#{1,3})\s+(.+)$/);
      var unorderedMatch = trimmed.match(/^[-*]\s+(.+)$/);
      var orderedMatch = trimmed.match(/^\d+\.\s+(.+)$/);

      if (!trimmed) {
        flushParagraph();
        flushList();
        return;
      }

      if (headingMatch) {
        flushParagraph();
        flushList();
        var level = Math.min(headingMatch[1].length + 2, 5);
        html.push("<h" + level + ">" + renderInlineMarkdown(headingMatch[2]) + "</h" + level + ">");
        return;
      }

      if (unorderedMatch) {
        flushParagraph();
        if (listType && listType !== "ul") {
          flushList();
        }
        listType = "ul";
        listItems.push(unorderedMatch[1]);
        return;
      }

      if (orderedMatch) {
        flushParagraph();
        if (listType && listType !== "ol") {
          flushList();
        }
        listType = "ol";
        listItems.push(orderedMatch[1]);
        return;
      }

      flushList();
      paragraph.push(trimmed);
    });

    flushParagraph();
    flushList();
    return html.join("");
  }

  ns.utils = {
    createContext: createContext,
    getCtx: getCtx,
    markdownToHtml: markdownToHtml,
    pct: pct,
    truncateLabel: truncateLabel
  };
})(window, document);
