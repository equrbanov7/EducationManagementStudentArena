/* Create-exam modal selector helpers. */
(function (ns) {
    "use strict";

    ns.register(function installCreateExamSelectors(ctx) {
        function initCreateExamSearchableSelect(form, config) {
            if (!form || !config) {
                return null;
            }

            var hiddenSelect = form.querySelector('select[name="' + config.selectName + '"]');
            var listContainer = form.querySelector(config.listSelector);
            var searchInput = form.querySelector(config.searchSelector);
            var counter = form.querySelector(config.counterSelector);
            var optionMap = Object.create(null);
            var checkboxMap = Object.create(null);
            var selectionChangeHandlers = [];
            var itemToggleHandlers = [];

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

            function notifySelectionChange(meta) {
                selectionChangeHandlers.forEach(function (handler) {
                    handler(meta || {});
                });
            }

            function notifyItemToggle(meta) {
                itemToggleHandlers.forEach(function (handler) {
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
                notifyItemToggle(meta);
                notifySelectionChange(meta);
                return true;
            }

            function renderList() {
                var options = Array.from(hiddenSelect.options || []);
                listContainer.innerHTML = "";
                checkboxMap = Object.create(null);
                optionMap = Object.create(null);

                if (!options.length) {
                    listContainer.innerHTML = gettext('<div class="create-exam-list-empty">Məlumat tapılmadı.</div>');
                    updateCounter();
                    return;
                }

                options.forEach(function (option) {
                    optionMap[String(option.value)] = option;

                    var row = document.createElement("div");
                    row.className = "create-exam-list-item";
                    row.setAttribute("data-search", (option.textContent || "").toLowerCase());

                    var checkboxId = "create_exam_" + config.selectName + "_" + option.value;

                    row.innerHTML = "" +
                        '<input type="checkbox" class="create-exam-item-checkbox" id="' + checkboxId + '"' +
                        (option.selected ? " checked" : "") + ">" +
                        '<label class="create-exam-item-label" for="' + checkboxId + '"></label>';

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

        function parseCreateExamGroupStudentMap(form) {
            if (!form) {
                return {};
            }

            var mapScript = form.querySelector("#createExamGroupStudentMap");
            if (!mapScript || !mapScript.textContent) {
                return {};
            }

            try {
                var parsedMap = JSON.parse(mapScript.textContent);
                if (!parsedMap || typeof parsedMap !== "object") {
                    return {};
                }
                return parsedMap;
            } catch (error) {
                return {};
            }
        }

        function initCreateExamGroupUserSelectionSync(form, groupSelector, userSelector) {
            if (!form || !groupSelector || !userSelector) {
                return;
            }

            var groupStudentMap = parseCreateExamGroupStudentMap(form);
            if (!Object.keys(groupStudentMap).length) {
                return;
            }

            var manuallyDeselectedUserIds = new Set();
            var previousAutoSelectedUserIds = new Set();

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
                var staleManualIds = [];

                manuallyDeselectedUserIds.forEach(function (userId) {
                    if (!autoSelectedUserIds.has(userId)) {
                        staleManualIds.push(userId);
                    }
                });
                staleManualIds.forEach(function (userId) {
                    manuallyDeselectedUserIds.delete(userId);
                });

                previousAutoSelectedUserIds.forEach(function (userId) {
                    if (!autoSelectedUserIds.has(userId)) {
                        userSelector.setValueSelected(userId, false, "group-sync");
                    }
                });

                autoSelectedUserIds.forEach(function (userId) {
                    if (!manuallyDeselectedUserIds.has(userId)) {
                        userSelector.setValueSelected(userId, true, "group-sync");
                    }
                });

                previousAutoSelectedUserIds = new Set(autoSelectedUserIds);
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

                var autoSelectedUserIds = getAutoSelectedUserIds();
                if (!autoSelectedUserIds.has(userId)) {
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

        ctx.initCreateExamSearchableSelect = initCreateExamSearchableSelect;
        ctx.initCreateExamGroupUserSelectionSync = initCreateExamGroupUserSelectionSync;
    });
})(window.EMSProfile = window.EMSProfile || {});
