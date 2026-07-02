/* Exam create/edit form toggles and type picker helpers. */
(function (ns, window) {
    "use strict";

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

    function showModalTemplateInfo(form, templateSelect) {
        var infoPanel = form.querySelector("#modalSupervisionTemplateInfo");
        var infoTitle = form.querySelector("#modalSupervisionTemplateInfoTitle");
        var infoDesc = form.querySelector("#modalSupervisionTemplateInfoDesc");
        var infoFeatures = form.querySelector("#modalSupervisionTemplateInfoFeatures");
        if (!infoPanel || !templateSelect) {
            return;
        }

        var val = templateSelect.value;
        var templates =
            typeof window.MODAL_SUPERVISION_TPL_INFO === "object"
                ? window.MODAL_SUPERVISION_TPL_INFO
                : {};
        var borderColors = {
            custom: "#6c757d",
            light: "#28a745",
            medium: "#ffc107",
            strict: "#dc3545",
        };
        var tpl = templates[val];
        if (!tpl || val === "custom") {
            infoPanel.style.display = "none";
            return;
        }
        infoTitle.textContent = tpl.title || "";
        infoDesc.textContent = tpl.desc || "";
        infoFeatures.innerHTML = "";
        (tpl.features || []).forEach(function (f) {
            var li = document.createElement("li");
            li.textContent = f;
            infoFeatures.appendChild(li);
        });
        infoPanel.style.borderLeftColor = borderColors[val] || "#007bff";
        infoPanel.style.display = "block";
    }

    function initSupervisionToggle(form) {
        if (!form) {
            return;
        }

        var enabledCheckbox = form.querySelector('input[name="supervision_enabled"]');
        var settingsBlock = form.querySelector("#modalSupervisionSettings");
        var templateSelect = form.querySelector('select[name="supervision_template"]');
        var customBlock = form.querySelector("#modalSupervisionCustomSettings");

        if (!enabledCheckbox || !settingsBlock) {
            return;
        }

        function syncSupervisionSettings() {
            if (enabledCheckbox.checked) {
                settingsBlock.style.display = "block";
                settingsBlock.removeAttribute("hidden");
            } else {
                settingsBlock.style.display = "none";
            }
        }

        function syncSupervisionCustom() {
            if (!templateSelect || !customBlock) {
                return;
            }
            customBlock.style.display = templateSelect.value === "custom" ? "block" : "none";
        }

        syncSupervisionSettings();
        enabledCheckbox.addEventListener("change", syncSupervisionSettings);
        enabledCheckbox.addEventListener("click", function () {
            setTimeout(syncSupervisionSettings, 0);
        });

        if (templateSelect) {
            syncSupervisionCustom();
            templateSelect.addEventListener("change", syncSupervisionCustom);
            templateSelect.addEventListener("change", function () {
                showModalTemplateInfo(form, templateSelect);
            });
            showModalTemplateInfo(form, templateSelect);
        }
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
        var randomQuestionGroup = form.querySelector("[data-random-question-group], [data-test-random-question-group]");
        var randomQuestionInput = form.querySelector('input[name="random_question_count"]');

        function syncExamTypeVisibility(examType) {
            if (!paintCheckbox) {
                if (randomQuestionGroup) {
                    randomQuestionGroup.hidden = false;
                }
                if (randomQuestionInput) {
                    randomQuestionInput.disabled = false;
                }
                return;
            }

            var isWritten = examType === "written";
            if (randomQuestionGroup) {
                randomQuestionGroup.hidden = false;
            }
            if (randomQuestionInput) {
                randomQuestionInput.disabled = false;
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

    ns.toggles = {
        initAccessToggle: initAccessToggle,
        initExamTypePicker: initExamTypePicker,
        initSupervisionToggle: initSupervisionToggle,
        showModalTemplateInfo: showModalTemplateInfo
    };
})(window.EMSExamCreateEditModal = window.EMSExamCreateEditModal || {}, window);
