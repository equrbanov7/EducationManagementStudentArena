/* Searchable checkbox-list controller used by the profile group modal. */
(function (ns, document) {
  "use strict";

  function initChecklist(ctx, root) {
    // Sahənin ÖZ select-i (`name` daşıyır); ixtisas süzgəci select-i `name`-sizdir.
    var hiddenSelect = root.querySelector("select[name]");
    var searchInput = root.querySelector(".js-select-search");
    var listContainer = root.querySelector(".js-select-list");
    var counterEl = root.querySelector(".js-selected-count");
    var selectAllBtn = root.querySelector(".js-select-all");
    var clearSelectedBtn = root.querySelector(".js-clear-selected");

    if (!hiddenSelect || !listContainer) {
      return null;
    }
    var showStudentGroupNumber = root.getAttribute("data-show-student-group-number") === "1";
    // İxtisasa görə süzgəc (yalnız tələbə siyahısında) — variantların
    // `data-specialty` atributundan qurulur (sahib, 2026-09-07).
    var specialtySelect = root.querySelector(".js-select-specialty");
    var specialtyBuilt = "";

    function currentSpecialty() {
      return specialtySelect ? String(specialtySelect.value || "") : "";
    }

    function buildSpecialtyOptions() {
      if (!specialtySelect) {
        return;
      }
      var values = {};
      Array.from(hiddenSelect.options || []).forEach(function (option) {
        var name = option.getAttribute("data-specialty") || "";
        if (name) {
          values[name] = (values[name] || 0) + 1;
        }
      });
      var keys = Object.keys(values).sort();
      var signature = keys.join("|");
      if (signature === specialtyBuilt) {
        return;
      }
      specialtyBuilt = signature;
      var previous = specialtySelect.value;
      var allLabel = specialtySelect.getAttribute("data-all-label") || "";
      specialtySelect.innerHTML = "";
      var allOption = document.createElement("option");
      allOption.value = "";
      allOption.textContent = allLabel;
      specialtySelect.appendChild(allOption);
      keys.forEach(function (key) {
        var opt = document.createElement("option");
        opt.value = key;
        opt.textContent = key + " (" + values[key] + ")";
        specialtySelect.appendChild(opt);
      });
      specialtySelect.value = keys.indexOf(previous) !== -1 ? previous : "";
      specialtySelect.hidden = !keys.length;
    }

    function normalize(text) {
      return String(text || "").toLowerCase();
    }

    function currentFilterValue() {
      return normalize(searchInput ? searchInput.value : "");
    }

    function optionGroupLabels(option) {
      if (!showStudentGroupNumber) {
        return "";
      }
      return String(option.getAttribute("data-student-group-number") || "").trim();
    }

    function optionSearchText(option) {
      return [
        option.textContent || "",
        option.getAttribute("data-search-text") || "",
        optionGroupLabels(option),
        showStudentGroupNumber ? option.getAttribute("data-user-group-labels") || "" : ""
      ].join(" ");
    }

    function optionMatchesFilter(option, filterValue) {
      var specialty = currentSpecialty();
      if (specialty && (option.getAttribute("data-specialty") || "") !== specialty) {
        return false;
      }
      if (!filterValue) {
        return true;
      }
      return normalize(optionSearchText(option)).indexOf(filterValue) !== -1;
    }

    function updateCounter() {
      if (!counterEl) {
        return;
      }
      counterEl.textContent = String(hiddenSelect.selectedOptions.length);
    }

    function render() {
      buildSpecialtyOptions();
      var filterValue = currentFilterValue();
      var options = Array.from(hiddenSelect.options || []);
      listContainer.innerHTML = "";

      var visibleCount = 0;
      options.forEach(function (option) {
        if (!optionMatchesFilter(option, filterValue)) {
          return;
        }
        visibleCount += 1;

        var row = document.createElement("label");
        row.className = "group-checklist__row";
        row.setAttribute("data-option-value", String(option.value));

        var checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = option.selected;

        var contentNode = document.createElement("span");
        contentNode.className = "group-checklist__content";

        var textNode = document.createElement("span");
        textNode.className = "group-checklist__name";
        textNode.textContent = option.textContent || "";
        contentNode.appendChild(textNode);

        var groupLabels = optionGroupLabels(option);
        if (groupLabels) {
          var groupBadge = document.createElement("span");
          groupBadge.className = "group-checklist__badge";
          groupBadge.textContent = ctx.studentGroupLabel + ": " + groupLabels;
          contentNode.appendChild(groupBadge);
        }
        // İxtisas şifri / adı + akademik qrup — seçim zamanı kimin kim olduğu görünsün.
        if (showStudentGroupNumber) {
          var specialtyText = [
            option.getAttribute("data-specialty-code") || "",
            option.getAttribute("data-specialty") || "",
            option.getAttribute("data-academic-group") || ""
          ].filter(Boolean).join(" · ");
          if (specialtyText) {
            var specialtyBadge = document.createElement("span");
            specialtyBadge.className = "group-checklist__badge group-checklist__badge--specialty";
            specialtyBadge.textContent = specialtyText;
            contentNode.appendChild(specialtyBadge);
          }
        }

        checkbox.addEventListener("change", function () {
          option.selected = checkbox.checked;
          updateCounter();
        });

        row.addEventListener("click", function (event) {
          if (event.target === checkbox) {
            return;
          }
          event.preventDefault();
          checkbox.checked = !checkbox.checked;
          option.selected = checkbox.checked;
          updateCounter();
        });

        row.appendChild(checkbox);
        row.appendChild(contentNode);
        listContainer.appendChild(row);
      });

      if (!visibleCount) {
        listContainer.innerHTML = '<div class="group-checklist__empty">' + ctx.searchNoResultsLabel + "</div>";
      }

      updateCounter();
    }

    function selectVisible() {
      var filterValue = currentFilterValue();
      Array.from(hiddenSelect.options || []).forEach(function (option) {
        if (optionMatchesFilter(option, filterValue)) {
          option.selected = true;
        }
      });
      render();
    }

    function clearAllSelected() {
      Array.from(hiddenSelect.options || []).forEach(function (option) {
        option.selected = false;
      });
      render();
    }

    function setSelectedValues(values) {
      var normalizedValues = new Set((values || []).map(function (item) {
        return String(item);
      }));
      Array.from(hiddenSelect.options || []).forEach(function (option) {
        option.selected = normalizedValues.has(String(option.value));
      });
      render();
    }

    function resetSearch() {
      if (searchInput) {
        searchInput.value = "";
      }
      if (specialtySelect) {
        specialtySelect.value = "";
      }
      render();
    }

    if (searchInput) {
      searchInput.addEventListener("input", render);
    }
    if (specialtySelect) {
      specialtySelect.addEventListener("change", render);
    }

    if (selectAllBtn) {
      selectAllBtn.addEventListener("click", function () {
        selectVisible();
      });
    }

    if (clearSelectedBtn) {
      clearSelectedBtn.addEventListener("click", function () {
        clearAllSelected();
      });
    }

    render();

    return {
      select: hiddenSelect,
      setSelectedValues: setSelectedValues,
      resetSearch: resetSearch,
      refresh: render
    };
  }

  ns.checklist = {
    initChecklist: initChecklist
  };
})(window.EMSProfileGroupModal = window.EMSProfileGroupModal || {}, document);
