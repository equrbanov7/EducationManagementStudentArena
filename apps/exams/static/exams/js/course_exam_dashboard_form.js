/* course_exam_dashboard_form.js — kurs imtahanı redaktor modalının FORMA
 * köməkçiləri (2026-09-21 bölgüsü, modul ölçü büdcəsi ≤ 550 sətir):
 *   • initSearchableSelect  — gizli <select multiple> + axtarışlı siyahı (lazy axtarış)
 *   • initGroupUserSelectionSync — qrup seçimi → tələbə seçimi sinxronu
 *   • initAccessToggle      — is_public → giriş məhdudiyyəti bloku
 *   • initExamTypePicker    — imtahan növü pilləri + paint mövcudluğu
 * Hamısı saf `form`-parametrli funksiyalardır (modal vəziyyətindən asılı deyil).
 * `course_exam_dashboard.js` onları `window.EMSCourseExamDashboard.form`-dan
 * `bindEditorForm()` anında (fetch-dən sonra) oxuyur — yükləmə sırası vacib deyil,
 * amma hər iki fayl birlikdə yüklənməlidir (_exam_modals.html).
 */
(function () {
  var namespace = (window.EMSCourseExamDashboard = window.EMSCourseExamDashboard || {});

  function getHiddenSelect(form, selectName) {
    return form.querySelector('select[name="' + selectName + '"]');
  }

  function initSearchableSelect(form, options) {
    if (!form) {
      return null;
    }

    var hiddenSelect = getHiddenSelect(form, options.selectName);
    var listContainer = form.querySelector(options.listSelector);
    var searchInputElement = form.querySelector(options.searchSelector);
    var counterElement = form.querySelector(options.counterSelector);
    if (!hiddenSelect || !listContainer) {
      return null;
    }

    var selectionChangeHandlers = [];
    var itemToggleHandlers = [];

    function getSelectedValues() {
      return Array.from(hiddenSelect.selectedOptions).map(function (option) {
        return String(option.value);
      });
    }

    function setValueSelected(value, shouldSelect, source) {
      var normalizedValue = String(value);
      Array.from(hiddenSelect.options).forEach(function (option) {
        if (String(option.value) === normalizedValue) {
          option.selected = !!shouldSelect;
        }
      });

      renderList();
      selectionChangeHandlers.forEach(function (handler) {
        handler(getSelectedValues(), { source: source || "programmatic", value: normalizedValue, isSelected: !!shouldSelect });
      });
      itemToggleHandlers.forEach(function (handler) {
        handler({ source: source || "programmatic", value: normalizedValue, isSelected: !!shouldSelect });
      });
    }

    function updateCounter() {
      if (counterElement) {
        counterElement.textContent = String(hiddenSelect.selectedOptions.length);
      }
    }

    function renderList() {
      var optionsList = Array.from(hiddenSelect.options);
      listContainer.innerHTML = "";

      if (!optionsList.length) {
        listContainer.innerHTML = '<div class="create-exam-list-empty">Melumat tapilmadi.</div>';
        updateCounter();
        return;
      }

      optionsList.forEach(function (option) {
        var row = document.createElement("div");
        row.className = "create-exam-list-item";
        row.setAttribute("data-search", (option.text || "").toLowerCase());

        var checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "create-exam-item-checkbox";
        checkbox.value = option.value;
        checkbox.checked = option.selected;

        var label = document.createElement("label");
        label.className = "create-exam-item-label";
        label.textContent = option.text;

        checkbox.addEventListener("change", function () {
          option.selected = checkbox.checked;
          updateCounter();
          selectionChangeHandlers.forEach(function (handler) {
            handler(getSelectedValues(), { source: "user", value: String(option.value), isSelected: checkbox.checked });
          });
          itemToggleHandlers.forEach(function (handler) {
            handler({ source: "user", value: String(option.value), isSelected: checkbox.checked });
          });
        });

        row.addEventListener("click", function (event) {
          if (event.target === checkbox) {
            return;
          }
          checkbox.checked = !checkbox.checked;
          checkbox.dispatchEvent(new Event("change"));
        });

        row.appendChild(checkbox);
        row.appendChild(label);
        listContainer.appendChild(row);
      });

      updateCounter();
    }

    function filterList(query) {
      var normalizedQuery = (query || "").toLowerCase();
      listContainer.querySelectorAll(".create-exam-list-item").forEach(function (row) {
        var haystack = row.getAttribute("data-search") || "";
        row.style.display = haystack.indexOf(normalizedQuery) !== -1 ? "flex" : "none";
      });
    }

    // Lazy: server yalnız seçili variantları render edir; qalanı axtarış
    // endpoint-indən (data-search-url) debounce ilə gətirilir.
    var lazyContainer = form.querySelector('[data-target-select-name="' + options.selectName + '"]');
    var lazySearchUrl = lazyContainer ? lazyContainer.getAttribute("data-search-url") : "";
    var lazyDebounce = null;
    var lazySeq = 0;

    function mergeResults(results) {
      var existing = {};
      Array.from(hiddenSelect.options).forEach(function (o) {
        existing[String(o.value)] = true;
      });
      (results || []).forEach(function (item) {
        if (!existing[String(item.id)]) {
          var opt = document.createElement("option");
          opt.value = item.id;
          opt.text = item.text;
          hiddenSelect.appendChild(opt);
        }
      });
    }

    function lazyFetch(query) {
      if (!lazySearchUrl) {
        renderList();
        filterList(query);
        return;
      }
      var seq = ++lazySeq;
      var url = lazySearchUrl + (lazySearchUrl.indexOf("?") === -1 ? "?" : "&") + "q=" + encodeURIComponent(query || "");
      fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then(function (r) { return r.ok ? r.json() : { results: [] }; })
        .then(function (data) {
          if (seq !== lazySeq) {
            return;
          }
          mergeResults((data && data.results) || []);
          renderList();
          filterList(query);
        })
        .catch(function () {});
    }

    if (searchInputElement) {
      searchInputElement.addEventListener("input", function () {
        var q = searchInputElement.value.trim();
        if (lazySearchUrl) {
          if (lazyDebounce) {
            clearTimeout(lazyDebounce);
          }
          lazyDebounce = setTimeout(function () {
            lazyFetch(q);
          }, 300);
        } else {
          filterList(q);
        }
      });
      searchInputElement.addEventListener("focus", function () {
        if (lazySearchUrl && hiddenSelect.options.length <= hiddenSelect.selectedOptions.length) {
          lazyFetch(searchInputElement.value.trim());
        }
      });
    }

    renderList();
    if (searchInputElement && searchInputElement.value) {
      filterList(searchInputElement.value);
    }

    return {
      getSelectedValues: getSelectedValues,
      setValueSelected: setValueSelected,
      onSelectionChange: function (handler) {
        if (typeof handler === "function") {
          selectionChangeHandlers.push(handler);
        }
      },
      onItemToggle: function (handler) {
        if (typeof handler === "function") {
          itemToggleHandlers.push(handler);
        }
      }
    };
  }

  function parseGroupStudentMap(form) {
    if (!form) {
      return {};
    }

    var mapScript = form.querySelector("#createExamGroupStudentMap");
    if (!mapScript || !mapScript.textContent) {
      return {};
    }

    try {
      var parsedMap = JSON.parse(mapScript.textContent);
      return parsedMap && typeof parsedMap === "object" ? parsedMap : {};
    } catch (error) {
      return {};
    }
  }

  function initGroupUserSelectionSync(form, groupSelector, userSelector) {
    if (!form || !groupSelector || !userSelector) {
      return;
    }

    var groupStudentMap = parseGroupStudentMap(form);
    if (!Object.keys(groupStudentMap).length) {
      return;
    }

    var manuallyDeselectedUserIds = new Set();

    function getAutoSelectedUserIds() {
      var selectedGroupIds = groupSelector.getSelectedValues();
      var userIds = new Set();

      selectedGroupIds.forEach(function (groupId) {
        var mappedUserIds = groupStudentMap[String(groupId)] || [];
        mappedUserIds.forEach(function (userId) {
          userIds.add(String(userId));
        });
      });

      return userIds;
    }

    function syncUsersFromSelectedGroups() {
      var autoSelectedUserIds = getAutoSelectedUserIds();

      Array.from(manuallyDeselectedUserIds).forEach(function (userId) {
        if (!autoSelectedUserIds.has(userId)) {
          manuallyDeselectedUserIds.delete(userId);
        }
      });

      autoSelectedUserIds.forEach(function (userId) {
        if (!manuallyDeselectedUserIds.has(userId)) {
          userSelector.setValueSelected(userId, true, "group-sync");
        }
      });
    }

    groupSelector.onSelectionChange(function () {
      syncUsersFromSelectedGroups();
    });

    userSelector.onItemToggle(function (meta) {
      if (!meta || meta.source !== "user") {
        return;
      }

      var userId = String(meta.value || "");
      if (!userId || !getAutoSelectedUserIds().has(userId)) {
        return;
      }

      if (meta.isSelected) {
        manuallyDeselectedUserIds.delete(userId);
      } else {
        manuallyDeselectedUserIds.add(userId);
      }
    });

    syncUsersFromSelectedGroups();
  }

  function initAccessToggle(form) {
    var isPublicCheckbox = form.querySelector('input[name="is_public"]');
    var accessBlock = form.querySelector("#createExamAccessRestrictions");
    if (!isPublicCheckbox || !accessBlock) {
      return;
    }

    function syncAccessBlock() {
      accessBlock.classList.toggle("is-hidden", isPublicCheckbox.checked);
    }

    syncAccessBlock();
    isPublicCheckbox.addEventListener("change", syncAccessBlock);
  }

  function initExamTypePicker(form) {
    var nativeSelect = form.querySelector('select[name="exam_type"]');
    var picker = form.querySelector("[data-create-exam-type-picker]");
    if (!nativeSelect || !picker) {
      return;
    }

    var typeOptions = picker.querySelectorAll(".js-create-exam-type-option");
    var paintCheckbox = form.querySelector('input[name="enable_paint"]');
    var paintLabel = paintCheckbox ? paintCheckbox.closest(".modal-check-label--paint") : null;

    function syncPaintAvailability(examType) {
      if (!paintCheckbox) {
        return;
      }

      var isWritten = examType === "written";
      if (!isWritten) {
        paintCheckbox.checked = false;
      }
      paintCheckbox.disabled = !isWritten;

      if (paintLabel) {
        paintLabel.classList.toggle("is-disabled", !isWritten);
      }
    }

    function syncPickerFromSelect() {
      var selectedType = nativeSelect.value || "test";
      typeOptions.forEach(function (option) {
        option.checked = option.value === selectedType;
      });
      syncPaintAvailability(selectedType);
    }

    typeOptions.forEach(function (option) {
      option.addEventListener("change", function () {
        if (!option.checked) {
          return;
        }

        nativeSelect.value = option.value;
        syncPaintAvailability(option.value);
        nativeSelect.dispatchEvent(new Event("change", { bubbles: true }));
      });
    });

    nativeSelect.addEventListener("change", syncPickerFromSelect);
    syncPickerFromSelect();
  }

  namespace.form = {
    initSearchableSelect: initSearchableSelect,
    initGroupUserSelectionSync: initGroupUserSelectionSync,
    initAccessToggle: initAccessToggle,
    initExamTypePicker: initExamTypePicker
  };
})();
