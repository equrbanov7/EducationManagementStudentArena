(function () {
    var initializedRoots = new WeakSet();

    function setHidden(element, hidden) {
        if (!element) {
            return;
        }
        element.hidden = !!hidden;
    }

    function setCurrentPreviewOpacity(previewElement, hasPendingReplacement) {
        if (!previewElement) {
            return;
        }
        previewElement.style.opacity = hasPendingReplacement ? "0.45" : "1";
    }

    function initQuestionForm(root) {
        if (!root || initializedRoots.has(root)) {
            return;
        }
        initializedRoots.add(root);

        if (window.EMSBootstrapSelect) {
            window.EMSBootstrapSelect.init(root);
        }

        var imageInput = root.querySelector('input[name="image"]');
        var videoInput = root.querySelector('input[name="video"]');
        var imageClearInput = root.querySelector('input[name="image-clear"]');
        var videoClearInput = root.querySelector('input[name="video-clear"]');
        var imageFileName = root.querySelector("[data-question-image-file-name]");
        var videoFileName = root.querySelector("[data-question-video-file-name]");
        var currentImagePreview = root.querySelector("[data-current-image-preview]");
        var currentVideoPreview = root.querySelector("[data-current-video-preview]");
        var newImagePreview = root.querySelector("[data-new-image-preview]");
        var newVideoPreview = root.querySelector("[data-new-video-preview]");
        var newImage = root.querySelector("[data-new-image]");
        var newVideo = root.querySelector("[data-new-video]");
        var newVideoSource = root.querySelector("[data-new-video-source]");
        var imageRemoveButton = root.querySelector('[data-question-clear-media="image"]');
        var videoRemoveButton = root.querySelector('[data-question-clear-media="video"]');
        var form = root.querySelector("form");
        var answerModeSelect = root.querySelector('select[name="answer_mode"]');
        var singleAnswerWarning = root.querySelector("[data-single-answer-warning]");
        var variantsSection = root.querySelector(".variants-section");
        var optionList = root.querySelector("[data-option-list]");
        var optionCardTemplate = root.querySelector("[data-option-card-template]");
        var minOptionCount = parseInt(root.dataset.minOptionCount || "2", 10);

        function getCorrectOptionCheckboxes() {
            return Array.prototype.slice.call(root.querySelectorAll('input[name$="_is_correct"]'));
        }

        function getOptionCards() {
            if (!optionList) {
                return [];
            }
            return Array.prototype.slice.call(optionList.querySelectorAll("[data-option-card]"));
        }

        function getOptionTextInput(card) {
            return card ? card.querySelector('input[type="text"]') : null;
        }

        function getOptionCheckbox(card) {
            return card ? card.querySelector('input[type="checkbox"]') : null;
        }

        function getOptionTextLabel(card) {
            return card ? card.querySelector("[data-option-text-label]") : null;
        }

        function getOrdinalSuffix(index) {
            var suffixMap = {
                0: "cu",
                1: "ci",
                2: "ci",
                3: "cü",
                4: "cü",
                5: "ci",
                6: "cı",
                7: "ci",
                8: "ci",
                9: "cu"
            };
            return suffixMap[index % 10] || "ci";
        }

        function formatOptionLabel(index) {
            return index + "-" + getOrdinalSuffix(index) + " variant";
        }

        function getCheckedCorrectCount() {
            return getCorrectOptionCheckboxes().reduce(function (count, checkbox) {
                return count + (checkbox.checked ? 1 : 0);
            }, 0);
        }

        function hideSingleAnswerWarning() {
            if (!singleAnswerWarning) {
                return;
            }
            singleAnswerWarning.textContent = "";
            setHidden(singleAnswerWarning, true);
        }

        function showSingleAnswerWarning() {
            if (!singleAnswerWarning) {
                return;
            }
            singleAnswerWarning.textContent =
                root.dataset.singleAnswerWarningMessage ||
                "Cavab rejimini tək seçimdən çoxlu seçimə dəyişmək lazımdır.";
            setHidden(singleAnswerWarning, false);
        }

        function isSingleAnswerMode() {
            return !!answerModeSelect && answerModeSelect.value === "single";
        }

        function syncSingleAnswerWarning() {
            if (!answerModeSelect || !getCorrectOptionCheckboxes().length) {
                return;
            }

            if (isSingleAnswerMode() && getCheckedCorrectCount() > 1) {
                showSingleAnswerWarning();
                return;
            }

            hideSingleAnswerWarning();
        }

        function updateRemoveButtons() {
            var cards = getOptionCards();
            cards.forEach(function (card) {
                var button = card.querySelector("[data-remove-option-btn]");
                if (button) {
                    button.hidden = cards.length <= minOptionCount;
                }
            });
        }

        function renumberOptionCards() {
            var cards = getOptionCards();
            cards.forEach(function (card, position) {
                var index = position + 1;
                var label = formatOptionLabel(index);
                var textInput = getOptionTextInput(card);
                var checkbox = getOptionCheckbox(card);
                var textLabel = getOptionTextLabel(card);

                card.dataset.optionIndex = String(index);

                if (textLabel) {
                    textLabel.textContent = label + ":";
                    textLabel.setAttribute("for", "id_option" + index + "_text");
                }

                if (textInput) {
                    textInput.name = "option" + index + "_text";
                    textInput.id = "id_option" + index + "_text";
                }

                if (checkbox) {
                    checkbox.name = "option" + index + "_is_correct";
                    checkbox.id = "id_option" + index + "_is_correct";
                }
            });

            updateRemoveButtons();
            syncSingleAnswerWarning();
        }

        function buildOptionCard(index) {
            if (!optionCardTemplate) {
                return null;
            }

            var label = formatOptionLabel(index);
            var html = optionCardTemplate.innerHTML
                .replace(/__INDEX__/g, String(index))
                .replace(/__LABEL__/g, label);

            var temp = document.createElement("div");
            temp.innerHTML = html.trim();
            return temp.firstElementChild;
        }

        function addOptionCard() {
            if (!optionList) {
                return;
            }

            var nextIndex = getOptionCards().length + 1;
            var card = buildOptionCard(nextIndex);
            if (!card) {
                return;
            }

            optionList.appendChild(card);
            renumberOptionCards();

            var textInput = getOptionTextInput(card);
            if (textInput) {
                textInput.focus();
            }
        }

        function removeOptionCard(button) {
            var card = button.closest("[data-option-card]");
            if (!card) {
                return;
            }

            if (getOptionCards().length <= minOptionCount) {
                return;
            }

            card.remove();
            renumberOptionCards();
        }

        function handleCorrectOptionChange(event) {
            if (!answerModeSelect || !isSingleAnswerMode()) {
                hideSingleAnswerWarning();
                return;
            }

            if (!event.target.checked) {
                syncSingleAnswerWarning();
                return;
            }

            if (getCheckedCorrectCount() > 1) {
                event.target.checked = false;
                showSingleAnswerWarning();
                answerModeSelect.focus();
                return;
            }

            hideSingleAnswerWarning();
        }

        function handleFormSubmit(event) {
            if (!isSingleAnswerMode() || getCheckedCorrectCount() <= 1) {
                return;
            }

            event.preventDefault();
            showSingleAnswerWarning();
            answerModeSelect.focus();
        }

        function showFileName(labelElement, file) {
            if (!labelElement) {
                return;
            }
            if (!file) {
                labelElement.textContent = "";
                setHidden(labelElement, true);
                return;
            }
            labelElement.textContent = file.name;
            setHidden(labelElement, false);
        }

        function clearImageSelectionState() {
            showFileName(imageFileName, null);
            if (newImage) {
                newImage.src = "";
            }
            setHidden(newImagePreview, true);
            setCurrentPreviewOpacity(currentImagePreview, false);
        }

        function clearVideoSelectionState() {
            showFileName(videoFileName, null);
            if (newVideoSource) {
                newVideoSource.src = "";
            }
            if (newVideo) {
                newVideo.load();
            }
            setHidden(newVideoPreview, true);
            setCurrentPreviewOpacity(currentVideoPreview, false);
        }

        function handleImageChange(event) {
            var file = event.target.files && event.target.files[0];
            if (!file) {
                clearImageSelectionState();
                return;
            }

            if (imageClearInput) {
                imageClearInput.checked = false;
            }

            showFileName(imageFileName, file);

            var reader = new FileReader();
            reader.onload = function (loadEvent) {
                if (newImage) {
                    newImage.src = loadEvent.target.result;
                }
                setHidden(newImagePreview, false);
                setCurrentPreviewOpacity(currentImagePreview, true);
            };
            reader.readAsDataURL(file);
        }

        function handleVideoChange(event) {
            var file = event.target.files && event.target.files[0];
            if (!file) {
                clearVideoSelectionState();
                return;
            }

            if (videoClearInput) {
                videoClearInput.checked = false;
            }

            showFileName(videoFileName, file);

            var objectUrl = URL.createObjectURL(file);
            if (newVideoSource) {
                newVideoSource.src = objectUrl;
            }
            if (newVideo) {
                newVideo.load();
            }
            setHidden(newVideoPreview, false);
            setCurrentPreviewOpacity(currentVideoPreview, true);
        }

        function clearImage() {
            var confirmMessage = root.dataset.confirmDeleteImage || "Delete image?";
            var alertMessage = root.dataset.alertImageWillBeDeleted || "";
            if (!window.confirm(confirmMessage)) {
                return;
            }

            if (imageClearInput) {
                imageClearInput.checked = true;
            }
            if (imageInput) {
                imageInput.value = "";
            }
            if (currentImagePreview) {
                currentImagePreview.style.display = "none";
            }
            clearImageSelectionState();
            if (alertMessage) {
                window.alert(alertMessage);
            }
        }

        function clearVideo() {
            var confirmMessage = root.dataset.confirmDeleteVideo || "Delete video?";
            var alertMessage = root.dataset.alertVideoWillBeDeleted || "";
            if (!window.confirm(confirmMessage)) {
                return;
            }

            if (videoClearInput) {
                videoClearInput.checked = true;
            }
            if (videoInput) {
                videoInput.value = "";
            }
            if (currentVideoPreview) {
                currentVideoPreview.style.display = "none";
            }
            clearVideoSelectionState();
            if (alertMessage) {
                window.alert(alertMessage);
            }
        }

        if (imageInput) {
            imageInput.addEventListener("change", handleImageChange);
        }
        if (videoInput) {
            videoInput.addEventListener("change", handleVideoChange);
        }
        if (imageRemoveButton) {
            imageRemoveButton.addEventListener("click", clearImage);
        }
        if (videoRemoveButton) {
            videoRemoveButton.addEventListener("click", clearVideo);
        }
        if (answerModeSelect) {
            answerModeSelect.addEventListener("change", syncSingleAnswerWarning);
            syncSingleAnswerWarning();
        }
        if (variantsSection) {
            variantsSection.addEventListener("click", function (event) {
                var addButton = event.target.closest("[data-add-option-btn]");
                if (addButton) {
                    addOptionCard();
                    return;
                }

                var removeButton = event.target.closest("[data-remove-option-btn]");
                if (removeButton) {
                    removeOptionCard(removeButton);
                }
            });

            variantsSection.addEventListener("change", function (event) {
                if (event.target && /_is_correct$/.test(event.target.name || "")) {
                    handleCorrectOptionChange(event);
                }
            });

            renumberOptionCards();
        } else {
            updateRemoveButtons();
        }
        if (form) {
            form.addEventListener("submit", handleFormSubmit);
        }
    }

    window.ExamQuestionForm = {
        init: initQuestionForm
    };

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll(".js-exam-question-form-root").forEach(initQuestionForm);
    });
})();
