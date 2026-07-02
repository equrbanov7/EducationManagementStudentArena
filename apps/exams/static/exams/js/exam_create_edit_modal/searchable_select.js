/* Searchable group/user selectors and group-to-student sync. */
(function (ns, document) {
    "use strict";

    function parseGroupStudentMap(form) {
        if (!form) {
            return {};
        }

        var mapScript = form.querySelector("#createExamGroupStudentMap");
        if (!mapScript || !mapScript.textContent) {
            return {};
        }

        try {
            var parsed = JSON.parse(mapScript.textContent);
            if (!parsed || typeof parsed !== "object") {
                return {};
            }
            return parsed;
        } catch (error) {
            return {};
        }
    }

    function initSearchableSelect(form, config) {
        if (!form || !config) {
            return null;
        }

        var hiddenSelect = form.querySelector('select[name="' + config.selectName + '"]');
        var listContainer = form.querySelector(config.listSelector);
        var searchInput = form.querySelector(config.searchSelector);
        var counter = form.querySelector(config.counterSelector);
        var optionMap = Object.create(null);
        var checkboxMap = Object.create(null);
        var selectionHandlers = [];
        var toggleHandlers = [];

        if (!hiddenSelect || !listContainer) {
            return null;
        }

        function updateCounter() {
            if (counter) {
                counter.textContent = String(hiddenSelect.selectedOptions.length);
            }
        }

        function getSelectedValues() {
            return Array.from(hiddenSelect.selectedOptions || []).map(function (option) {
                return String(option.value);
            });
        }

        function notifySelection(meta) {
            selectionHandlers.forEach(function (handler) {
                handler(meta || {});
            });
        }

        function notifyToggle(meta) {
            toggleHandlers.forEach(function (handler) {
                handler(meta || {});
            });
        }

        function setValueSelected(value, isSelected, source) {
            var normalizedValue = String(value);
            var option = optionMap[normalizedValue];
            if (!option || option.selected === isSelected) {
                return false;
            }

            option.selected = isSelected;

            var checkbox = checkboxMap[normalizedValue];
            if (checkbox) {
                checkbox.checked = isSelected;
            }

            updateCounter();

            var meta = {
                value: normalizedValue,
                isSelected: isSelected,
                source: source || "programmatic"
            };

            notifyToggle(meta);
            notifySelection(meta);
            return true;
        }

        function renderList() {
            var options = Array.from(hiddenSelect.options || []);
            listContainer.innerHTML = "";
            optionMap = Object.create(null);
            checkboxMap = Object.create(null);

            options.forEach(function (option) {
                optionMap[String(option.value)] = option;

                var row = document.createElement("div");
                row.className = "create-exam-list-item";
                row.setAttribute("data-search", (option.textContent || "").toLowerCase());

                var checkboxId = "exam_modal_" + config.selectName + "_" + option.value;

                row.innerHTML =
                    '<input type="checkbox" class="create-exam-item-checkbox" id="' +
                    checkboxId +
                    '"' +
                    (option.selected ? " checked" : "") +
                    ">" +
                    '<label class="create-exam-item-label" for="' +
                    checkboxId +
                    '"></label>';

                var checkbox = row.querySelector(".create-exam-item-checkbox");
                var label = row.querySelector(".create-exam-item-label");

                if (label) {
                    label.textContent = option.textContent || "";
                }

                if (checkbox) {
                    checkboxMap[String(option.value)] = checkbox;
                    checkbox.addEventListener("change", function () {
                        setValueSelected(option.value, checkbox.checked, "user");
                    });
                }

                row.addEventListener("click", function (event) {
                    if (!checkbox) {
                        return;
                    }
                    if (event.target === checkbox || event.target === label) {
                        return;
                    }

                    var nextChecked = !checkbox.checked;
                    checkbox.checked = nextChecked;
                    setValueSelected(option.value, nextChecked, "user");
                });

                listContainer.appendChild(row);
            });

            updateCounter();
        }

        function filterList(query) {
            var normalizedQuery = (query || "").toLowerCase();
            var rows = listContainer.querySelectorAll(".create-exam-list-item");

            rows.forEach(function (row) {
                var haystack = row.getAttribute("data-search") || "";
                row.style.display = haystack.indexOf(normalizedQuery) !== -1 ? "flex" : "none";
            });
        }

        if (searchInput) {
            searchInput.addEventListener("input", function () {
                filterList(searchInput.value);
            });
        }

        renderList();
        if (searchInput && searchInput.value) {
            filterList(searchInput.value);
        }

        return {
            getSelectedValues: getSelectedValues,
            setValueSelected: setValueSelected,
            onSelectionChange: function (handler) {
                if (typeof handler === "function") {
                    selectionHandlers.push(handler);
                }
            },
            onItemToggle: function (handler) {
                if (typeof handler === "function") {
                    toggleHandlers.push(handler);
                }
            }
        };
    }

    function initGroupUserSync(form, groupSelector, userSelector) {
        if (!form || !groupSelector || !userSelector) {
            return;
        }

        var groupStudentMap = parseGroupStudentMap(form);
        if (!Object.keys(groupStudentMap).length) {
            return;
        }

        var manuallyDeselectedUserIds = new Set();
        var previousAutoSelectedUserIds = new Set();

        function getAutoSelectedUserIds() {
            var selectedGroupIds = groupSelector.getSelectedValues();
            var autoSelectedIds = new Set();

            selectedGroupIds.forEach(function (groupId) {
                var mappedUsers = groupStudentMap[String(groupId)] || [];
                mappedUsers.forEach(function (userId) {
                    autoSelectedIds.add(String(userId));
                });
            });

            return autoSelectedIds;
        }

        function syncUsersFromSelectedGroups() {
            var autoSelectedIds = getAutoSelectedUserIds();
            var staleManualIds = [];

            manuallyDeselectedUserIds.forEach(function (userId) {
                if (!autoSelectedIds.has(userId)) {
                    staleManualIds.push(userId);
                }
            });

            staleManualIds.forEach(function (userId) {
                manuallyDeselectedUserIds.delete(userId);
            });

            previousAutoSelectedUserIds.forEach(function (userId) {
                if (!autoSelectedIds.has(userId)) {
                    userSelector.setValueSelected(userId, false, "group-sync");
                }
            });

            autoSelectedIds.forEach(function (userId) {
                if (!manuallyDeselectedUserIds.has(userId)) {
                    userSelector.setValueSelected(userId, true, "group-sync");
                }
            });

            previousAutoSelectedUserIds = new Set(autoSelectedIds);
        }

        groupSelector.onSelectionChange(function () {
            syncUsersFromSelectedGroups();
        });

        userSelector.onItemToggle(function (meta) {
            if (!meta || meta.source !== "user") {
                return;
            }

            var userId = String(meta.value || "");
            if (!userId) {
                return;
            }

            var autoSelectedIds = getAutoSelectedUserIds();
            if (!autoSelectedIds.has(userId)) {
                return;
            }

            if (meta.isSelected) {
                manuallyDeselectedUserIds.delete(userId);
            } else {
                manuallyDeselectedUserIds.add(userId);
            }
        });

        var initialSelectedUserIds = new Set(userSelector.getSelectedValues());
        var initialAutoSelectedUserIds = getAutoSelectedUserIds();

        initialAutoSelectedUserIds.forEach(function (userId) {
            if (!initialSelectedUserIds.has(userId)) {
                manuallyDeselectedUserIds.add(userId);
            }
        });

        previousAutoSelectedUserIds = new Set(initialAutoSelectedUserIds);
        syncUsersFromSelectedGroups();
    }

    ns.searchableSelect = {
        initGroupUserSync: initGroupUserSync,
        initSearchableSelect: initSearchableSelect,
        parseGroupStudentMap: parseGroupStudentMap
    };
})(window.EMSExamCreateEditModal = window.EMSExamCreateEditModal || {}, document);
