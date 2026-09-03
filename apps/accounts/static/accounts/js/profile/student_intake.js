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

    /* ---- Ekran 08 (ATİS) əlavələri --------------------------------------
     *
     * EYNİ FAYL, çünki axın eynidir (fayl → quru icra → tətbiq). Fərq yalnız
     * SÜTUN dəstidir və qrup seçicisidir: `data-six-atis="1"` olan panel
     * genişləndirilmiş sətri render edir. İkinci JS faylı yazsaydıq, «Tətbiq
     * et» məntiqi iki yerdə saxlanılardı.
     */

    function isAtis(host) {
        return host.getAttribute("data-six-atis") === "1";
    }

    function groupOverrides(host) {
        var out = {};
        var nodes = host.querySelectorAll("[data-six-group]");
        for (var i = 0; i < nodes.length; i += 1) {
            if (nodes[i].value) {
                out[nodes[i].getAttribute("data-six-group")] = nodes[i].value;
            }
        }
        return out;
    }

    function updateKpis(host, payload) {
        var rows = payload.rows || [];
        var counts = { total: rows.length, ok: 0, blocking: 0, warning: 0 };
        rows.forEach(function (row) {
            if (row.status === "error") {
                counts.blocking += 1;
            } else {
                counts.ok += 1;
            }
            if ((row.warnings || []).length) {
                counts.warning += 1;
            }
        });
        Object.keys(counts).forEach(function (key) {
            var tile = host.querySelector('[data-ems-kpi-key="' + key + '"] .ems-kpi__value');
            if (tile) {
                tile.textContent = String(counts[key]);
            }
        });
        return counts;
    }

    function updateSteps(host, counts, applied) {
        var steps = host.querySelectorAll(".ems-step");
        if (!steps.length) {
            return;
        }
        var reached = applied ? 4 : counts.blocking ? 2 : 3;
        for (var i = 0; i < steps.length; i += 1) {
            steps[i].className =
                "ems-step ems-step--" + (i < reached ? "done" : i === reached ? "current" : "todo");
        }
        if (counts.blocking && steps[1]) {
            steps[1].className = "ems-step ems-step--error";
        }
    }

    function groupCell(host, row, t) {
        var td = document.createElement("td");
        if (row.status === "error") {
            // Handoff §5/08: «Bloklayan xəta olan sətir qrupa təyin edilə bilmir».
            td.textContent = "—";
            return td;
        }
        var select = document.createElement("select");
        select.className = "ems-select";
        select.setAttribute("data-six-group", String(row.row || ""));
        select.setAttribute("aria-label", t.tNogroup || "");
        var blank = document.createElement("option");
        blank.value = "";
        blank.textContent = t.tNogroup || "—";
        select.appendChild(blank);
        (row.group_options || []).forEach(function (option) {
            var node = document.createElement("option");
            node.value = option.id;
            node.textContent =
                option.name + " (" + option.taken + "/" + option.capacity + (option.is_full ? " · " + (t.tFull || "") : "") + ")";
            if (option.id === row.group_id) {
                node.selected = true;
            }
            select.appendChild(node);
        });
        if (!row.group_options || !row.group_options.length) {
            blank.textContent = row.group || t.tNogroup || "—";
        }
        td.appendChild(select);
        if (host.getAttribute("data-can-create-group") === "1" && row.specialty_id) {
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "ems-btn ems-btn--sm";
            btn.textContent = t.tNewgroup || "+";
            btn.setAttribute("data-sa-newgroup", row.specialty_id);
            btn.setAttribute("data-sa-suggest", row.suggested_group_name || "");
            btn.setAttribute("data-sa-row", String(row.row || ""));
            td.appendChild(btn);
        }
        return td;
    }

    function renderAtisRow(host, row, label, t) {
        var tr = document.createElement("tr");
        tr.className = "six-row is-" + label.tone;
        [
            String(row.row || ""),
            label.text + " · " + (row.message || ""),
            row.full_name || "",
            row.program_label || "",
            row.admission_score || "",
            row.funding_type || "",
            [row.education_form || "", row.group || ""].filter(Boolean).join(" / ")
        ].forEach(function (value, index) {
            var td = document.createElement("td");
            td.textContent = value;
            if (index === 1) {
                td.className = "six-status six-status--" + label.tone;
            }
            tr.appendChild(td);
        });
        tr.appendChild(groupCell(host, row, t));
        var note = document.createElement("td");
        note.textContent = (row.warnings || []).join(" · ");
        tr.appendChild(note);
        return tr;
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
        var atis = isAtis(host);
        (payload.rows || []).forEach(function (row) {
            var label = statusLabel(row.status, t);
            if (atis) {
                body.appendChild(renderAtisRow(host, row, label, t));
                return;
            }
            var tr = document.createElement("tr");
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
        // Qrup təyinatı (ekran 08): operatorun seçdiyi qruplar FAYLLA BİRLİKDƏ
        // gedir — serverdə state saxlanılmır, ona görə ön baxış və tətbiq
        // eyni sözlüyü alır («gördüyün nəticə = alacağın nəticə»).
        var overrides = groupOverrides(host);
        Object.keys(overrides).forEach(function (row) {
            data.append("group_" + row, overrides[row]);
        });
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
                if (isAtis(host)) {
                    updateSteps(host, updateKpis(host, payload), isApply);
                }
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

    /* ---- Ekran 08: «Yeni qrup yarat» ------------------------------------ */

    DELEGATE.on("click", "[data-sa-newgroup]", function (event, btn) {
        event.preventDefault();
        var dialog = document.getElementById("saGroupDialog");
        if (!dialog) {
            return;
        }
        var form = dialog.querySelector("form");
        if (form) {
            form.reset();
            var specialty = form.querySelector("[data-sa-specialty]");
            if (specialty) {
                specialty.value = btn.getAttribute("data-sa-newgroup") || "";
            }
            var name = form.querySelector('[name="name"]');
            if (name) {
                name.value = btn.getAttribute("data-sa-suggest") || "";
            }
            form.setAttribute("data-sa-row", btn.getAttribute("data-sa-row") || "");
            var box = form.querySelector("[data-ems-form-error]");
            if (box) {
                box.hidden = true;
                box.textContent = "";
            }
        }
        if (window.EMSOverlay) {
            window.EMSOverlay.open(dialog);
        }
    });

    DELEGATE.on("submit", "form[data-sa-group-form]", function (event, form) {
        event.preventDefault();
        var host = root();
        if (!host) {
            return;
        }
        var body = new FormData(form);
        body.delete("csrfmiddlewaretoken");
        var token = form.querySelector('input[name="csrfmiddlewaretoken"]');
        fetch(form.getAttribute("action"), {
            method: "POST",
            body: body,
            credentials: "same-origin",
            headers: {
                "X-CSRFToken": (token && token.value) || "",
                "X-Requested-With": "XMLHttpRequest"
            }
        })
            .then(function (response) {
                return response.json().then(function (payload) {
                    return { ok: response.ok, payload: payload };
                });
            })
            .then(function (result) {
                var box = form.querySelector("[data-ems-form-error]");
                if (!result.ok) {
                    if (box) {
                        box.textContent = (result.payload && result.payload.message) || "";
                        box.hidden = !box.textContent;
                    }
                    return;
                }
                // Yeni qrup BÜTÜN sətirlərin seçicisinə əlavə olunur və əmri
                // veren sətirdə dərhal seçilir (təkrar quru icra tələb olunmur).
                var selects = host.querySelectorAll("[data-six-group]");
                for (var i = 0; i < selects.length; i += 1) {
                    var option = document.createElement("option");
                    option.value = result.payload.id;
                    option.textContent = result.payload.name;
                    selects[i].appendChild(option);
                    if (selects[i].getAttribute("data-six-group") === form.getAttribute("data-sa-row")) {
                        selects[i].value = result.payload.id;
                    }
                }
                if (window.EMSOverlay) {
                    window.EMSOverlay.close(form.closest(".ems-overlay"));
                }
            })
            .catch(function () {
                var box = form.querySelector("[data-ems-form-error]");
                if (box) {
                    box.textContent = texts().tFailed || "";
                    box.hidden = !box.textContent;
                }
            });
    });
})(window, document);
