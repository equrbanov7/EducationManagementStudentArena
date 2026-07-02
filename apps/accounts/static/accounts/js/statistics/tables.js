(function (window, document) {
  "use strict";

  var ns = window.EMSStatistics || (window.EMSStatistics = {});

  function initSorting() {
    document.querySelectorAll(".stats-sortable-table").forEach(function (table) {
      var headers = table.querySelectorAll("th.stats-sortable");
      headers.forEach(function (th, colIndex) {
        th.addEventListener("click", function () {
          var isAsc = th.classList.contains("sort-asc");
          headers.forEach(function (header) {
            header.classList.remove("sort-asc", "sort-desc");
          });
          th.classList.add(isAsc ? "sort-desc" : "sort-asc");

          var tbody = table.querySelector("tbody");
          var rows = Array.from(tbody.querySelectorAll("tr"));
          var direction = isAsc ? -1 : 1;

          rows.sort(function (rowA, rowB) {
            var aValue = rowA.cells[colIndex] ? rowA.cells[colIndex].textContent.trim() : "";
            var bValue = rowB.cells[colIndex] ? rowB.cells[colIndex].textContent.trim() : "";
            var aNum = parseFloat(aValue.replace(/[^0-9.\-]/g, ""));
            var bNum = parseFloat(bValue.replace(/[^0-9.\-]/g, ""));

            if (!isNaN(aNum) && !isNaN(bNum)) {
              return (aNum - bNum) * direction;
            }
            return aValue.localeCompare(bValue) * direction;
          });

          rows.forEach(function (row) {
            tbody.appendChild(row);
          });
        });
      });
    });
  }

  function bindTableSearch(inputId, tableId) {
    var input = document.getElementById(inputId);
    var table = document.getElementById(tableId);
    if (!input || !table) {
      return;
    }

    input.addEventListener("input", function () {
      var query = input.value.toLowerCase().trim();
      table.querySelectorAll("tbody tr").forEach(function (row) {
        row.style.display = row.textContent.toLowerCase().indexOf(query) !== -1 ? "" : "none";
      });
    });
  }

  function initSearch() {
    bindTableSearch("statsTableSearchOrg", "statsOrgTable");
    bindTableSearch("statsTableSearchTeacher", "statsTeacherTable");
    bindTableSearch("statsTableSearchCourse", "statsCourseTable");
    bindTableSearch("statsTableSearchGroup", "statsGroupTable");
    bindTableSearch("statsTableSearchTeacherCourse", "statsTeacherCourseTable");
  }

  function init() {
    initSorting();
    initSearch();
  }

  ns.tables = {
    init: init
  };
})(window, document);
