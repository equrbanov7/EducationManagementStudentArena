(function () {
    if (window._EXAM_CREATE_EDIT_MODAL_INIT) {
        return;
    }
    window._EXAM_CREATE_EDIT_MODAL_INIT = true;

    document.addEventListener("DOMContentLoaded", function () {
        var modalElement = document.getElementById("examCreateEditModal");
        var modalBody = document.getElementById("examCreateEditModalBody");
        var modalTitle = document.getElementById("examCreateEditModalTitle");
        var modalHeader = modalElement ? modalElement.querySelector(".modal-header") : null;
        var bsModal = null;
        var submitInFlight = false;
        var i18n = window.EXAM_CREATE_EDIT_MODAL_I18N || {};

        if (!modalElement || !modalBody || typeof bootstrap === "undefined") {
            return;
        }

        bsModal = bootstrap.Modal.getOrCreateInstance(modalElement);

        function getLoadingMarkup() {
            var loadingText = i18n.loadingForm || "Loading...";
            return '<div class="create-exam-modal-loading">' + loadingText + "</div>";
        }

        function getErrorMarkup() {
            var errorText = i18n.submitError || (window.COURSES_I18N && window.COURSES_I18N.retryError) || "Please try again.";
            return '<div class="create-exam-modal-error">' + errorText + "</div>";
        }

        function buildModalUrl(rawUrl) {
            try {
                var parsed = new URL(rawUrl, window.location.origin);
                parsed.searchParams.set("modal", "1");
                return parsed.pathname + parsed.search;
            } catch (error) {
                return rawUrl + (rawUrl.indexOf("?") === -1 ? "?modal=1" : "&modal=1");
            }
        }

        function applyModalMode(mode) {
            var isEdit = mode === "edit";
            var titleText = isEdit ? i18n.editTitle : i18n.createTitle;

            if (modalTitle && titleText) {
                modalTitle.textContent = titleText;
            }

            if (modalHeader) {
                modalHeader.classList.remove("bg-primary", "bg-info");
                modalHeader.classList.add(isEdit ? "bg-primary" : "bg-info");
                modalHeader.classList.add("text-white");
            }
        }

        function resetModalBody() {
            modalBody.innerHTML = getLoadingMarkup();
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

        function initAccessToggle(form) {
            if (!form) {
                return;
            }

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
            if (!form) {
                return;
            }

            var nativeSelect = form.querySelector('select[name="exam_type"]');
            var picker = form.querySelector("[data-create-exam-type-picker]");
            if (!nativeSelect || !picker) {
                return;
            }

            var typeOptions = picker.querySelectorAll(".js-create-exam-type-option");
            var paintCheckbox = form.querySelector('input[name="enable_paint"]');
            var paintGroup = form.querySelector("[data-exam-paint-group]");
            var paintLabel = paintCheckbox ? paintCheckbox.closest(".modal-check-label--paint") : null;
            var randomQuestionGroup = form.querySelector("[data-test-random-question-group]");
            var randomQuestionInput = form.querySelector('input[name="random_question_count"]');

            function syncExamTypeVisibility(examType) {
                var isTest = examType === "test";
                if (!paintCheckbox) {
                    if (randomQuestionGroup) {
                        randomQuestionGroup.hidden = !isTest;
                    }
                    if (randomQuestionInput) {
                        randomQuestionInput.disabled = !isTest;
                    }
                    return;
                }

                var isWritten = examType === "written";
                if (randomQuestionGroup) {
                    randomQuestionGroup.hidden = !isTest;
                }
                if (randomQuestionInput) {
                    randomQuestionInput.disabled = !isTest;
                }

                if (!isWritten) {
                    paintCheckbox.checked = false;
                }
                paintCheckbox.disabled = !isWritten;

                if (paintGroup) {
                    paintGroup.hidden = !isWritten;
                }
                if (paintLabel) {
                    paintLabel.classList.toggle("is-disabled", !isWritten);
                }
            }

            function syncPickerFromSelect() {
                var selectedType = nativeSelect.value || "test";
                typeOptions.forEach(function (option) {
                    option.checked = option.value === selectedType;
                });
                syncExamTypeVisibility(selectedType);
            }

            typeOptions.forEach(function (option) {
                option.addEventListener("change", function () {
                    if (!option.checked) {
                        return;
                    }

                    nativeSelect.value = option.value;
                    syncExamTypeVisibility(option.value);
                    nativeSelect.dispatchEvent(new Event("change", { bubbles: true }));
                });
            });

            nativeSelect.addEventListener("change", syncPickerFromSelect);
            syncPickerFromSelect();
        }

        function bindModalForm() {
            var closeInlineBtn = modalBody.querySelector(".js-close-create-exam");
            if (closeInlineBtn) {
                closeInlineBtn.addEventListener("click", function () {
                    bsModal.hide();
                });
            }

            var form = modalBody.querySelector("#createExamModalForm");
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

            if (groupSelector && userSelector) {
                initGroupUserSync(form, groupSelector, userSelector);
            }

            form.addEventListener("submit", async function (event) {
                event.preventDefault();

                if (submitInFlight) {
                    return;
                }

                submitInFlight = true;

                var submitBtn = form.querySelector('button[type="submit"]');
                if (submitBtn) {
                    submitBtn.disabled = true;
                }

                try {
                    var response = await fetch(form.getAttribute("action"), {
                        method: "POST",
                        body: new FormData(form),
                        headers: {
                            "X-Requested-With": "XMLHttpRequest"
                        }
                    });

                    var contentType = response.headers.get("content-type") || "";

                    if (response.ok && contentType.indexOf("application/json") !== -1) {
                        var payload = await response.json();
                        if (payload.success) {
                            bsModal.hide();
                            window.location.reload();
                            return;
                        }
                    }

                    if (contentType.indexOf("application/json") !== -1) {
                        var jsonPayload = await response.json();
                        if (jsonPayload.html) {
                            modalBody.innerHTML = jsonPayload.html;
                            bindModalForm();
                            return;
                        }
                    }

                    var html = await response.text();
                    modalBody.innerHTML = html || getErrorMarkup();
                    bindModalForm();
                } catch (error) {
                    modalBody.innerHTML = getErrorMarkup();
                } finally {
                    submitInFlight = false;
                    if (submitBtn) {
                        submitBtn.disabled = false;
                    }
                }
            });
        }

        async function openExamModal(rawUrl, mode) {
            if (!rawUrl) {
                return;
            }

            applyModalMode(mode);
            modalBody.innerHTML = getLoadingMarkup();
            bsModal.show();

            var modalUrl = buildModalUrl(rawUrl);

            try {
                var response = await fetch(modalUrl, {
                    headers: {
                        "X-Requested-With": "XMLHttpRequest"
                    }
                });

                if (!response.ok) {
                    throw new Error("request_failed");
                }

                var html = await response.text();
                modalBody.innerHTML = html;
                bindModalForm();
            } catch (error) {
                modalBody.innerHTML = getErrorMarkup();
            }
        }

        document.addEventListener("click", function (event) {
            var trigger = event.target.closest(".js-open-exam-form-modal");
            if (!trigger) {
                return;
            }

            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                return;
            }

            event.preventDefault();

            var targetUrl = trigger.getAttribute("data-exam-modal-url") || trigger.getAttribute("href");
            var mode = trigger.getAttribute("data-exam-modal-mode") || "edit";

            var parentModal = trigger.closest(".modal.show");
            if (parentModal && parentModal !== modalElement) {
                var parentModalInstance = bootstrap.Modal.getInstance(parentModal);
                if (parentModalInstance) {
                    parentModal.addEventListener(
                        "hidden.bs.modal",
                        function () {
                            openExamModal(targetUrl, mode);
                        },
                        { once: true }
                    );
                    parentModalInstance.hide();
                    return;
                }
            }

            openExamModal(targetUrl, mode);
        });

        modalElement.addEventListener("hidden.bs.modal", function () {
            submitInFlight = false;
            resetModalBody();
        });

        resetModalBody();
    });
})();
