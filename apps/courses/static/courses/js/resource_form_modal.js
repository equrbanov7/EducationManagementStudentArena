/*
 * resource_form_modal.js
 * Source: apps/courses/templates/courses/partials/_resource_form_modal.html
 *
 * «Yeni Resurs Əlavə Et» modalı (2026-10-19):
 *   - tip (Fayl / Link / Video / Sənəd) dəyişəndə fayl sahəsinin `accept`-i, ipucu (formatlar +
 *     maks. ölçü) və limit radio-nun data-atributlarından yenilənir (mənbə: apps/courses/resource_upload.py);
 *   - fayl seçimi: sürüklə-burax zona, ad + ölçü, «çıxar» düyməsi; uzantı/ölçü YÜKLƏMƏDƏN əvvəl yoxlanır;
 *   - göndərmə XHR ilə — yükləmə irəliləyişi (<progress>), düymə bloklanır, pəncərə təsadüfən bağlanmır
 *     («Ləğv et» yükləməni dayandırır);
 *   - cavab JSON deyilsə (nginx 413/502/504, sessiya bitməsi) status koduna görə AYDIN mesaj göstərilir —
 *     əvvəl hər belə hal «Xəta baş verdi» toast-ı idi.
 * AJAX-safe: window.EMSReady + idempotent bağlama (form.dataset.resourceFormBound).
 */
(function () {
    "use strict";

    var MB = 1024 * 1024;

    function fmt(template, values) {
        return String(template || "").replace(/\{(\w+)\}/g, function (match, key) {
            return Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match;
        });
    }

    function formatMb(bytes) {
        var value = Math.round((bytes / MB) * 10) / 10;
        return String(value.toFixed(1)).replace(/\.0$/, "").replace(".", ",");
    }

    function formatSize(bytes) {
        if (bytes < MB) { return Math.max(1, Math.round(bytes / 1024)) + " KB"; }
        return formatMb(bytes) + " MB";
    }

    function extensionOf(name) {
        var match = /(\.[^./\\]+)$/.exec(String(name || "").toLowerCase());
        return match ? match[1] : "";
    }

    function init() {
        var cfg = document.getElementById("resourceFormModalConfig");
        var form = document.getElementById("resourceForm");
        var modalEl = document.getElementById("resourceFormModal");
        if (!cfg || !form || !modalEl || form.dataset.resourceFormBound === "1") { return; }
        form.dataset.resourceFormBound = "1";
        var d = cfg.dataset;

        var fileSection = document.getElementById("fileUploadSection");
        var urlSection = document.getElementById("urlInputSection");
        var fileInput = document.getElementById("resourceFile");
        var urlInput = document.getElementById("resourceUrl");
        var titleInput = document.getElementById("resourceTitle");
        var errorsBox = document.getElementById("resourceErrors");
        var dropzone = form.querySelector("[data-resource-dropzone]");
        var nameEl = form.querySelector("[data-resource-file-name]");
        var sizeEl = form.querySelector("[data-resource-file-size]");
        var clearBtn = form.querySelector("[data-resource-file-clear]");
        var hintEl = form.querySelector("[data-resource-file-hint]");
        var progressBox = form.querySelector("[data-resource-progress]");
        var progressBar = form.querySelector("[data-resource-progress-bar]");
        var progressText = form.querySelector("[data-resource-progress-text]");
        var submitBtn = form.querySelector("[data-resource-submit]") || form.querySelector('button[type="submit"]');
        var cancelBtn = modalEl.querySelector('.ems-bsd__foot [data-bs-dismiss="modal"]');
        var submitHtml = submitBtn ? submitBtn.innerHTML : "";
        var xhr = null;

        function selectedRadio() {
            return form.querySelector('input[name="resource_type"]:checked') ||
                form.querySelector('input[name="resource_type"]');
        }

        function kindLabel(radio) {
            var label = radio && form.querySelector('label[for="' + radio.id + '"]');
            return label ? label.textContent.trim() : (radio ? radio.value : "");
        }

        function clearErrors() {
            if (!errorsBox) { return; }
            errorsBox.textContent = "";
            errorsBox.classList.add("d-none");
        }

        function showErrors(messages) {
            if (!errorsBox) { return; }
            errorsBox.textContent = "";
            var strong = document.createElement("strong");
            strong.textContent = (d.i18nErrorsHeader || "") + ":";
            var list = document.createElement("ul");
            list.className = "mb-0";
            messages.forEach(function (message) {
                var item = document.createElement("li");
                item.textContent = String(message);
                list.appendChild(item);
            });
            errorsBox.appendChild(strong);
            errorsBox.appendChild(list);
            errorsBox.classList.remove("d-none");
            if (typeof errorsBox.scrollIntoView === "function") {
                errorsBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
            }
        }

        function flattenErrors(errors) {
            var out = [];
            Object.keys(errors || {}).forEach(function (field) {
                var value = errors[field];
                (Array.isArray(value) ? value : [value]).forEach(function (message) {
                    out.push(typeof message === "object" && message && message.message ? message.message : message);
                });
            });
            return out;
        }

        function currentFile() {
            return fileInput && fileInput.files && fileInput.files.length ? fileInput.files[0] : null;
        }

        /* Fayl tipə uyğundurmu — uyğun deyilsə xəta mətni (server də eyni qaydanı yoxlayır). */
        function fileProblem(file, radio) {
            if (!file || !radio) { return ""; }
            var allowed = (radio.dataset.extensions || "").split(/\s+/).filter(Boolean);
            var ext = extensionOf(file.name);
            if (allowed.indexOf(ext) === -1) {
                return fmt(d.i18nExtRejected, {
                    kind: kindLabel(radio), ext: ext || d.i18nNoExtension, formats: radio.dataset.formats || ""
                });
            }
            if (!file.size) { return d.i18nEmptyFile; }
            var maxBytes = Number(radio.dataset.maxBytes) || 0;
            if (maxBytes && file.size > maxBytes) {
                return fmt(d.i18nTooLarge, { size: formatMb(file.size), max_mb: radio.dataset.maxMb });
            }
            return "";
        }

        function refreshFileUi() {
            var file = currentFile();
            if (dropzone) { dropzone.classList.toggle("has-file", !!file); }
            if (nameEl) { nameEl.textContent = file ? file.name : (nameEl.dataset.emptyLabel || ""); }
            if (sizeEl) {
                sizeEl.textContent = file ? formatSize(file.size) : "";
                sizeEl.hidden = !file;
            }
            if (clearBtn) { clearBtn.hidden = !file; }
            var problem = fileProblem(file, selectedRadio());
            if (dropzone) { dropzone.classList.toggle("is-invalid", !!problem); }
            if (problem) { showErrors([problem]); } else { clearErrors(); }
        }

        function applyType(radio) {
            if (!radio) { return; }
            var isLink = radio.value === "link";
            fileSection.classList.toggle("d-none", isLink);
            urlSection.classList.toggle("d-none", !isLink);
            // Gizli sahə göndərilmir (FormData disabled sahələri atır) — tip ↔ sahə uyğunsuzluğu olmur.
            fileInput.disabled = isLink;
            urlInput.disabled = !isLink;
            fileInput.required = !isLink;
            urlInput.required = isLink;
            fileInput.setAttribute("accept", radio.dataset.accept || "");
            if (hintEl) { hintEl.textContent = radio.dataset.hint || ""; }
            if (isLink) { clearErrors(); } else { refreshFileUi(); }
        }

        function clientErrors() {
            var radio = selectedRadio();
            var messages = [];
            if (titleInput && !titleInput.value.trim()) { messages.push(d.i18nTitleRequired); }
            if (radio && radio.value === "link") {
                var url = (urlInput.value || "").trim();
                if (!url) { messages.push(d.i18nUrlRequired); }
                else if (!/^https?:\/\//i.test(url)) { messages.push(d.i18nUrlScheme); }
            } else {
                var file = currentFile();
                if (!file) { messages.push(fmt(d.i18nFileRequired, { kind: kindLabel(radio) })); }
                else {
                    var problem = fileProblem(file, radio);
                    if (problem) { messages.push(problem); }
                }
            }
            return messages;
        }

        function setBusy(busy) {
            if (submitBtn) {
                submitBtn.disabled = busy;
                if (busy) {
                    submitBtn.textContent = "";
                    var icon = document.createElement("i");
                    icon.className = "fas fa-spinner fa-spin";
                    icon.setAttribute("aria-hidden", "true");
                    submitBtn.appendChild(icon);
                    submitBtn.appendChild(document.createTextNode(" " + (d.i18nLoading || "")));
                } else {
                    submitBtn.innerHTML = submitHtml;
                }
            }
            form.setAttribute("aria-busy", busy ? "true" : "false");
            if (dropzone) { dropzone.classList.toggle("is-busy", busy); }
            if (clearBtn) { clearBtn.disabled = busy; }
        }

        function showProgress(pct, text) {
            if (!progressBox) { return; }
            progressBox.hidden = false;
            if (progressBar) {
                if (pct === null) { progressBar.removeAttribute("value"); }
                else { progressBar.value = pct; }
            }
            if (progressText) { progressText.textContent = text; }
        }

        function hideProgress() {
            if (!progressBox) { return; }
            progressBox.hidden = true;
            if (progressBar) { progressBar.value = 0; }
            if (progressText) { progressText.textContent = ""; }
        }

        function statusMessage(status) {
            var radio = selectedRadio();
            if (status === 413) {
                return fmt(d.i18nServerLimit, { max_mb: (radio && radio.dataset.maxMb) || "" });
            }
            if (status === 401) { return d.i18nSession; }
            if (status === 403) { return d.i18nForbidden; }
            if (status === 0) { return d.i18nNetwork; }
            if (status === 408 || status === 502 || status === 503 || status === 504) {
                return fmt(d.i18nTimeout, { status: status });
            }
            return fmt(d.i18nServer, { status: status });
        }

        function parseJson(request) {
            var type = (request.getResponseHeader && request.getResponseHeader("Content-Type")) || "";
            if (type.indexOf("application/json") === -1) { return null; }
            try { return JSON.parse(request.responseText); } catch (err) { return null; }
        }

        function resetForm() {
            form.reset();
            if (window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(document.getElementById("resourceTopic"));
            }
            var topicName = document.getElementById("resourceModalTopicName");
            if (topicName) { topicName.textContent = ""; }
            hideProgress();
            applyType(selectedRadio());
            clearErrors();
        }

        function onSuccess(data) {
            var instance = window.bootstrap && window.bootstrap.Modal && window.bootstrap.Modal.getInstance(modalEl);
            if (instance) { instance.hide(); }
            resetForm();
            if (typeof window.notify === "function") { window.notify(data.message, "success"); }
            setTimeout(function () { window.location.reload(); }, 1000);
        }

        function send() {
            var formData = new FormData(form);
            var request = new XMLHttpRequest();
            xhr = request;
            var hasFile = selectedRadio() && selectedRadio().value !== "link" && currentFile();
            setBusy(true);
            if (hasFile) { showProgress(0, fmt(d.i18nUploading, { pct: "0%" })); }

            request.open("POST", form.action, true);
            request.setRequestHeader("X-Requested-With", "XMLHttpRequest");
            if (request.upload && hasFile) {
                request.upload.addEventListener("progress", function (event) {
                    if (!event.lengthComputable) { return; }
                    var pct = Math.min(100, Math.floor((event.loaded / event.total) * 100));
                    showProgress(pct, fmt(d.i18nUploading, { pct: pct + "%" }));
                });
                request.upload.addEventListener("load", function () {
                    showProgress(null, d.i18nProcessing);
                });
            }
            function finish() {
                xhr = null;
                setBusy(false);
            }
            request.addEventListener("load", function () {
                var data = parseJson(request);
                finish();
                if (data && data.success) { onSuccess(data); return; }
                hideProgress();
                if (data && data.errors) {
                    var messages = flattenErrors(data.errors);
                    showErrors(messages.length ? messages : [statusMessage(request.status)]);
                    return;
                }
                showErrors([statusMessage(request.status)]);
            });
            request.addEventListener("error", function () {
                finish();
                hideProgress();
                showErrors([statusMessage(0)]);
            });
            request.addEventListener("abort", function () {
                finish();
                hideProgress();
            });
            request.send(formData);
        }

        form.querySelectorAll('input[name="resource_type"]').forEach(function (radio) {
            radio.addEventListener("change", function () { applyType(radio); });
        });

        fileInput.addEventListener("change", refreshFileUi);

        if (clearBtn) {
            clearBtn.addEventListener("click", function () {
                fileInput.value = "";
                refreshFileUi();
                fileInput.focus();
            });
        }

        if (dropzone) {
            ["dragenter", "dragover"].forEach(function (name) {
                dropzone.addEventListener(name, function (event) {
                    event.preventDefault();
                    if (!fileInput.disabled && !xhr) { dropzone.classList.add("is-dragover"); }
                });
            });
            ["dragleave", "dragend"].forEach(function (name) {
                dropzone.addEventListener(name, function () { dropzone.classList.remove("is-dragover"); });
            });
            dropzone.addEventListener("drop", function (event) {
                event.preventDefault();
                dropzone.classList.remove("is-dragover");
                var files = event.dataTransfer && event.dataTransfer.files;
                if (!files || !files.length || fileInput.disabled || xhr) { return; }
                try {
                    fileInput.files = files;
                } catch (err) {
                    return;
                }
                refreshFileUi();
            });
        }

        form.addEventListener("submit", function (event) {
            event.preventDefault();
            if (xhr) { return; }
            var messages = clientErrors();
            if (messages.length) { showErrors(messages); return; }
            clearErrors();
            send();
        });

        // Yükləmə gedərkən pəncərə ESC/fon/✕ ilə bağlanmır; «Ləğv et» yükləməni dayandırır və bağlayır.
        if (cancelBtn) {
            cancelBtn.addEventListener("click", function () {
                if (xhr) { xhr.abort(); }
            });
        }
        modalEl.addEventListener("hide.bs.modal", function (event) {
            if (xhr) { event.preventDefault(); }
        });
        modalEl.addEventListener("hidden.bs.modal", resetForm);

        applyType(selectedRadio());
    }

    if (window.EMSReady) { window.EMSReady(init); }
    else { document.addEventListener("DOMContentLoaded", init); }
})();
