/* Preview and apply the same file; never treat a stale preview as authorization. */
(function (window, document) {
    "use strict";
    var delegate = window.EMSDelegate;
    if (!delegate) return;
    var previews = new WeakMap();

    // W6 `w6paper` (2026-09-14): şablon vərəq kartının şəbəkəsi ilə endirilir —
    // sual sayı / bir sualın maksimumu / imtahan növü klik anında URL-ə yazılır
    // (server parametr olmayanda sonuncu vərəqin şəbəkəsinə düşür).
    var GRID_FIELDS = {
        question_count: "[data-ese-question-count]",
        question_max: "[data-ese-question-max]",
        exam_kind: "[data-ese-exam-kind]"
    };
    function templateHref(link) {
        var url = new URL(link.getAttribute("href"), window.location.href);
        Object.keys(GRID_FIELDS).forEach(function (name) {
            var field = document.querySelector(GRID_FIELDS[name]);
            if (field && field.value !== "") url.searchParams.set(name, field.value);
        });
        return url.toString();
    }
    function scoreText(item) {
        if (item.score == null) return "—";
        var parts = item.question_scores;
        if (!parts || !parts.length) return String(item.score);
        return item.score + " (" + parts.join(" + ") + ")";
    }

    function t(key) {
        var labels = document.getElementById("eseI18n");
        return labels ? labels.getAttribute("data-" + key) || "" : "";
    }
    function error(root, message) {
        var box = root.querySelector("[data-esi-error]");
        box.textContent = message || "";
        box.hidden = !message;
    }
    function payload(root, file) {
        var data = new FormData();
        data.set("file", file);
        data.set("offering_id", root.dataset.offeringId);
        if (root.dataset.orgId) data.set("organization_id", root.dataset.orgId);
        document.querySelectorAll("[data-ese-meta-field], [data-ese-meta-file]").forEach(function (field) {
            if (field.type === "file") {
                if (field.files[0]) data.set(field.name, field.files[0]);
            } else data.set(field.name, field.value);
        });
        data.set("reason", root.querySelector("[data-esi-reason]").value);
        data.set("note", root.querySelector("[data-esi-note]").value);
        // 2026-09-26: panelin öz təqdimat skanı + bitmiş dövrün düzəliş rejimi bayrağı.
        var evidence = root.querySelector("[data-esi-evidence]");
        if (evidence && evidence.files[0]) data.set(evidence.name, evidence.files[0]);
        if (correctionMode(root)) data.set(root.dataset.correctionField || "correction_mode", "1");
        return data;
    }
    function correctionMode(root) {
        return root.dataset.correctionMode === "1";
    }
    function hasScan(form) {
        return Boolean(form.get("sheet_evidence") || form.get("justification_evidence"));
    }
    function render(root, data) {
        root.querySelector("[data-esi-result]").hidden = false;
        root.querySelector("[data-esi-result-title]").textContent = t(data.applied ? "import-applied-title" : "import-preview-title");
        var summary = data.summary;
        root.querySelector("[data-esi-counts]").textContent =
            (data.applied ? data.result.total : summary.total) + " " + t("summary-students") + " · " +
            (data.applied ? data.result.written : summary.writes) + " " + t(data.applied ? "status-written" : "summary-writes") +
            " · " + (data.applied ? data.result.failed : summary.error) + " " + t("status-error");
        var rows = root.querySelector("[data-esi-rows]");
        rows.replaceChildren();
        (data.rows || []).forEach(function (item) {
            var row = document.createElement("tr");
            [item.row, item.written ? t("status-written") : t("import-" + item.status), item.student || item.full_name || item.key,
                item.current == null ? "—" : item.current, scoreText(item),
                [item.message, item.warning].filter(Boolean).join(" · ")].forEach(function (value) {
                var cell = document.createElement("td");
                cell.textContent = String(value == null ? "" : value);
                row.appendChild(cell);
            });
            rows.appendChild(row);
        });
        // Server `needs_justification`-ı bitmiş dövr qaydası ilə hesablayır (2026-09-26).
        root.querySelector("[data-esi-just]").hidden = !data.needs_justification || data.applied;
        root.querySelector("[data-esi-apply]").hidden = data.applied || !summary.writes;
        root.querySelector("[data-esi-reload]").hidden = !data.applied;
    }
    async function send(root, apply) {
        var file = root.querySelector("[data-esi-file]").files[0];
        if (!file) return error(root, t("import-nofile"));
        if (root.dataset.busy === "1") return;
        if (apply && previews.get(root) !== file) return error(root, t("import-preview-title"));
        var form = payload(root, file);
        if (apply && !root.querySelector("[data-esi-just]").hidden &&
                (!form.get("reason") || !form.get("note").trim() || !hasScan(form))) {
            return error(root, t(root.dataset.submissionRequired === "1" ? "need-submission" : "need-justification"));
        }
        var csrf = window.EMSCore && window.EMSCore.getCookie("csrftoken");
        var token = document.querySelector('[name="csrfmiddlewaretoken"]');
        root.dataset.busy = "1";
        root.setAttribute("aria-busy", "true");
        root.querySelectorAll("button").forEach(function (button) { button.disabled = true; });
        error(root, "");
        try {
            var response = await fetch(apply ? root.dataset.applyUrl : root.dataset.previewUrl, {
                method: "POST", body: form, credentials: "same-origin",
                headers: {"X-CSRFToken": csrf || (token && token.value) || "", "X-Requested-With": "XMLHttpRequest"}
            });
            var data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.message || t("import-failed"));
            if (!root.isConnected || root.querySelector("[data-esi-file]").files[0] !== file) return;
            if (apply) previews.delete(root); else previews.set(root, file);
            render(root, data);
        } catch (problem) {
            error(root, problem.message || t("import-failed"));
        } finally {
            root.dataset.busy = "0";
            root.removeAttribute("aria-busy");
            root.querySelectorAll("button").forEach(function (button) { button.disabled = false; });
        }
    }
    delegate.on("click", "[data-esi-preview]", function (event, button) {
        event.preventDefault(); send(button.closest("[data-esi-root]"), false);
    });
    delegate.on("click", "[data-esi-apply]", function (event, button) {
        event.preventDefault(); send(button.closest("[data-esi-root]"), true);
    });
    delegate.on("change", "[data-esi-file]", function (event, input) {
        var root = input.closest("[data-esi-root]");
        previews.delete(root);
        var label = root.querySelector("[data-esi-file-label]");
        if (label) label.textContent = input.files[0] ? input.files[0].name : label.dataset.esiEmpty;
        var drop = input.closest("[data-esi-drop]");
        if (drop) drop.classList.toggle("is-filled", Boolean(input.files[0]));
        root.querySelector("[data-esi-result]").hidden = true;
        root.querySelector("[data-esi-apply]").hidden = true;
        error(root, "");
    });
    delegate.on("dragover", "[data-esi-drop]", function (event, drop) {
        event.preventDefault();
        drop.classList.add("is-over");
    });
    delegate.on("dragleave", "[data-esi-drop]", function (event, drop) {
        if (!drop.contains(event.relatedTarget)) drop.classList.remove("is-over");
    });
    delegate.on("drop", "[data-esi-drop]", function (event, drop) {
        event.preventDefault();
        drop.classList.remove("is-over");
        var input = drop.querySelector("[data-esi-file]");
        if (event.dataTransfer && event.dataTransfer.files.length) {
            input.files = event.dataTransfer.files;
            input.dispatchEvent(new Event("change", {bubbles: true}));
        }
    });
    delegate.on("click", "[data-esi-reload]", function (event) {
        event.preventDefault(); window.location.reload();
    });
    delegate.on("click", "[data-esi-template]", function (event, link) {
        // Kartdakı yanlış şəbəkə (məs. köhnə vərəqdən qalan max 20) endirməni
        // dayandırır — brauzerin öz validasiya mesajı (yeni mətn yoxdur).
        var invalid = Object.keys(GRID_FIELDS).map(function (name) {
            return document.querySelector(GRID_FIELDS[name]);
        }).filter(function (field) { return field && !field.checkValidity(); })[0];
        if (invalid) {
            event.preventDefault();
            invalid.reportValidity();
            return;
        }
        // href klik anında yenilənir — brauzer naviqasiyanı YENİ dəyərlə edir.
        link.setAttribute("href", templateHref(link));
    });
})(window, document);
