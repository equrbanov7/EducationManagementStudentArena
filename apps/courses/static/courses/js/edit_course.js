/*
 * edit_course.js
 * Source: apps/courses/templates/courses/edit_course.html
 * Cover-image live preview on file selection.
 * The file input's id is bridged via data-file-input-id on #imageDisplayArea.
 */
(function () {
    "use strict";

    window.EMSReady(function () {
        var display = document.getElementById("imageDisplayArea");
        if (!display) { return; }

        var fileInputId = display.dataset.fileInputId;
        var fileInput = fileInputId ? document.getElementById(fileInputId) : null;
        var currentImageBlock = document.getElementById("currentImageBlock");
        var imagePreviewBlock = document.getElementById("imagePreviewBlock");
        var previewImg = document.getElementById("previewImg");

        if (!fileInput || fileInput.dataset.ecBound === "1") { return; }
        fileInput.dataset.ecBound = "1";

        fileInput.addEventListener("change", function (e) {
            var file = e.target.files[0];
            if (!file) { return; }
            var reader = new FileReader();
            reader.onload = function (event) {
                if (previewImg) { previewImg.src = event.target.result; }
                if (imagePreviewBlock) { imagePreviewBlock.classList.remove("d-none"); }
                if (currentImageBlock) { currentImageBlock.classList.add("d-none"); }
            };
            reader.readAsDataURL(file);
        });
    });
})();
