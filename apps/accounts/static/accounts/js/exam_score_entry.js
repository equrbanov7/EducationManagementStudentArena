/*
 * exam_score_entry.js — İmtahan Mərkəzi: yazılı imtahan ballarının köçürülməsi
 * (siyahı forması, 2026-09-12 yenidən yazıldı).
 *
 * CSP: bu bölmədə inline <script> YOXDUR — bütün davranış buradadır. Dinamik
 * dəyərlər DOM-dan oxunur: i18n sətirləri `#eseI18n` data-atributlarından,
 * sətrin vəziyyəti `[data-ese-row]`-un data-has-score / data-initial-indən.
 *
 * Nə edir:
 *   1. hər sətrin VƏZİYYƏT nişanını canlı saxlayır (boş / yazılıb /
 *      dəyişdirilib / dəyişiklik·səbəb / xəta) + «Dəyişdirilib» KPI kartı;
 *   2. klaviatura: Enter / ↓ növbəti sətrin balına, ↑ əvvəlkinə keçir
 *      (Enter formanı GÖNDƏRMİR);
 *   3. «Balları yadda saxla» → təsdiq dialoqu: «N tələbə · M bal yazılacaq ·
 *      K dəyişiklik səbəb tələb edir»; K>0 olduqda səbəb + qeyd + skan
 *      (vərəq kartındakı fayl) tələb olunur — server qatı eyni qaydanı yenidən
 *      tətbiq edir, bu yalnız erkən UX;
 *   4. sətrin «tarixçə» düyməsi → `<template>` klonu çekmecəyə (əlavə sorğu yox);
 *   5. «Qrup → Fənn» / «Fənn → Qrup» açarı paneli SPA ilə yenidən yükləyir.
 *
 * Qaydalar (CLAUDE.md + docs/frontend/AJAX_SAFE_JS_PATTERN.md): `EMSDelegate.on`
 * (swap-safe, document səviyyəsində), `EMSReady` (idempotent), null-safe.
 * ⚠️ DELEQAT AÇARLARI (`evt|selector`) qlobaldır — `data-ese-*` seçiciləri
 * YALNIZ bu faylda qeyd olunur (bax test_static_js_delegate_keys.py).
 */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    function root() {
        return document.querySelector("[data-ese-root]");
    }

    function t(key) {
        var el = document.getElementById("eseI18n");
        return el ? el.getAttribute("data-" + key) || "" : "";
    }

    function rows(host) {
        return Array.prototype.slice.call((host || document).querySelectorAll("[data-ese-row]"));
    }

    function scoreInput(row) {
        return row.querySelector("[data-ese-score]");
    }

    /* ---- Sətir vəziyyəti ------------------------------------------------- */

    function rowState(row) {
        var input = scoreInput(row);
        if (!input) {
            return { dirty: false, invalid: false, change: false, value: "" };
        }
        var initial = (input.getAttribute("data-initial") || "").trim();
        var value = (input.value || "").trim();
        var dirty = value !== "" && value !== initial;
        var max = Number(input.getAttribute("max") || 0);
        var num = value === "" ? null : Number(value);
        var invalid = value !== "" && (isNaN(num) || num < 0 || num > max || Math.floor(num) !== num);
        // Sonrakı dəyişiklik = təqdimatlı (sahibin qaydası E7).
        var change = dirty && row.getAttribute("data-has-score") === "1";
        return { dirty: dirty, invalid: invalid, change: change, value: value };
    }

    var BADGE = "ems-badge";

    function setBadge(badge, tone, text) {
        badge.className = BADGE + " " + BADGE + "--" + tone;
        badge.textContent = text;
    }

    function syncRow(row) {
        var input = scoreInput(row);
        var badge = row.querySelector("[data-ese-status]");
        var state = rowState(row);
        if (input) {
            input.classList.toggle("is-dirty", state.dirty && !state.invalid);
            input.classList.toggle("is-invalid", state.invalid);
            input.setAttribute("aria-invalid", state.invalid ? "true" : "false");
        }
        row.classList.toggle("is-dirty", state.dirty);
        if (!badge) {
            return state;
        }
        if (state.invalid) {
            setBadge(badge, "danger", t("status-error"));
        } else if (state.change) {
            setBadge(badge, "warning", t("status-change"));
        } else if (state.dirty) {
            setBadge(badge, "warning", t("status-dirty"));
        } else if (row.getAttribute("data-has-score") === "1") {
            setBadge(badge, "success", t("status-recorded"));
        } else {
            setBadge(badge, "muted", t("status-empty"));
        }
        return state;
    }

    function summarize(host) {
        var all = rows(host);
        var total = { students: all.length, writes: 0, changes: 0, invalid: 0 };
        all.forEach(function (row) {
            var state = rowState(row);
            if (state.invalid) {
                total.invalid += 1;
            } else if (state.dirty) {
                total.writes += 1;
                if (state.change) {
                    total.changes += 1;
                }
            }
        });
        total.untouched = total.students - total.writes - total.invalid;
        return total;
    }

    function syncSummary(host) {
        var summary = summarize(host);
        var line = host.querySelector("[data-ese-summary]");
        if (line) {
            var parts = [summary.students + " " + t("summary-students"), summary.writes + " " + t("summary-writes")];
            if (summary.changes) {
                parts.push(summary.changes + " " + t("summary-changes"));
            }
            parts.push(summary.untouched + " " + t("summary-untouched"));
            line.textContent = parts.join(" · ");
            line.classList.toggle("is-dirty", summary.writes > 0 || summary.invalid > 0);
        }
        var tile = host.querySelector('[data-ems-kpi-key="dirty"] .ems-kpi__value');
        if (tile) {
            tile.textContent = String(summary.writes);
        }
        var card = host.querySelector('[data-ems-kpi-key="dirty"]');
        if (card) {
            card.classList.toggle("ems-kpi--accent-warning", summary.writes > 0);
        }
        return summary;
    }

    function syncAll(host) {
        rows(host).forEach(syncRow);
        return syncSummary(host);
    }

    /* ---- Klaviatura naviqasiyası ----------------------------------------- */

    function moveFocus(current, delta) {
        var all = rows(root()).map(scoreInput).filter(Boolean);
        var index = all.indexOf(current);
        if (index < 0) {
            return;
        }
        var target = all[index + delta];
        if (target) {
            target.focus();
            if (typeof target.select === "function") {
                target.select();
            }
        }
    }

    DELEGATE.on("keydown", "[data-ese-score]", function (event, input) {
        if (event.key === "Enter" || event.key === "ArrowDown") {
            event.preventDefault(); // Enter formanı göndərməsin; ↓ dəyəri azaltmasın.
            moveFocus(input, 1);
        } else if (event.key === "ArrowUp") {
            event.preventDefault();
            moveFocus(input, -1);
        }
    });

    DELEGATE.on("input", "[data-ese-score]", function (event, input) {
        var row = input.closest("[data-ese-row]");
        var host = root();
        if (row) {
            syncRow(row);
        }
        if (host) {
            syncSummary(host);
        }
    });

    /* ---- Sıfırla ---------------------------------------------------------- */

    DELEGATE.on("click", "[data-ese-reset]", function (event) {
        event.preventDefault();
        var host = root();
        if (!host) {
            return;
        }
        rows(host).forEach(function (row) {
            var input = scoreInput(row);
            if (input) {
                input.value = input.getAttribute("data-initial") || "";
            }
        });
        syncAll(host);
    });

    /* ---- Təsdiq dialoqu --------------------------------------------------- */

    function scanSelected(host) {
        var file = host.querySelector("[data-ese-meta-file]");
        return !!(file && file.files && file.files.length);
    }

    function syncScanStatus(host) {
        var status = host.querySelector("[data-ese-scan-status]");
        if (!status) {
            return;
        }
        var ok = scanSelected(host);
        status.textContent = ok ? "✓ " + t("scan-ok") : "✗ " + t("scan-missing");
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

    DELEGATE.on("click", "[data-ese-save]", function (event) {
        event.preventDefault();
        var host = root();
        if (!host) {
            return;
        }
        var summary = syncAll(host);
        var line = host.querySelector("[data-ese-summary]");
        if (summary.invalid) {
            if (line) {
                line.textContent = t("invalid");
                line.classList.add("is-dirty");
            }
            var bad = rows(host).map(scoreInput).filter(function (input) {
                return input && input.classList.contains("is-invalid");
            })[0];
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
        var just = host.querySelector("[data-ese-just]");
        if (just) {
            just.hidden = !summary.changes;
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

    DELEGATE.on("change", "[data-ese-meta-file]", function () {
        var host = root();
        if (host) {
            syncScanStatus(host);
        }
    });

    DELEGATE.on("submit", "form[data-ese-form]", function (event, form) {
        var host = root();
        if (!host) {
            return;
        }
        var summary = summarize(host);
        if (summary.invalid) {
            event.preventDefault();
            showDialogError(host, t("invalid"));
            return;
        }
        if (summary.changes && !justificationComplete(host)) {
            event.preventDefault();
            showDialogError(host, t("need-justification"));
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

    /* ---- Tarixçə çekmecəsi ----------------------------------------------- */

    DELEGATE.on("click", "[data-ese-history]", function (event, btn) {
        event.preventDefault();
        var host = root();
        if (!host) {
            return;
        }
        var id = btn.getAttribute("data-ese-history");
        var template = host.querySelector('[data-ese-history-tpl="' + id + '"]');
        var body = host.querySelector("[data-ese-drawer-body]");
        if (!template || !body) {
            return;
        }
        body.textContent = "";
        body.appendChild(template.content.cloneNode(true));
        if (window.EMSOverlay) {
            window.EMSOverlay.open("eseHistoryDrawer");
        }
    });

    /* ---- Seçim sırası açarı (Qrup → Fənn / Fənn → Qrup) ------------------- */

    DELEGATE.on("click", "[data-ese-nav]", function (event, link) {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return;
        }
        var href = link.getAttribute("href") || "";
        var panel = link.closest("[data-profile-section-panel]");
        var section = panel ? panel.getAttribute("data-profile-section-panel") : "";
        if (!href || !section || typeof window.EMSProfileLoadSection !== "function") {
            return; // kabinetdən kənar: linkin öz davranışı
        }
        event.preventDefault();
        var url = new URL(href, window.location.href);
        url.searchParams.set("section", section);
        window.EMSProfileLoadSection(section, url.pathname + url.search);
    });

    /* ---- İlk render + hər swap -------------------------------------------- */

    window.EMSReady(function () {
        var host = root();
        if (!host) {
            return;
        }
        syncAll(host);
        syncScanStatus(host);
    });
})(window, document);
