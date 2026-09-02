/* «Tələbə idxalı» bölməsi (student-intake) — AJAX-safe panel məntiqi.
 *
 * Panel SERVER-RENDER-lidir; JS üç şeyi edir:
 *   1) seçilmiş faylı QURU İCRA-ya göndərir (multipart POST → preview_url);
 *   2) nəticə cədvəlini qurur və «Tətbiq et» düyməsini şərti göstərir;
 *   3) tətbiqdən sonra birdəfəlik parolları CSV kimi endirir (Blob).
 *
 * Qaydalar (CLAUDE.md + docs/frontend/AJAX_SAFE_JS_PATTERN.md):
 *   · inline JS yoxdur — dinamik dəyərlər `data-*` atributlarındadır;
 *   · `EMSDelegate.on` ilə document səviyyəsində delegasiya (swap-safe);
 *   · kök element (`[data-six-root]`) yoxdursa heç nə etmir (null-safe);
 *   · parol heç vaxt DOM-da saxlanılmır — yalnız endirmə anında qurulur.
 */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE || !window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") {
        return;
    }

    var pendingCredentials = null;

    function root() {
        return document.querySelector("[data-six-root]");
    }

    function texts() {
        var host = root();
        var node = host && host.querySelector("[data-six-i18n]");
        return node ? node.dataset : {};
    }

    function showError(host, message) {
        var box = host.querySelector("[data-six-error]");
        if (!box) {
            return;
        }
        box.textContent = message || "";
        box.hidden = !message;
    }

    function statusLabel(status, t) {
        if (status === "created") {
            return { text: t.tCreated || "created", tone: "ok" };
        }
        if (status === "create") {
            return { text: t.tCreate || "create", tone: "info" };
        }
        if (status === "skip") {
            return { text: t.tSkip || "skip", tone: "warn" };
        }
        return { text: t.tError || "error", tone: "danger" };
    }

    function renderRows(host, payload, title) {
        var t = texts();
        var body = host.querySelector("[data-six-rows]");
        var counts = host.querySelector("[data-six-counts]");
        var result = host.querySelector("[data-six-result]");
        var heading = host.querySelector("[data-six-result-title]");
        if (!body || !result) {
            return;
        }
        body.textContent = "";
        (payload.rows || []).forEach(function (row) {
            var tr = document.createElement("tr");
            var label = statusLabel(row.status, t);
            tr.className = "six-row is-" + label.tone;
            [
                String(row.row || ""),
                label.text,
                row.fin || "",
                row.full_name || "",
                row.group || "",
                row.username || "",
                [row.message || ""].concat(row.warnings || []).filter(Boolean).join(" · "),
            ].forEach(function (value, index) {
                var td = document.createElement("td");
                td.textContent = value;
                if (index === 1) {
                    td.className = "six-status six-status--" + label.tone;
                }
                tr.appendChild(td);
            });
            body.appendChild(tr);
        });

        var summary = payload.summary || {};
        if (counts) {
            counts.textContent = "";
            [
                [t.tTotal || "total", summary.total || 0, "info"],
                [t.tCreated || "created", summary.created, "ok"],
                [t.tCreate || "create", summary.create, "info"],
                [t.tSkip || "skip", summary.skip || 0, "warn"],
                [t.tError || "error", summary.error || 0, "danger"],
            ].forEach(function (item) {
                if (item[1] === undefined || item[1] === null) {
                    return;
                }
                var chip = document.createElement("span");
                chip.className = "six-chip six-chip--" + item[2];
                chip.textContent = item[0] + ": " + item[1];
                counts.appendChild(chip);
            });
        }
        if (heading) {
            heading.textContent = title || "";
        }
        result.hidden = false;
        return summary;
    }

    function setBusy(button, busy, busyText) {
        if (!button) {
            return;
        }
        if (busy) {
            button.dataset.sixLabel = button.dataset.sixLabel || button.textContent;
            button.textContent = busyText || "…";
            button.disabled = true;
        } else {
            if (button.dataset.sixLabel) {
                button.textContent = button.dataset.sixLabel;
            }
            button.disabled = false;
        }
    }

    function selectedFile(host) {
        var input = host.querySelector("[data-six-file]");
        return input && input.files && input.files.length ? input.files[0] : null;
    }

    function post(host, url, file) {
        var data = new FormData();
        data.append("file", file);
        return window.EMSCore.fetchJSON(url, { method: "POST", body: data });
    }

    function errorMessage(err, t) {
        var payload = err && err.payload;
        if (payload && typeof payload === "object" && payload.message) {
            return payload.message;
        }
        return t.tFailed || "error";
    }

    function run(host, mode) {
        var t = texts();
        var file = selectedFile(host);
        showError(host, "");
        if (!file) {
            showError(host, t.tNofile || "");
            return;
        }
        var isApply = mode === "apply";
        var button = host.querySelector(isApply ? "[data-six-apply]" : "[data-six-preview]");
        var url = host.getAttribute(isApply ? "data-apply-url" : "data-preview-url");
        if (isApply && !window.confirm(t.tConfirm || "?")) {
            return;
        }
        setBusy(button, true, t.tBusy);
        post(host, url, file)
            .then(function (payload) {
                var summary = renderRows(host, payload, isApply ? t.tApplied : t.tPreview);
                var applyButton = host.querySelector("[data-six-apply]");
                var downloadButton = host.querySelector("[data-six-download]");
                var note = host.querySelector("[data-six-note]");
                if (applyButton) {
                    applyButton.hidden = isApply || !summary || !summary.create;
                }
                pendingCredentials = isApply ? payload.credentials || [] : null;
                if (downloadButton) {
                    downloadButton.hidden = !(pendingCredentials && pendingCredentials.length);
                }
                if (note) {
                    note.hidden = !(pendingCredentials && pendingCredentials.length);
                }
                if (isApply) {
                    var input = host.querySelector("[data-six-file]");
                    var label = host.querySelector("[data-six-file-label]");
                    if (input) {
                        input.value = "";
                    }
                    if (label) {
                        label.textContent = label.dataset.sixEmpty || label.textContent;
                    }
                }
            })
            .catch(function (err) {
                showError(host, errorMessage(err, t));
            })
            .then(function () {
                setBusy(button, false);
            });
    }

    function csvCell(value) {
        var text = String(value === undefined || value === null ? "" : value);
        return '"' + text.replace(/"/g, '""') + '"';
    }

    function downloadCredentials() {
        if (!pendingCredentials || !pendingCredentials.length) {
            return;
        }
        var lines = [["username", "password", "full_name", "fin", "group"].join(",")];
        pendingCredentials.forEach(function (row) {
            lines.push(
                [row.username, row.password, row.full_name, row.fin, row.group].map(csvCell).join(",")
            );
        });
        var blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
        var url = window.URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = "telebe_idxal_parollari.csv";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.setTimeout(function () {
            window.URL.revokeObjectURL(url);
        }, 1000);
    }

    DELEGATE.on("change", "[data-six-file]", function (event, input) {
        var host = root();
        if (!host) {
            return;
        }
        var label = host.querySelector("[data-six-file-label]");
        if (label) {
            label.dataset.sixEmpty = label.dataset.sixEmpty || label.textContent;
            label.textContent = input.files && input.files.length ? input.files[0].name : label.dataset.sixEmpty;
        }
        showError(host, "");
    });

    DELEGATE.on("click", "[data-six-preview]", function (event) {
        var host = root();
        if (!host) {
            return;
        }
        event.preventDefault();
        run(host, "preview");
    });

    DELEGATE.on("click", "[data-six-apply]", function (event) {
        var host = root();
        if (!host) {
            return;
        }
        event.preventDefault();
        run(host, "apply");
    });

    DELEGATE.on("click", "[data-six-download]", function (event) {
        event.preventDefault();
        downloadCredentials();
    });
})(window, document);
