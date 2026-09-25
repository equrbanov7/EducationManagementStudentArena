/*
 * exam_score_entry_confirm.js — İmtahan Mərkəzi: balların TƏSDİQ dialoqu
 * (2026-09-14, sahibin rəyi). `exam_score_entry.js`-in QARDAŞIDIR (modul-ölçü
 * büdcəsi, SOFT_CAP=600); ortaq vəziyyət funksiyaları `window.EMSExamScoreEntry`
 * API-sindən gəlir (əsas fayl `defer` ilə BUNDAN ƏVVƏL yüklənir).
 *
 * Nə edir:
 *   · «Balları yadda saxla» → dialoq: növ + tarix + yoxlayan başlıqda, yazılacaq
 *     hər tələbə (ad, giriş, imtahan, yekun, hərf — server şkalası; F qırmızı,
 *     kəsilən sayı başlıqda); xətalı sətir varsa dialoq açılmır;
 *   · K>0 dəyişiklik → növ + səbəb + qeyd + skan tələb olunur; skan DİALOQUN
 *     öz fayl sahəsində (`data-ese-just-file`, 2026-09-26) və ya vərəq kartında
 *     seçilir — server eyni qaydanı yenidən tətbiq edir, bu yalnız erkən UX;
 *   · `data-submission-required="1"` (RİM düzəliş rejimi və ya 60 gündən köhnə
 *     bitmiş dövr) — HƏR yazı (ilk daxiletmə də) eyni təqdimatı tələb edir;
 *   · YALNIZ dialoqun «Təsdiq et» düyməsi POST edir (Enter / kənar submit bloklanır).
 *
 * CSP: inline yoxdur; i18n `#eseI18n`. AJAX-safe: `EMSDelegate` (açarlar
 * `data-ese-save`, `data-ese-meta-file`, `form[data-ese-form]` — yalnız burada).
 */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    function api() {
        return window.EMSExamScoreEntry || null;
    }

    function root() {
        return document.querySelector("[data-ese-root]");
    }

    function t(key) {
        var el = document.getElementById("eseI18n");
        return el ? el.getAttribute("data-" + key) || "" : "";
    }

    function fileOf(host, selector) {
        var input = host.querySelector(selector);
        return input && input.files && input.files.length ? input.files[0] : null;
    }

    /* Skan: dialoqun öz fayl sahəsi (2026-09-26) VƏ YA vərəq kartındakı fayl. */
    function scanSelected(host) {
        return !!(fileOf(host, "[data-ese-just-file]") || fileOf(host, "[data-ese-meta-file]"));
    }

    /* HƏR yazı təqdimatlıdır — RİM düzəliş rejimi və ya 60 gündən köhnə bitmiş
       dövrə ilk köçürmə (server `data-submission-required`-i eyni qaydadan qurur). */
    function submissionRequired(host) {
        return host.getAttribute("data-submission-required") === "1";
    }

    function needsJustification(host, summary) {
        return !!(summary.changes || (submissionRequired(host) && summary.writes));
    }

    function syncScanStatus(host) {
        var status = host.querySelector("[data-ese-scan-status]");
        var own = fileOf(host, "[data-ese-just-file]");
        var meta = fileOf(host, "[data-ese-meta-file]");
        var name = host.querySelector("[data-ese-just-file-name]");
        if (name) {
            name.textContent = own ? own.name : name.getAttribute("data-empty") || "";
        }
        var drop = host.querySelector("[data-ese-just-drop]");
        if (drop) {
            drop.classList.toggle("is-filled", !!own);
        }
        if (!status) {
            return;
        }
        var ok = !!(own || meta);
        var text = ok ? "✓ " + t("scan-ok") : "✗ " + t("scan-missing");
        if (!own && meta) {
            text += " — " + meta.name + " (" + t("scan-from-meta") + ")";
        }
        status.textContent = text;
        status.classList.toggle("is-ok", ok);
        status.classList.toggle("is-missing", !ok);
    }

    function justificationComplete(host) {
        var reason = host.querySelector("[data-ese-reason]");
        var note = host.querySelector("[data-ese-note]");
        return !!(reason && reason.value && note && (note.value || "").trim() && scanSelected(host));
    }

    function summaryItem(list, count, label, warning) {
        var item = document.createElement("li");
        if (warning) {
            item.className = "is-warning";
        }
        var num = document.createElement("b");
        num.textContent = String(count);
        item.appendChild(num);
        item.appendChild(document.createTextNode(label));
        list.appendChild(item);
    }

    function showDialogError(host, message) {
        var box = host.querySelector("[data-ese-dialog-error]");
        if (box) {
            box.textContent = message || "";
            box.hidden = !message;
        }
    }

    function cell(text, numeric) {
        var td = document.createElement("td");
        if (numeric) {
            td.className = "ems-table__num ese-td--num";
        }
        td.textContent = text;
        return td;
    }

    function selectedLabel(select) {
        var option = select && select.options[select.selectedIndex];
        return option ? option.textContent.trim() : "";
    }

    function formatDate(iso) {
        var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
        return m ? m[3] + "." + m[2] + "." + m[1] : "—";
    }

    /* Dialoqun başlığı + cədvəli: yazılacaq hər tələbə, hərf, kəsilən sayı. */
    function fillConfirm(host, summary) {
        var cfg = api().config();
        var body = host.querySelector("[data-ese-confirm-rows]");
        var failedBox = host.querySelector("[data-ese-confirm-failed]");
        var failedCount = host.querySelector("[data-ese-confirm-failed-count]");
        var failed = 0;
        if (body) {
            body.textContent = "";
            api().rows(host).forEach(function (row) {
                var state = api().rowState(row);
                if (!state.dirty || state.invalid) {
                    return;
                }
                var result = api().grade(row, Number(state.value), cfg);
                var tr = document.createElement("tr");
                tr.className = result.failed ? "is-failed" : "";
                var th = document.createElement("th");
                th.scope = "row";
                th.textContent = row.getAttribute("data-student") || "";
                tr.appendChild(th);
                tr.appendChild(cell(String(result.entry), true));
                tr.appendChild(cell(state.value, true));
                tr.appendChild(cell(String(result.total), true));
                var letterTd = document.createElement("td");
                letterTd.className = "ems-table__num ese-td--num";
                var badge = document.createElement("span");
                badge.className = "ems-badge ese-letter-badge " + (result.failed ? "ems-badge--danger" : "ems-badge--success");
                badge.textContent = result.letter;
                letterTd.appendChild(badge);
                tr.appendChild(letterTd);
                body.appendChild(tr);
                if (result.failed) {
                    failed += 1;
                }
            });
        }
        if (failedBox) {
            failedBox.hidden = failed === 0;
        }
        if (failedCount) {
            failedCount.textContent = String(failed);
        }
        var kind = host.querySelector("[data-ese-confirm-kind]");
        var kindSelect = host.querySelector("[data-ese-exam-kind]");
        if (kind) {
            kind.textContent = selectedLabel(kindSelect) || (kindSelect ? kindSelect.getAttribute("data-ese-exam-kind-label") : "") || "";
        }
        var date = host.querySelector("[data-ese-confirm-date]");
        var dateInput = host.querySelector('[name="exam_date"]');
        if (date) {
            date.textContent = formatDate(dateInput ? dateInput.value : "");
        }
        var examiner = host.querySelector("[data-ese-confirm-examiner]");
        if (examiner) {
            examiner.textContent = selectedLabel(host.querySelector("[data-ese-examiner]")) || "—";
        }
        var title = document.getElementById("eseSaveDialog-title");
        if (title) {
            title.textContent = t("dialog-title") + " — " + summary.writes + " " + t("summary-writes");
        }
    }

    DELEGATE.on("click", "[data-ese-save]", function (event) {
        event.preventDefault();
        var host = root();
        if (!host) {
            return;
        }
        var summary = api().syncAll(host);
        var line = host.querySelector("[data-ese-summary]");
        if (summary.invalid) {
            if (line) {
                line.textContent = summary.overCap ? t("question-sum") : api().questionCount(host) > 0 ? t("question-invalid") : t("invalid");
                line.classList.add("is-dirty");
            }
            var badRow = host.querySelector("[data-ese-row].is-invalid");
            var bad = badRow ? badRow.querySelector(".bootstrap-single-select__toggle, [data-ese-score]") : null;
            if (bad) {
                bad.focus();
            }
            return;
        }
        if (!summary.writes) {
            if (line) {
                line.textContent = t("nothing");
            }
            return;
        }
        var list = host.querySelector("[data-ese-dialog-summary]");
        if (list) {
            list.textContent = "";
            summaryItem(list, summary.students, t("summary-students"));
            summaryItem(list, summary.writes, t("summary-writes"));
            if (summary.changes) {
                summaryItem(list, summary.changes, t("summary-changes"), true);
            }
            summaryItem(list, summary.untouched, t("summary-untouched"));
        }
        fillConfirm(host, summary);
        var just = host.querySelector("[data-ese-just]");
        if (just) {
            just.hidden = !needsJustification(host, summary);
        }
        showDialogError(host, "");
        syncScanStatus(host);
        var confirm = host.querySelector("[data-ese-confirm]");
        if (confirm) {
            confirm.disabled = false;
        }
        if (window.EMSOverlay) {
            window.EMSOverlay.open("eseSaveDialog");
        }
    });

    DELEGATE.on("change", "[data-ese-meta-file], [data-ese-just-file]", function () {
        var host = root();
        if (host) {
            syncScanStatus(host);
            showDialogError(host, "");
        }
    });

    DELEGATE.on("dragover", "[data-ese-just-drop]", function (event, drop) {
        event.preventDefault();
        drop.classList.add("is-over");
    });

    DELEGATE.on("dragleave", "[data-ese-just-drop]", function (event, drop) {
        if (!drop.contains(event.relatedTarget)) {
            drop.classList.remove("is-over");
        }
    });

    DELEGATE.on("drop", "[data-ese-just-drop]", function (event, drop) {
        event.preventDefault();
        drop.classList.remove("is-over");
        var input = drop.querySelector("[data-ese-just-file]");
        if (input && event.dataTransfer && event.dataTransfer.files.length) {
            input.files = event.dataTransfer.files;
            input.dispatchEvent(new Event("change", { bubbles: true }));
        }
    });

    DELEGATE.on("submit", "form[data-ese-form]", function (event, form) {
        var host = root();
        if (!host) {
            return;
        }
        var dialog = document.getElementById("eseSaveDialog");
        if (dialog && dialog.hidden) {
            event.preventDefault(); // yalnız təsdiq dialoqunun düyməsi göndərir
            return;
        }
        var summary = api().summarize(host);
        if (summary.invalid) {
            event.preventDefault();
            showDialogError(host, t("invalid"));
            return;
        }
        if (needsJustification(host, summary) && !justificationComplete(host)) {
            event.preventDefault();
            showDialogError(host, t(submissionRequired(host) ? "need-submission" : "need-justification"));
            syncScanStatus(host);
            var reason = host.querySelector("[data-ese-reason]");
            if (reason && !reason.value) {
                var toggle = form.querySelector(".ese-just .bootstrap-single-select__toggle");
                (toggle || reason).focus();
            }
            return;
        }
        // İkiqat göndərişin qarşısı: təsdiq düyməsi kilidlənir.
        var confirm = form.querySelector("[data-ese-confirm]");
        if (confirm) {
            confirm.disabled = true;
        }
    });


    window.EMSReady(function () {
        var host = root();
        if (host && api()) {
            syncScanStatus(host);
        }
    });
})(window, document);
