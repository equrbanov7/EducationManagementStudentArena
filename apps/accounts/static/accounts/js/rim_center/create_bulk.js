/* RİM «yeni hesab» — TOPLU idxal dialoqu (qəbul siyahısı faylı).
 *
 * SERVER MƏNTİQİ TAM PAYLAŞILIR: bu dialoq mövcud «Tələbə idxalı»
 * endpoint-lərini (`student_intake_preview` / `…_apply`) çağırır — eyni
 * `user.import` qapısı, eyni parser, eyni plan qurucusu. Yəni «gördüyün nəticə
 * = alacağın nəticə» müqaviləsi iki səthdə də eynidir və burada NƏ parser,
 * NƏ validator təkrarlanmır.
 *
 * TƏKRARLANAN yeganə şey TƏQDİMATDIR (cədvəl + CSV): bölmə səthi
 * `profile/student_intake.js` ATİS-ə xas sütun/qrup-seçici budaqları daşıyır;
 * onları dialoqa gətirmək iki ekranı bir-birinə kilidləyərdi.
 *
 * Parol heç vaxt DOM-da saxlanılmır — CSV yalnız endirmə anında qurulur və
 * dialoq bağlananda yaddaşdakı nüsxə silinir.
 */
(function (window, document) {
    "use strict";

    var ns = (window.EMSRimCreate = window.EMSRimCreate || {});
    if (!window.EMSDelegate || !window.EMSReady) {
        return;
    }

    var bulk = (ns.bulk = {});
    var credentials = null;

    function root() {
        return document.querySelector("[data-rimc-root]");
    }

    function t(key) {
        return ns.t ? ns.t(key) : key;
    }

    function pick(selector) {
        return document.querySelector(selector);
    }

    function showError(message) {
        var box = pick("[data-rimb-error]");
        if (box) {
            box.textContent = message || "";
            box.hidden = !message;
        }
    }

    function selectedFile() {
        var input = pick("[data-rimb-file]");
        return input && input.files && input.files.length ? input.files[0] : null;
    }

    function statusLabel(status) {
        if (status === "created") {
            return { text: t("st_created"), tone: "ok" };
        }
        if (status === "create") {
            return { text: t("st_create"), tone: "info" };
        }
        if (status === "skip") {
            return { text: t("st_skip"), tone: "warn" };
        }
        return { text: t("st_error"), tone: "danger" };
    }

    function renderRows(payload) {
        var body = pick("[data-rimb-rows]");
        if (!body) {
            return;
        }
        body.textContent = "";
        (payload.rows || []).forEach(function (row) {
            var label = statusLabel(row.status);
            var tr = document.createElement("tr");
            [
                String(row.row || ""),
                label.text,
                row.fin || "",
                row.full_name || "",
                row.group || "",
                row.username || "",
                [row.message || ""].concat(row.warnings || []).filter(Boolean).join(" · ")
            ].forEach(function (value, index) {
                var td = document.createElement("td");
                td.textContent = value;
                if (index === 1) {
                    td.className = "rimc-status rimc-status--" + label.tone;
                }
                tr.appendChild(td);
            });
            body.appendChild(tr);
        });
    }

    function renderCounts(summary) {
        var box = pick("[data-rimb-counts]");
        if (!box) {
            return;
        }
        box.textContent = "";
        [
            [t("total"), summary.total, "info"],
            [t("st_created"), summary.created, "ok"],
            [t("st_create"), summary.create, "info"],
            [t("st_skip"), summary.skip, "warn"],
            [t("st_error"), summary.error, "danger"]
        ].forEach(function (item) {
            if (item[1] === undefined || item[1] === null) {
                return;
            }
            var chip = document.createElement("span");
            chip.className = "rimc-chip rimc-chip--" + item[2];
            chip.textContent = item[0] + ": " + item[1];
            box.appendChild(chip);
        });
    }

    function setBusy(button, busy) {
        if (!button) {
            return;
        }
        if (busy) {
            button.dataset.rimbLabel = button.dataset.rimbLabel || button.textContent;
            button.textContent = t("bulk_busy");
            button.disabled = true;
            button.setAttribute("aria-disabled", "true");
        } else {
            if (button.dataset.rimbLabel) {
                button.textContent = button.dataset.rimbLabel;
                delete button.dataset.rimbLabel;
            }
            button.disabled = false;
            button.setAttribute("aria-disabled", "false");
        }
        var result = pick("[data-rimb-result]");
        if (result) {
            result.setAttribute("aria-busy", busy ? "true" : "false");
        }
    }

    function afterRun(payload, applied) {
        var summary = payload.summary || {};
        renderRows(payload);
        renderCounts(summary);

        var caption = pick("[data-rimb-caption]");
        if (caption) {
            caption.textContent = applied ? t("bulk_applied") : t("bulk_preview");
        }
        var result = pick("[data-rimb-result]");
        if (result) {
            result.hidden = false;
        }

        // «Tətbiq et» yalnız yaradılacaq sətir varsa və hələ tətbiq olunmayıbsa.
        var apply = pick("[data-rimb-apply]");
        if (apply) {
            var pending = !applied && Number(summary.create || 0) > 0;
            apply.hidden = !pending;
            apply.textContent = t("bulk_apply_count").replace("{n}", String(summary.create || 0));
            delete apply.dataset.rimbLabel;
        }

        credentials = applied ? payload.credentials || [] : null;
        var download = pick("[data-rimb-download]");
        var note = pick("[data-rimb-note]");
        var hasCredentials = !!(credentials && credentials.length);
        if (download) {
            download.hidden = !hasCredentials;
        }
        if (note) {
            note.hidden = !hasCredentials;
        }
    }

    function run(mode) {
        var host = root();
        var fetchJSON = window.EMSCore && window.EMSCore.fetchJSON;
        if (!host || !fetchJSON) {
            return;
        }
        var file = selectedFile();
        showError("");
        if (!file) {
            showError(t("bulk_nofile"));
            return;
        }
        var applied = mode === "apply";
        var button = pick(applied ? "[data-rimb-apply]" : "[data-rimb-preview]");
        var url = host.getAttribute(applied ? "data-apply-url" : "data-preview-url");

        var body = new FormData();
        body.append("file", file);

        setBusy(button, true);
        fetchJSON(url, { method: "POST", body: body })
            .then(function (payload) {
                afterRun(payload || {}, applied);
            })
            .catch(function (err) {
                var response = err && err.payload;
                showError((response && response.message) || t("failed"));
            })
            .then(function () {
                setBusy(button, false);
            });
    }

    /* ── CSV (birdəfəlik parollar) ──────────────────────────────────────── */

    function csvCell(value) {
        return '"' + String(value === undefined || value === null ? "" : value).replace(/"/g, '""') + '"';
    }

    function downloadCredentials() {
        if (!credentials || !credentials.length) {
            return;
        }
        var lines = [["username", "password", "full_name", "fin", "group"].join(",")];
        credentials.forEach(function (row) {
            lines.push([row.username, row.password, row.full_name, row.fin, row.group].map(csvCell).join(","));
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

    /* ── Fayl seçimi (klik + sürüşdürmə) ────────────────────────────────── */

    function syncFileLabel() {
        var input = pick("[data-rimb-file]");
        var label = pick("[data-rimb-file-label]");
        var drop = pick("[data-rimb-drop]");
        var preview = pick("[data-rimb-preview]");
        var file = selectedFile();
        if (label) {
            label.dataset.rimbEmpty = label.dataset.rimbEmpty || label.textContent;
            label.textContent = file ? file.name : label.dataset.rimbEmpty;
        }
        if (drop) {
            drop.classList.toggle("is-filled", !!file);
            drop.classList.remove("is-over");
        }
        if (preview) {
            preview.disabled = !file;
            preview.setAttribute("aria-disabled", file ? "false" : "true");
        }
        if (input && !file) {
            input.value = "";
        }
        showError("");
    }

    bulk.reset = function reset() {
        var input = pick("[data-rimb-file]");
        if (input) {
            input.value = "";
        }
        credentials = null;
        [
            "[data-rimb-result]",
            "[data-rimb-apply]",
            "[data-rimb-download]",
            "[data-rimb-note]"
        ].forEach(function (selector) {
            var el = pick(selector);
            if (el) {
                el.hidden = true;
            }
        });
        syncFileLabel();
    };

    window.EMSDelegate.on("change", "[data-rimb-file]", function () {
        syncFileLabel();
    });

    window.EMSDelegate.on("dragover", "[data-rimb-drop]", function (event, drop) {
        event.preventDefault();
        drop.classList.add("is-over");
    });

    window.EMSDelegate.on("dragleave", "[data-rimb-drop]", function (event, drop) {
        drop.classList.remove("is-over");
    });

    window.EMSDelegate.on("drop", "[data-rimb-drop]", function (event) {
        event.preventDefault();
        var input = pick("[data-rimb-file]");
        var transfer = event.dataTransfer;
        if (input && transfer && transfer.files && transfer.files.length) {
            input.files = transfer.files;
        }
        syncFileLabel();
    });

    window.EMSDelegate.on("click", "[data-rimb-preview]", function (event) {
        event.preventDefault();
        run("preview");
    });

    window.EMSDelegate.on("click", "[data-rimb-apply]", function (event) {
        event.preventDefault();
        run("apply");
    });

    window.EMSDelegate.on("click", "[data-rimb-download]", function (event) {
        event.preventDefault();
        downloadCredentials();
    });

    // Dialoq bağlananda parollar yaddaşdan silinir.
    window.EMSDelegate.on("ems:overlay:close", "#rimc-bulk", function () {
        credentials = null;
    });

    window.EMSReady(function () {
        if (!root()) {
            return; // Bölmə bu səhifədə yoxdur — null-safe çıxış.
        }
        syncFileLabel();
    });
})(window, document);
