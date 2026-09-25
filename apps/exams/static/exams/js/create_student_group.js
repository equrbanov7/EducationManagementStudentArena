/*
 * create_student_group.js
 * Source template: apps/exams/templates/exams/teacher/create_student_group.html
 *
 * * Tələbə / əlavə müəllim siyahıları (`[data-csg-checklist]`) gizli
 *   `<select multiple>`-dən checkbox siyahısı kimi qurulur (əvvəllər
 *   `partials/_searchable_multi_select.html`-in inline nonce skripti idi).
 * * Namizəd variantları səhifə ilə RENDER OLUNMUR — `#createGroupForm
 *   [data-candidates-url]` doludursa səhifə açılanda oradan (JSON: students /
 *   primary_teacher / assigned_teachers — serverdə eyni widget) çəkilir
 *   (perf auditi 2026-09-13 F-10: tam səhifə bütün tələbə `<option>`-larını
 *   render edirdi). URL boşdursa (POST xətası re-render-i) mövcud
 *   `<option>`-larla işlənir — seçim qorunur.
 * * Əsas müəllim `<select>`-i üçün axtarış: `#primaryTeacherSearch
 *   [data-teacher-select-id]`.
 */
(function () {
  "use strict";

  // Tolerant axtarış (EMSSearch: az↔en hərfləri, «234king» → «234 K ing»).
  // «İ».toLowerCase() = «i» + U+0307 (birləşən nöqtə) — mətndən atılır.
  function searchMatcher(query) {
    var q = String(query || "").trim();
    var m = window.EMSSearch ? window.EMSSearch.matcher(q) : null;
    var low = q.toLowerCase();
    return function (text) {
      var t = String(text || "").replace(/\u0307/g, "");
      return m ? m(t) : !low || t.toLowerCase().indexOf(low) !== -1;
    };
  }

  var form = document.getElementById("createGroupForm");
  if (!form) return;

  var i18nEl = document.getElementById("csg-i18n");
  var I18N = i18nEl ? JSON.parse(i18nEl.textContent) : {};

  function createChecklist(root) {
    var hiddenSelect = document.getElementById(root.getAttribute("data-select-id") || "");
    var container = root.querySelector("[data-csg-list]");
    var searchInput = root.querySelector("[data-csg-search]");
    var counterSpan = root.querySelector("[data-csg-count]");
    var showGroupNumber = root.getAttribute("data-student-meta") === "1";
    if (!hiddenSelect || !container) return null;

    function updateCounter() {
      if (counterSpan) counterSpan.textContent = hiddenSelect.selectedOptions.length;
    }

    function optionGroupNumber(option) {
      return showGroupNumber ? (option.getAttribute("data-student-group-number") || "").trim() : "";
    }

    function optionSearchText(option) {
      return [option.text || "", option.getAttribute("data-search-text") || "", optionGroupNumber(option)]
        .join(" ")
        .toLowerCase();
    }

    function build() {
      container.innerHTML = "";
      var options = Array.from(hiddenSelect.options);
      if (options.length === 0) {
        var empty = document.createElement("div");
        empty.className = "loading-text";
        empty.textContent = I18N.noDataFound || "";
        container.appendChild(empty);
        updateCounter();
        return;
      }

      options.forEach(function (option) {
        var row = document.createElement("div");
        row.className = "list-item-row";
        row.setAttribute("data-search", optionSearchText(option));

        var checkboxId = "cb_" + hiddenSelect.id + "_" + option.value;
        var checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.id = checkboxId;
        checkbox.className = "custom-item-checkbox";
        checkbox.value = option.value;
        checkbox.checked = option.selected;

        var label = document.createElement("label");
        label.htmlFor = checkboxId;
        label.className = "custom-item-label";

        var nameSpan = document.createElement("span");
        nameSpan.className = "custom-item-label__name";
        nameSpan.textContent = option.text || "";
        label.appendChild(nameSpan);

        var groupNumber = optionGroupNumber(option);
        if (groupNumber) {
          var badge = document.createElement("span");
          badge.className = "custom-item-label__group";
          badge.textContent = (I18N.studentRegisteredGroupNumber || "") + ": " + groupNumber;
          label.appendChild(badge);
        }

        checkbox.addEventListener("change", function () {
          option.selected = this.checked;
          updateCounter();
        });
        row.addEventListener("click", function (e) {
          var clickedLabel = e.target.closest && e.target.closest("label");
          if (e.target !== checkbox && !clickedLabel) {
            checkbox.checked = !checkbox.checked;
            checkbox.dispatchEvent(new Event("change"));
          }
        });

        row.appendChild(checkbox);
        row.appendChild(label);
        container.appendChild(row);
      });
      updateCounter();
    }

    if (searchInput) {
      searchInput.addEventListener("input", function () {
        var match = searchMatcher(this.value);
        container.querySelectorAll(".list-item-row").forEach(function (row) {
          var text = row.getAttribute("data-search") || "";
          row.hidden = !match(text); // bootstrap reboot: [hidden]{display:none!important}
        });
      });
    }

    return { build: build };
  }

  var checklists = Array.from(form.querySelectorAll("[data-csg-checklist]")).map(createChecklist).filter(Boolean);

  function injectOptions(select, markup) {
    if (!select || !markup) return;
    var holder = document.createElement("div");
    holder.innerHTML = markup;
    var parsed = holder.querySelector("select");
    if (parsed) select.innerHTML = parsed.innerHTML;
  }

  function buildAll() {
    checklists.forEach(function (checklist) {
      checklist.build();
    });
  }

  function loadCandidates() {
    var candidatesUrl = form.getAttribute("data-candidates-url") || "";
    if (!candidatesUrl || typeof window.fetch !== "function") {
      buildAll();
      return;
    }
    var studentsSelect = document.getElementById(form.getAttribute("data-students-select-id") || "");
    var primarySelect = document.getElementById(form.getAttribute("data-primary-teacher-select-id") || "");
    var assignedSelect = document.getElementById(form.getAttribute("data-assigned-teachers-select-id") || "");
    var primaryValue = primarySelect ? primarySelect.value : "";

    window
      .fetch(candidatesUrl, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" }
      })
      .then(function (response) {
        if (!response.ok) throw new Error("candidates_unavailable");
        return response.json();
      })
      .then(function (data) {
        injectOptions(studentsSelect, data.students);
        injectOptions(primarySelect, data.primary_teacher);
        injectOptions(assignedSelect, data.assigned_teachers);
        if (primarySelect && primaryValue) primarySelect.value = primaryValue;
      })
      .catch(function () {
        /* siyahılar boş qalır — «Məlumat tapılmadı» göstərilir */
      })
      .then(buildAll);
  }

  // Əsas müəllim `<select>`-inin axtarışı.
  var searchInput = document.getElementById("primaryTeacherSearch");
  var teacherSelect = searchInput ? document.getElementById(searchInput.dataset.teacherSelectId || "") : null;
  if (searchInput && teacherSelect) {
    searchInput.addEventListener("input", function () {
      var match = searchMatcher(this.value);
      var options = Array.from(teacherSelect.options);
      options.forEach(function (option) {
        option.hidden = !match(option.text || "");
      });
      var selectedVisible = options.find(function (option) {
        return option.selected && !option.hidden;
      });
      if (!selectedVisible) {
        var firstVisible = options.find(function (option) {
          return !option.hidden;
        });
        if (firstVisible) firstVisible.selected = true;
      }
    });
  }

  loadCandidates();
})();
