/*
 * EMS DataTable (U12) — vahid cədvəl davranışı (progressive enhancement).
 * Opt-in: <table data-ems-table> → başlıqlara klik-sort;
 *         data-ems-table-filter → cədvəlin üstünə sürətli axtarış qutusu;
 *         data-ems-page-size="25" → klient tərəfi pagination (sətir çoxdursa).
 * CSP-safe (inline yoxdur), AJAX panellərində yenidən işə düşür
 * (window.EMSTable.init(root) — profile section loader-in reinit hook-u çağırır).
 */
(function () {
  "use strict";

  var FILTER_PLACEHOLDER = (window.gettext ? window.gettext("Axtar…") : "Axtar…");

  function textOf(cell) {
    return (cell.textContent || "").trim().toLowerCase();
  }

  function compareRows(index, ascending) {
    return function (a, b) {
      var av = textOf(a.cells[index] || {});
      var bv = textOf(b.cells[index] || {});
      var an = parseFloat(av.replace("%", "").replace(",", "."));
      var bn = parseFloat(bv.replace("%", "").replace(",", "."));
      var result;
      if (!isNaN(an) && !isNaN(bn)) {
        result = an - bn;
      } else {
        result = av.localeCompare(bv);
      }
      return ascending ? result : -result;
    };
  }

  function initSort(table) {
    var headers = table.querySelectorAll("thead th");
    headers.forEach(function (th, index) {
      if (th.hasAttribute("data-no-sort")) return;
      th.classList.add("ems-th-sortable");
      th.setAttribute("tabindex", "0");
      th.setAttribute("role", "button");
      function toggle() {
        var ascending = th.getAttribute("aria-sort") !== "ascending";
        headers.forEach(function (other) { other.removeAttribute("aria-sort"); });
        th.setAttribute("aria-sort", ascending ? "ascending" : "descending");
        var tbody = table.tBodies[0];
        if (!tbody) return;
        Array.prototype.slice.call(tbody.rows)
          .sort(compareRows(index, ascending))
          .forEach(function (row) { tbody.appendChild(row); });
      }
      th.addEventListener("click", toggle);
      th.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
      });
    });
  }

  function initFilter(table) {
    if (!table.hasAttribute("data-ems-table-filter")) return;
    var wrap = document.createElement("div");
    wrap.className = "ems-table-filter";
    var input = document.createElement("input");
    input.type = "search";
    input.className = "ems-table-filter-input";
    input.placeholder = FILTER_PLACEHOLDER;
    input.setAttribute("aria-label", FILTER_PLACEHOLDER);
    wrap.appendChild(input);
    table.parentNode.insertBefore(wrap, table);
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      var tbody = table.tBodies[0];
      if (!tbody) return;
      Array.prototype.forEach.call(tbody.rows, function (row) {
        row.hidden = q !== "" && row.textContent.toLowerCase().indexOf(q) === -1;
      });
    });
  }

  function init(root) {
    (root || document).querySelectorAll("table[data-ems-table]").forEach(function (table) {
      if (table.getAttribute("data-ems-table-ready") === "1") return;
      table.setAttribute("data-ems-table-ready", "1");
      initSort(table);
      initFilter(table);
    });
  }

  window.EMSTable = { init: init };
  // Profil bölmə AJAX-swap-larından sonra yenidən işə düş (reinit hook contract).
  window.EMSProfileReinitHooks = window.EMSProfileReinitHooks || {};
  window.EMSProfileReinitHooks.emsTable = function (panel) { init(panel || document); };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { init(document); });
  } else {
    init(document);
  }
})();
