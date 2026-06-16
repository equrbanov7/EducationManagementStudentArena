/* =========================================================================
   trial_exam.js — Trial-exam ("sınaq imtahanı") request page.

   - Skeleton → content reveal on load.
   - Accessible drag-and-drop PDF dropzone with click-to-select.
   - Client-side PDF type/size validation (mirrors the server limits).
   - Submit guard: spinner + single-submit protection.

   AJAX-safe: initialises via EMSReady when available (re-runs after profile
   section swaps), otherwise on DOMContentLoaded. Idempotent per root.
   ========================================================================= */
(function () {
    "use strict";

    var MAX_MB = 25;
    var MAX_BYTES = MAX_MB * 1024 * 1024;

    // i18n strings are read from data-* on the error element when present,
    // with safe Azerbaijani fallbacks.
    var MSG = {
        type: "Yalnız PDF formatı qəbul olunur.",
        size: "Fayl ölçüsü 25 MB-dan çox ola bilməz.",
        required: "Zəhmət olmasa sualları PDF formatında yükləyin."
    };

    function formatSize(bytes) {
        if (bytes < 1024) { return bytes + " B"; }
        if (bytes < 1024 * 1024) { return (bytes / 1024).toFixed(0) + " KB"; }
        return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    }

    function isPdf(file) {
        if (!file) { return false; }
        var nameOk = /\.pdf$/i.test(file.name || "");
        // Some browsers omit type; trust the extension when type is blank.
        var typeOk = !file.type || file.type === "application/pdf";
        return nameOk && typeOk;
    }

    function init() {
        var roots = document.querySelectorAll("[data-trial-root]");
        Array.prototype.forEach.call(roots, function (root) {
            if (root.getAttribute("data-trial-init") === "1") { return; }
            root.setAttribute("data-trial-init", "1");
            revealContent(root);
            setupForm(root);
        });
    }

    /* ---- Skeleton → content ---- */
    function revealContent(root) {
        // Brief skeleton flash, then swap in the real form.
        window.setTimeout(function () {
            root.setAttribute("data-loading", "0");
        }, 220);
    }

    /* ---- Dropzone + validation + submit ---- */
    function setupForm(root) {
        var form = root.querySelector("[data-trial-form]");
        if (!form) { return; }

        var drop = form.querySelector("[data-trial-drop]");
        var input = form.querySelector(".trial-form__file-input");
        var emptyView = form.querySelector("[data-trial-drop-empty]");
        var fileView = form.querySelector("[data-trial-drop-file]");
        var nameEl = form.querySelector("[data-trial-file-name]");
        var sizeEl = form.querySelector("[data-trial-file-size]");
        var removeBtn = form.querySelector("[data-trial-file-remove]");
        var errEl = form.querySelector("[data-trial-file-error]");
        var submitBtn = form.querySelector("[data-trial-submit]");

        if (!drop || !input) { return; }

        function showError(msg) {
            if (errEl) {
                errEl.textContent = msg;
                errEl.hidden = false;
            }
            drop.classList.add("has-error");
        }
        function clearError() {
            if (errEl) { errEl.hidden = true; errEl.textContent = ""; }
            drop.classList.remove("has-error");
        }

        function renderSelected(file) {
            if (nameEl) { nameEl.textContent = file.name; }
            if (sizeEl) { sizeEl.textContent = formatSize(file.size); }
            if (emptyView) { emptyView.hidden = true; }
            if (fileView) { fileView.hidden = false; }
        }
        function renderEmpty() {
            if (emptyView) { emptyView.hidden = false; }
            if (fileView) { fileView.hidden = true; }
        }

        function validate(file) {
            if (!isPdf(file)) { showError(MSG.type); return false; }
            if (file.size > MAX_BYTES) { showError(MSG.size); return false; }
            clearError();
            return true;
        }

        function handleFile(file) {
            if (!file) { renderEmpty(); return; }
            if (validate(file)) {
                renderSelected(file);
            } else {
                // Invalid → drop it so the form never submits a bad file.
                clearInput();
                renderEmpty();
            }
        }

        function clearInput() {
            try {
                input.value = "";
                if (window.DataTransfer) { input.files = new DataTransfer().files; }
            } catch (e) { /* no-op */ }
        }

        // Native input change (click-to-select path).
        input.addEventListener("change", function () {
            handleFile(input.files && input.files[0]);
        });

        // Remove button.
        if (removeBtn) {
            removeBtn.addEventListener("click", function (e) {
                e.preventDefault();
                e.stopPropagation();
                clearInput();
                clearError();
                renderEmpty();
            });
        }

        // Drag & drop.
        ["dragenter", "dragover"].forEach(function (evt) {
            drop.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                drop.classList.add("is-dragover");
            });
        });
        ["dragleave", "dragend"].forEach(function (evt) {
            drop.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                drop.classList.remove("is-dragover");
            });
        });
        drop.addEventListener("drop", function (e) {
            e.preventDefault();
            e.stopPropagation();
            drop.classList.remove("is-dragover");
            var files = e.dataTransfer && e.dataTransfer.files;
            if (!files || !files.length) { return; }
            var file = files[0];
            if (!validate(file)) { clearInput(); renderEmpty(); return; }
            try {
                if (window.DataTransfer) {
                    var dt = new DataTransfer();
                    dt.items.add(file);
                    input.files = dt.files;
                }
            } catch (err) { /* assignment unsupported — fall back to empty */ }
            renderSelected(file);
        });

        // Submit guard.
        form.addEventListener("submit", function (e) {
            var file = input.files && input.files[0];
            if (!file) {
                e.preventDefault();
                showError(MSG.required);
                drop.scrollIntoView({ behavior: "smooth", block: "center" });
                return;
            }
            if (!validate(file)) {
                e.preventDefault();
                return;
            }
            // Valid → show spinner, prevent double submit (after default fires).
            if (submitBtn) {
                window.setTimeout(function () {
                    submitBtn.disabled = true;
                    var label = submitBtn.querySelector(".trial__btn-label");
                    var spin = submitBtn.querySelector(".trial__btn-spinner");
                    if (label) { label.hidden = true; }
                    if (spin) { spin.hidden = false; }
                }, 0);
            }
        });
    }

    /* ---- Bootstrapping ---- */
    if (window.EMSReady) {
        window.EMSReady(init);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
