/*
 * manage_blocks.js — Lab «Bloklar və suallar» səhifəsi (2026-10-17, Paket E).
 *
 * Bloklar sol tab siyahısında, seçilmiş blokun sualları sağ paneldə (hamısı serverdə render olunub);
 * seçim `location.hash`-də (`#block-<id>`) saxlanılır. Yaratma/redaktə/idxal dialoqları ortaq
 * `ems_ui/overlay.js` (`EMSOverlay`) ilə açılır; göndəriş `EMSCore.fetchJSON` ilə, uğurda səhifə
 * yenilənir. AJAX-safe: `EMSDelegate` (document-səviyyəli, bir dəfə) + `EMSReady` (idempotent init).
 * Konfiqurasiya + tərcümələr `#manageBlocksConfig` data-* atributlarındadır.
 */
(function () {
    "use strict";

    var RELOAD_NOTIFICATION_KEY = "labs.manageBlocks.pendingNotification";

    function config() {
        var el = document.getElementById("manageBlocksConfig");
        return el ? el.dataset : null;
    }

    function labId() {
        var d = config();
        return d ? d.labId : "";
    }

    function t(key, fallback) {
        var d = config();
        var name = "i18n" + key.charAt(0).toUpperCase() + key.slice(1);
        return (d && d[name]) || fallback;
    }

    function byId(id) {
        return document.getElementById(id);
    }

    function toast(message, level, timeout) {
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, level || "info", timeout);
        }
    }

    /* ── Dialoq köməkçiləri ─────────────────────────────────────────────── */
    function formOf(dialogId) {
        var dialog = byId(dialogId);
        return dialog ? dialog.querySelector("form") : null;
    }

    function setFormError(form, message) {
        var box = form && form.querySelector("[data-ems-form-error]");
        if (!box) {
            if (message) { toast(message, "error", 5000); }
            return;
        }
        box.textContent = message || "";
        box.hidden = !message;
    }

    function openDialog(dialogId) {
        var form = formOf(dialogId);
        if (form) { setFormError(form, ""); }
        if (window.EMSOverlay) { window.EMSOverlay.open(dialogId); }
    }

    function setBusy(button, label) {
        if (!button) { return; }
        if (button.dataset.idleHtml === undefined) { button.dataset.idleHtml = button.innerHTML; }
        button.disabled = true;
        button.textContent = "";
        var spinner = document.createElement("i");
        spinner.className = "fas fa-spinner fa-spin";
        spinner.setAttribute("aria-hidden", "true");
        button.appendChild(spinner);
        button.appendChild(document.createTextNode(" " + label));
    }

    function setIdle(button) {
        if (!button || button.dataset.idleHtml === undefined) { return; }
        button.disabled = false;
        button.innerHTML = button.dataset.idleHtml;
        delete button.dataset.idleHtml;
    }

    function errorText(err, payload) {
        var body = payload || (err && err.payload);
        if (body && typeof body === "object") {
            if (body.view_as_blocked) { return ""; } // EMSCore.fetchJSON artıq göstərib
            if (body.error) { return t("errorPrefix", "Error") + ": " + body.error; }
        }
        return t("errorServer", "Server error");
    }

    /* POST + uğurda yenilə; xəta dialoqun içində göstərilir. */
    function submitDialogForm(form, url, busyKey, busyFallback, onSuccess) {
        if (!form) { return; }
        if (typeof form.checkValidity === "function" && !form.checkValidity()) {
            setFormError(form, t("required", "Please fill in the required fields."));
            if (typeof form.reportValidity === "function") { form.reportValidity(); }
            return;
        }
        var button = form.querySelector('[type="submit"]');
        setFormError(form, "");
        setBusy(button, t(busyKey, busyFallback));
        window.EMSCore.fetchJSON(url, { method: "POST", body: new FormData(form) })
            .then(function (data) {
                if (data && data.success) {
                    if (onSuccess) { onSuccess(data); }
                    window.location.reload();
                    return;
                }
                setFormError(form, t("errorPrefix", "Error") + ": " + ((data && data.error) || t("errorUnknown", "Unknown error")));
                setIdle(button);
            })
            .catch(function (err) {
                var message = errorText(err);
                if (message) { setFormError(form, message); }
                setIdle(button);
            });
    }

    function confirmAndPost(bodyText, url) {
        window.EMSConfirm.open({ body: bodyText, danger: true }).then(function (ok) {
            if (!ok) { return; }
            window.EMSCore.fetchJSON(url, { method: "POST" })
                .then(function (data) {
                    if (data && data.success) {
                        window.location.reload();
                    } else {
                        toast(t("errorPrefix", "Error") + ": " + ((data && data.error) || t("errorUnknown", "Unknown error")), "error", 5000);
                    }
                })
                .catch(function (err) {
                    var message = errorText(err);
                    if (message) { toast(message, "error", 5000); }
                });
        });
    }

    /* ── Blok tab-ları ──────────────────────────────────────────────────── */
    function blockTabs() {
        return Array.prototype.slice.call(document.querySelectorAll("[data-lab-block-tab]"));
    }

    function selectBlock(blockId, focusTab) {
        var found = null;
        blockTabs().forEach(function (tab) {
            var on = tab.dataset.labBlockTab === String(blockId);
            tab.setAttribute("aria-selected", on ? "true" : "false");
            if (on) {
                tab.removeAttribute("tabindex");
                found = tab;
            } else {
                tab.setAttribute("tabindex", "-1");
            }
        });
        if (!found) { return false; }
        Array.prototype.forEach.call(document.querySelectorAll("[data-lab-block-panel]"), function (panel) {
            panel.hidden = panel.dataset.labBlockPanel !== String(blockId);
        });
        if (focusTab) { found.focus(); }
        return true;
    }

    function selectFromHash() {
        var match = /^#block-(\d+)$/.exec(window.location.hash || "");
        if (match) { selectBlock(match[1], false); }
    }

    function initBlocks() {
        selectFromHash();
        try {
            var raw = window.sessionStorage.getItem(RELOAD_NOTIFICATION_KEY);
            if (raw) {
                window.sessionStorage.removeItem(RELOAD_NOTIFICATION_KEY);
                var note = JSON.parse(raw);
                if (note && note.message) { toast(note.message, note.type || "info", note.duration || 4500); }
            }
        } catch (err) {
            /* sessionStorage əlçatmazdır — bildiriş atlanır */
        }
    }

    window.EMSReady(initBlocks);
    window.EMSReady.once("labs-manage-blocks-hash", function () {
        window.addEventListener("hashchange", selectFromHash);
    });

    window.EMSDelegate.on("click", "[data-lab-block-tab]", function (event, tab) {
        selectBlock(tab.dataset.labBlockTab, false);
        if (window.history && window.history.replaceState) {
            window.history.replaceState(null, "", "#block-" + tab.dataset.labBlockTab);
        }
    });

    window.EMSDelegate.on("keydown", "[data-lab-block-tab]", function (event, tab) {
        var tabs = blockTabs();
        var index = tabs.indexOf(tab);
        var next = null;
        if (event.key === "ArrowDown" || event.key === "ArrowRight") { next = tabs[(index + 1) % tabs.length]; }
        else if (event.key === "ArrowUp" || event.key === "ArrowLeft") { next = tabs[(index - 1 + tabs.length) % tabs.length]; }
        else if (event.key === "Home") { next = tabs[0]; }
        else if (event.key === "End") { next = tabs[tabs.length - 1]; }
        if (!next) { return; }
        event.preventDefault();
        selectBlock(next.dataset.labBlockTab, true);
        if (window.history && window.history.replaceState) {
            window.history.replaceState(null, "", "#block-" + next.dataset.labBlockTab);
        }
    });

    /* ── Blok: redaktə / sil ────────────────────────────────────────────── */
    window.EMSDelegate.on("click", ".js-edit-block", function (event, btn) {
        var form = formOf("editBlockModal");
        if (!form) { return; }
        byId("editBlockId").value = btn.dataset.id || "";
        byId("edit-block-title").value = btn.dataset.title || "";
        byId("edit-block-description").value = btn.dataset.description || "";
        byId("edit-block-qtp").value = btn.dataset.qtp || 0;
        openDialog("editBlockModal");
    });

    window.EMSDelegate.on("click", ".js-delete-block", function (event, btn) {
        confirmAndPost(t("confirmDeleteBlock", "Delete this block and all questions inside it?"), "/labs/blocks/" + btn.dataset.id + "/delete/");
    });

    window.EMSDelegate.on("submit", "#addBlockModal form", function (event, form) {
        event.preventDefault();
        submitDialogForm(form, "/labs/" + labId() + "/blocks/create/", "stateCreating", "Creating...");
    });

    window.EMSDelegate.on("submit", "#editBlockModal form", function (event, form) {
        event.preventDefault();
        var blockId = byId("editBlockId").value;
        if (!blockId) { return; }
        submitDialogForm(form, "/labs/blocks/" + blockId + "/edit/", "stateSaving", "Saving...");
    });

    /* ── Sual: əlavə / redaktə / sil / idxal ────────────────────────────── */
    window.EMSDelegate.on("click", ".js-add-question", function (event, btn) {
        var form = formOf("addQuestionModal");
        if (!form) { return; }
        form.reset();
        byId("addQuestionId").value = btn.dataset.blockId || "";
        openDialog("addQuestionModal");
    });

    window.EMSDelegate.on("click", ".js-edit-question", function (event, btn) {
        var form = formOf("editQuestionModal");
        if (!form) { return; }
        form.reset();
        byId("editQuestionId").value = btn.dataset.id || "";
        byId("edit-question-text").value = btn.dataset.text || "";
        byId("edit-question-points").value = btn.dataset.points || 0;
        var current = byId("editQuestionCurrentFile");
        if (current) {
            current.textContent = "";
            if (btn.dataset.attachment) {
                var link = document.createElement("a");
                link.className = "lab-chip";
                link.href = btn.dataset.attachment;
                link.target = "_blank";
                link.rel = "noopener";
                var icon = document.createElement("i");
                icon.className = "fas fa-paperclip";
                icon.setAttribute("aria-hidden", "true");
                link.appendChild(icon);
                link.appendChild(document.createTextNode(" " + t("fileExisting", "Existing file")));
                current.appendChild(link);
            }
        }
        openDialog("editQuestionModal");
    });

    window.EMSDelegate.on("click", ".js-import-questions", function (event, btn) {
        var form = formOf("importQuestionsModal");
        if (!form) { return; }
        form.reset();
        byId("importBlockId").value = btn.dataset.blockId || "";
        openDialog("importQuestionsModal");
    });

    window.EMSDelegate.on("click", ".js-delete-question", function (event, btn) {
        confirmAndPost(t("confirmDeleteQuestion", "Delete this question?"), "/labs/questions/" + btn.dataset.id + "/delete/");
    });

    window.EMSDelegate.on("submit", "#addQuestionModal form", function (event, form) {
        event.preventDefault();
        var blockId = byId("addQuestionId").value;
        if (!blockId) { return; }
        submitDialogForm(form, "/labs/blocks/" + blockId + "/questions/create/", "stateAdding", "Adding...");
    });

    window.EMSDelegate.on("submit", "#editQuestionModal form", function (event, form) {
        event.preventDefault();
        var questionId = byId("editQuestionId").value;
        if (!questionId) { return; }
        submitDialogForm(form, "/labs/questions/" + questionId + "/edit/", "stateSaving", "Saving...");
    });

    window.EMSDelegate.on("submit", "#importQuestionsModal form", function (event, form) {
        event.preventDefault();
        var blockId = byId("importBlockId").value;
        if (!blockId) { return; }
        submitDialogForm(form, "/labs/blocks/" + blockId + "/questions/import/", "stateImporting", "Importing...", function (data) {
            var message = data.message || t("successImportDefault", "{count} questions imported").replace("{count}", data.count || 0);
            try {
                window.sessionStorage.setItem(RELOAD_NOTIFICATION_KEY, JSON.stringify({ message: message, type: "success", duration: 4500 }));
            } catch (err) {
                /* sessionStorage əlçatmazdır — bildiriş atlanır */
            }
        });
    });

    /* Yeni sual/idxal: seçilmiş blok hash-də qalsın. */
    window.EMSDelegate.on("click", ".js-add-question, .js-import-questions", function (event, btn) {
        var blockId = btn.dataset.blockId;
        if (blockId && window.history && window.history.replaceState) {
            window.history.replaceState(null, "", "#block-" + blockId);
        }
    });
})();
