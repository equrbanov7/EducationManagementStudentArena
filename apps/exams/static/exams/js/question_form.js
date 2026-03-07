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
    }

    window.ExamQuestionForm = {
        init: initQuestionForm
    };

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll(".js-exam-question-form-root").forEach(initQuestionForm);
    });
})();
