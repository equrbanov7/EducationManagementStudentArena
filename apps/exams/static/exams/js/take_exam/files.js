(function (ns, window, document) {
    "use strict";

    function syncInputFiles(ctx, qid) {
        var input = document.querySelector('input[name="file_' + qid + '[]"]');
        if (!input) {
            return;
        }

        var dataTransfer = new DataTransfer();
        (ctx.fileState[qid] || []).forEach(function (file) {
            dataTransfer.items.add(file);
        });
        input.files = dataTransfer.files;
    }

    function renderPreview(ctx, qid) {
        var container = document.getElementById("file-preview-" + qid);
        if (!container) {
            return;
        }

        var files = ctx.fileState[qid] || [];
        container.innerHTML = "";

        files.forEach(function (file, index) {
            var icon = "\uD83D\uDCC4";
            var nameLower = file.name.toLowerCase();
            if (nameLower.endsWith(".pdf")) {
                icon = "\uD83D\uDCD5";
            }
            if (nameLower.endsWith(".zip")) {
                icon = "\uD83D\uDDC2\uFE0F";
            }
            if (file.type.startsWith("image/")) {
                icon = "\uD83D\uDDBC\uFE0F";
            }

            var item = document.createElement("div");
            item.className = "file-preview-item";
            item.dataset.index = String(index);

            var left = document.createElement("div");
            left.className = "file-preview-left";

            var iconEl = document.createElement("span");
            iconEl.className = "file-icon";
            iconEl.textContent = icon;

            var nameEl = document.createElement("span");
            nameEl.className = "file-name";
            nameEl.textContent = file.name;

            var removeBtn = document.createElement("button");
            removeBtn.type = "button";
            removeBtn.className = "file-remove-btn";
            removeBtn.setAttribute("data-remove-file-question", qid);
            removeBtn.setAttribute("data-remove-file-index", index);
            removeBtn.textContent = "\u00D7";

            left.appendChild(iconEl);
            left.appendChild(nameEl);
            item.appendChild(left);
            item.appendChild(removeBtn);
            container.appendChild(item);
        });
    }

    ns.files = {
        init: function (ctx) {
            document.querySelectorAll(".file-preview-area").forEach(function (container) {
                container.dataset.existingFileCount = String(container.querySelectorAll(".file-preview-item").length);
            });

            window.handleFiles = function (event, qid) {
                var selected = Array.from(event.target.files);
                if (!ctx.fileState[qid]) {
                    ctx.fileState[qid] = [];
                }
                ctx.fileState[qid] = ctx.fileState[qid].concat(selected);
                syncInputFiles(ctx, qid);
                renderPreview(ctx, qid);
                ns.draft.markAnswerChanged(ctx, 1000, qid, { containsBinary: true });
            };

            window.handleDrop = function (event, qid) {
                event.preventDefault();
                event.currentTarget.classList.remove("hover");

                var selected = Array.from(event.dataTransfer.files);
                if (!ctx.fileState[qid]) {
                    ctx.fileState[qid] = [];
                }
                ctx.fileState[qid] = ctx.fileState[qid].concat(selected);
                syncInputFiles(ctx, qid);
                renderPreview(ctx, qid);
                ns.draft.markAnswerChanged(ctx, 1000, qid, { containsBinary: true });
            };

            window.triggerFileInput = function (qid) {
                var input = document.querySelector('input[name="file_' + qid + '[]"]');
                if (input) {
                    input.click();
                }
            };

            window.removeFile = function (qid, index) {
                if (!ctx.fileState[qid]) {
                    return;
                }
                ctx.fileState[qid].splice(index, 1);
                syncInputFiles(ctx, qid);
                renderPreview(ctx, qid);
                ns.draft.markAnswerChanged(ctx, 1000, qid, { containsBinary: true });
            };
        }
    };
})(window.EMSTakeExam = window.EMSTakeExam || {}, window, document);
