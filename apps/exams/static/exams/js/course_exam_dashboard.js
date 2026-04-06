(function () {
  if (window._COURSE_EXAM_DASHBOARD_INIT) {
    return;
  }
  window._COURSE_EXAM_DASHBOARD_INIT = true;

  function init() {
    var configElement = document.getElementById("courseExamDashboardConfig");
    if (!configElement || !window.bootstrap) {
      return;
    }

    var editorModalElement = document.getElementById("courseExamEditorModal");
    var editorModalTitle = document.getElementById("courseExamEditorModalTitle");
    var editorModalBody = document.getElementById("courseExamEditorModalBody");
    var searchInput = document.getElementById("examSearchInput");
    var editorModal = editorModalElement ? window.bootstrap.Modal.getOrCreateInstance(editorModalElement) : null;
    var linkModalElement = document.getElementById("linkExamModal");
    var linkModal = linkModalElement ? window.bootstrap.Modal.getOrCreateInstance(linkModalElement) : null;
    var submitInFlight = false;
    var config = configElement.dataset;

    function loadingMarkup() {
      return '<div class="create-exam-modal-loading">' + (config.loadingText || "Yuklenir...") + "</div>";
    }

    function errorMarkup() {
      return '<div class="create-exam-modal-error">' + (config.loadErrorText || "Form yuklenmedi.") + "</div>";
    }

    function buildModalUrl(url) {
      var parsedUrl = new URL(url, window.location.origin);
      parsedUrl.searchParams.set("modal", "1");
      return parsedUrl.pathname + parsedUrl.search;
    }

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

      if (searchInputElement) {
        searchInputElement.addEventListener("input", function () {
          filterList(searchInputElement.value);
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

    function bindEditorForm() {
      if (!editorModalBody) {
        return;
      }

      var form = editorModalBody.querySelector("#createExamModalForm");
      var closeButton = editorModalBody.querySelector(".js-close-create-exam");
      if (closeButton) {
        closeButton.addEventListener("click", function () {
          editorModal.hide();
        });
      }
      if (!form) {
        return;
      }

      initExamTypePicker(form);
      initAccessToggle(form);
      var groupSelector = initSearchableSelect(form, {
        selectName: "allowed_groups",
        listSelector: "#createExamGroupsList",
        searchSelector: "#createExamGroupsSearch",
        counterSelector: "#createExamGroupsCount"
      });
      var userSelector = initSearchableSelect(form, {
        selectName: "allowed_users",
        listSelector: "#createExamUsersList",
        searchSelector: "#createExamUsersSearch",
        counterSelector: "#createExamUsersCount"
      });
      initGroupUserSelectionSync(form, groupSelector, userSelector);

      form.addEventListener("submit", function (event) {
        event.preventDefault();
        if (submitInFlight) {
          return;
        }

        submitInFlight = true;
        var submitButton = form.querySelector('button[type="submit"]');
        var originalSubmitText = submitButton ? submitButton.innerHTML : "";
        if (submitButton) {
          submitButton.disabled = true;
          submitButton.innerHTML = config.submittingText || "Yaddash saxlanilir...";
        }

        fetch(form.getAttribute("action"), {
          method: "POST",
          body: new FormData(form),
          headers: {
            "X-Requested-With": "XMLHttpRequest"
          }
        })
          .then(function (response) {
            var contentType = response.headers.get("content-type") || "";
            if (response.ok && contentType.indexOf("application/json") !== -1) {
              return response.json().then(function (data) {
                if (data.success) {
                  editorModal.hide();
                  window.location.href = config.reloadUrl || window.location.href;
                  return null;
                }

                if (data.html) {
                  editorModalBody.innerHTML = data.html;
                  bindEditorForm();
                }
                return null;
              });
            }

            if (contentType.indexOf("application/json") !== -1) {
              return response.json().then(function (data) {
                if (data.html) {
                  editorModalBody.innerHTML = data.html;
                  bindEditorForm();
                  return null;
                }
                editorModalBody.innerHTML = errorMarkup();
                return null;
              });
            }

            return response.text().then(function (html) {
              editorModalBody.innerHTML = html || errorMarkup();
              bindEditorForm();
            });
          })
          .catch(function () {
            editorModalBody.innerHTML = errorMarkup();
          })
          .finally(function () {
            submitInFlight = false;
            if (submitButton) {
              submitButton.disabled = false;
              submitButton.innerHTML = originalSubmitText;
            }
          });
      });
    }

    function openEditorModal(trigger) {
      if (!editorModal || !editorModalBody || !editorModalTitle || !trigger) {
        return;
      }

      if (linkModal) {
        linkModal.hide();
      }

      var targetUrl = trigger.getAttribute("data-url");
      if (!targetUrl) {
        return;
      }

      editorModalTitle.textContent = trigger.getAttribute("data-modal-title") || config.createTitle || "";
      editorModalBody.innerHTML = loadingMarkup();
      editorModal.show();

      fetch(buildModalUrl(targetUrl), {
        headers: {
          "X-Requested-With": "XMLHttpRequest"
        }
      })
        .then(function (response) {
          if (!response.ok) {
            throw new Error("modal load failed");
          }
          return response.text();
        })
        .then(function (html) {
          editorModalBody.innerHTML = html;
          bindEditorForm();
        })
        .catch(function () {
          editorModalBody.innerHTML = errorMarkup();
        });
    }

    function showError(message) {
      alert((config.errorPrefix || "") + (message || ""));
    }

    function postExamAction(url, examId) {
      return fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]')?.value || "",
          "X-Requested-With": "XMLHttpRequest"
        },
        body: JSON.stringify({ exam_id: examId })
      }).then(function (response) {
        return response.json();
      });
    }

    function unlinkExam(trigger) {
      var examId = trigger.getAttribute("data-exam-id");
      if (!examId || !config.unlinkUrl) {
        return;
      }

      var performUnlink = function () {
        return postExamAction(config.unlinkUrl, examId)
          .then(function (data) {
            if (data.success) {
              window.location.href = config.reloadUrl || window.location.href;
              return true;
            }
            showError(data.error);
            return false;
          })
          .catch(function () {
            showError("");
            return false;
          });
      };

      if (typeof window.openActionConfirmModal === "function") {
        window.openActionConfirmModal({
          title: trigger.textContent.trim() || config.unlinkTitle || "",
          message: config.unlinkConfirm || "",
          confirmLabel: trigger.textContent.trim() || config.unlinkTitle || "",
          confirmButtonClass: "btn btn-danger",
          onConfirm: performUnlink
        });
        return;
      }

      if (window.confirm(config.unlinkConfirm || "")) {
        performUnlink();
      }
    }

    function linkExam(trigger) {
      var examId = trigger.getAttribute("data-exam-id");
      if (!examId || !config.linkUrl) {
        return;
      }

      postExamAction(config.linkUrl, examId)
        .then(function (data) {
          if (data.success) {
            window.location.href = config.reloadUrl || window.location.href;
            return;
          }
          showError(data.error);
        })
        .catch(function () {
          showError("");
        });
    }

    if (searchInput) {
      searchInput.addEventListener("input", function () {
        var query = (searchInput.value || "").toLowerCase();
        document.querySelectorAll(".exam-search-item").forEach(function (item) {
          item.style.display = item.textContent.toLowerCase().indexOf(query) !== -1 ? "" : "none";
        });
      });
    }

    document.addEventListener("click", function (event) {
      var editorTrigger = event.target.closest(".js-open-course-exam-editor");
      if (editorTrigger) {
        event.preventDefault();
        openEditorModal(editorTrigger);
        return;
      }

      var linkTrigger = event.target.closest(".js-link-exam");
      if (linkTrigger) {
        event.preventDefault();
        linkExam(linkTrigger);
        return;
      }

      var unlinkTrigger = event.target.closest(".js-unlink-exam");
      if (unlinkTrigger) {
        event.preventDefault();
        unlinkExam(unlinkTrigger);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
