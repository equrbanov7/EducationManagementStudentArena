/*
 * Elektron jurnal detalı (U13) — tab naviqasiyası + Excel-vari klaviatura keçidi.
 * CSP-safe (inline yoxdur), progressive enhancement: JS olmadan bütün panellər
 * `hidden` atributu ilə gizlidir, ilk panel (grid) görünür — formlar işləyir.
 *
 * - Tablar: [data-journal-tabs] düymələri panelləri dəyişir; seçim sessionStorage-də
 *   offering üzrə yadda saxlanır (POST-redirect-dən sonra istifadəçi eyni tabda qalır);
 *   URL hash (#tab-finals) üstünlük təşkil edir.
 * - Klaviatura: grid daxilindəki .cell-score input-larında ↑/↓/←/→ qonşu xanaya
 *   fokus keçirir (Excel davranışı); ← / → yalnız kursor input kənarındadırsa.
 */
(function () {
  "use strict";

  var page = document.querySelector(".jd-page");
  if (!page) return;

  // ── Tablar ────────────────────────────────────────────────────────────────
  var tabBar = page.querySelector("[data-journal-tabs]");
  if (tabBar) {
    var storageKey = "jd-tab:" + (page.getAttribute("data-offering-id") || "");
    var tabs = Array.prototype.slice.call(tabBar.querySelectorAll("[data-jtab]"));
    var panels = Array.prototype.slice.call(page.querySelectorAll("[data-jtab-panel]"));

    function activate(name, persist) {
      var found = false;
      panels.forEach(function (panel) {
        var match = panel.getAttribute("data-jtab-panel") === name;
        panel.hidden = !match;
        panel.classList.toggle("is-active", match);
        if (match) found = true;
      });
      tabs.forEach(function (tab) {
        var match = tab.getAttribute("data-jtab") === name;
        tab.classList.toggle("is-active", match);
        tab.setAttribute("aria-selected", match ? "true" : "false");
      });
      if (found && persist) {
        try { window.sessionStorage.setItem(storageKey, name); } catch (e) { /* ignore */ }
      }
      return found;
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        activate(tab.getAttribute("data-jtab"), true);
      });
    });

    // Bərpa: URL hash → sessionStorage → default (grid).
    var initial = (window.location.hash || "").replace("#tab-", "");
    if (!initial) {
      try { initial = window.sessionStorage.getItem(storageKey) || ""; } catch (e) { /* ignore */ }
    }
    if (initial && initial !== "grid") {
      activate(initial, false);
    }
  }

  // ── Excel-vari klaviatura keçidi ─────────────────────────────────────────
  page.querySelectorAll("[data-journal-grid]").forEach(function (wrap) {
    var table = wrap.querySelector("table");
    if (!table || !table.tBodies.length) return;

    // Matris: hər sətir üçün oradakı .cell-score input-ları (sütun sırası ilə).
    function buildMatrix() {
      return Array.prototype.map.call(table.tBodies[0].rows, function (row) {
        return Array.prototype.slice.call(row.querySelectorAll("input.cell-score"));
      });
    }

    function locate(matrix, input) {
      for (var r = 0; r < matrix.length; r++) {
        var c = matrix[r].indexOf(input);
        if (c !== -1) return { r: r, c: c };
      }
      return null;
    }

    function caretAtEdge(input, side) {
      try {
        if (input.selectionStart === null) return true; // number inputs in some browsers
        return side === "left"
          ? input.selectionStart === 0 && input.selectionEnd === 0
          : input.selectionStart === input.value.length;
      } catch (e) {
        return true;
      }
    }

    wrap.addEventListener("keydown", function (event) {
      var input = event.target;
      if (!input.classList || !input.classList.contains("cell-score")) return;
      var key = event.key;
      if (key !== "ArrowUp" && key !== "ArrowDown" && key !== "ArrowLeft" && key !== "ArrowRight") return;
      if (key === "ArrowLeft" && !caretAtEdge(input, "left")) return;
      if (key === "ArrowRight" && !caretAtEdge(input, "right")) return;

      var matrix = buildMatrix();
      var pos = locate(matrix, input);
      if (!pos) return;

      var target = null;
      if (key === "ArrowUp") {
        for (var r = pos.r - 1; r >= 0 && !target; r--) target = matrix[r][pos.c] || null;
      } else if (key === "ArrowDown") {
        for (var r2 = pos.r + 1; r2 < matrix.length && !target; r2++) target = matrix[r2][pos.c] || null;
      } else if (key === "ArrowLeft") {
        target = matrix[pos.r][pos.c - 1] || null;
      } else {
        target = matrix[pos.r][pos.c + 1] || null;
      }
      if (target) {
        event.preventDefault();
        target.focus();
        try { target.select(); } catch (e) { /* ignore */ }
      }
    });
  });
})();
