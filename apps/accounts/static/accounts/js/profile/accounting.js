/*
 * «Mühasibatlıq» — panelin davranışı (sahib 2026-10-19).
 *
 * 1) MÜƏLLİM PƏNCƏRƏSİ: cədvəldə sətrə / ada klik `data-ac-detail-url`-dən (views/accounting.py →
 *    `accounting_teacher_detail`, JSON: title, subtitle, html, foot) məzmunu yükləyib `#ac-teacher-dialog`-u açır.
 *    Fokus tələsi, Escape, fokusun qayıtması — `EMSOverlay` (ems_ui/overlay.js). Modifikator klik / orta düymə
 *    adi linkdir (tam səhifə drill-down-u yeni tabda). Köhnə cavab yenisini əvəzləmir (sorğu nömrəsi).
 * 2) «DAHA ÇOX»: pəncərədə keçirilmiş dərslər `ac_part=lessons` ilə növbəti səhifə qədər əlavə olunur.
 * 3) TARİX ARALIĞI: görünən tarix sahələri filtr sahəsi DEYİL — tam, semestr hüdudunda və «başlanğıc ≤ son»
 *    olanda gizli `ac_from` / `ac_to`-ya yazılır və `EMSFilterBar.apply` çağırılır (yazı yarımçıqkən bölmə
 *    yenilənmir). «Ay» select-i aralıqdan başqa dəyərə keçəndə və ya SEMESTR dəyişəndə gizli tarixlər boşalır (URL-dən düşür).
 *
 * AJAX-safe: yalnız EMSDelegate / EMSReady.once (sənəd səviyyəsində, bir dəfə); `[data-ac-root]` yoxdursa
 * heç nə etmir. CSP: inline kod yoxdur, mətnlər data-atributlardadır.
 */
(function (window, document) {
    "use strict";

    if (window.EMSAccounting) {
        return;
    }

    var RANGE_DEBOUNCE_MS = 600;
    var ISO_RE = /^\d{4}-\d{2}-\d{2}$/;
    var requestSeq = 0;
    var rangeTimer = null;

    function dialogEl() {
        return document.getElementById("ac-teacher-dialog");
    }

    function part(dialog, name) {
        return dialog ? dialog.querySelector("[data-ac-dialog-" + name + "]") : null;
    }

    function message(dialog, kind, text) {
        var body = part(dialog, "body");
        if (!body) {
            return;
        }
        var box = document.createElement("div");
        box.className = "ems-msg ems-msg--" + kind + " ac__notice";
        box.setAttribute("role", kind === "danger" ? "alert" : "status");
        var span = document.createElement("div");
        span.textContent = text;
        box.appendChild(span);
        body.innerHTML = "";
        body.appendChild(box);
        resetFoot(dialog);
    }

    /* Altlığın İLKİN halı («Bağla») — yeni müəllim yüklənəndə / xətada əvvəlkinin ixrac düyməsi qalmasın. */
    var initialFoot = typeof WeakMap === "function" ? new WeakMap() : null;

    function resetFoot(dialog) {
        var foot = part(dialog, "foot");
        if (!foot || !initialFoot) {
            return;
        }
        if (!initialFoot.has(dialog)) {
            initialFoot.set(dialog, foot.innerHTML);
            return;
        }
        foot.innerHTML = initialFoot.get(dialog);
    }

    function skeleton(dialog) {
        var body = part(dialog, "body");
        if (!body) {
            return;
        }
        resetFoot(dialog);
        var html = "";
        for (var i = 0; i < 4; i += 1) {
            html +=
                '<div class="ems-skelcard" aria-hidden="true"><span class="skeleton skeleton-line skeleton-line--lg"></span>' +
                '<span class="skeleton skeleton-line"></span><span class="skeleton skeleton-line skeleton-line--sm"></span></div>';
        }
        body.innerHTML = '<div class="ems-filter-skeleton">' + html + "</div>";
        body.setAttribute("aria-busy", "true");
        var loading = dialog.getAttribute("data-ac-loading") || "";
        var title = part(dialog, "title");
        var sub = part(dialog, "sub");
        if (title) {
            title.textContent = loading;
        }
        if (sub) {
            sub.textContent = "";
        }
    }

    function errorText(dialog, status) {
        if (status === 404) {
            return dialog.getAttribute("data-ac-not-found") || "";
        }
        if (status === 403) {
            return dialog.getAttribute("data-ac-forbidden") || "";
        }
        return dialog.getAttribute("data-ac-error") || "";
    }

    function fill(dialog, payload) {
        var body = part(dialog, "body");
        var foot = part(dialog, "foot");
        var title = part(dialog, "title");
        var sub = part(dialog, "sub");
        if (title) {
            title.textContent = payload.title || "";
        }
        if (sub) {
            sub.textContent = payload.subtitle || "";
        }
        if (body) {
            body.innerHTML = payload.html || ""; // server-render, Django avto-escape
            body.removeAttribute("aria-busy");
            body.scrollTop = 0;
        }
        if (foot && payload.foot) {
            foot.innerHTML = payload.foot;
        }
    }

    function openTeacher(url) {
        var dialog = dialogEl();
        if (!dialog || !url || !window.EMSOverlay || !window.EMSCore || !window.EMSCore.fetchJSON) {
            return false;
        }
        requestSeq += 1;
        var seq = requestSeq;
        skeleton(dialog);
        window.EMSOverlay.open(dialog);
        window.EMSCore.fetchJSON(url)
            .then(function (payload) {
                if (seq !== requestSeq || !document.contains(dialog)) {
                    return;
                }
                if (!payload || payload.ok === false) {
                    message(dialog, "danger", errorText(dialog, 0));
                    return;
                }
                fill(dialog, payload);
            })
            .catch(function (err) {
                if (seq !== requestSeq || !document.contains(dialog)) {
                    return;
                }
                var body = part(dialog, "body");
                if (body) {
                    body.removeAttribute("aria-busy");
                }
                var title = part(dialog, "title");
                if (title) {
                    title.textContent = "";
                }
                message(dialog, "danger", errorText(dialog, err && err.status));
            });
        return true;
    }

    function plainClick(event) {
        return !(event.defaultPrevented || event.button > 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey);
    }

    window.EMSDelegate.on("click", "[data-ac-root] [data-ac-open]", function (event, link) {
        if (!plainClick(event)) {
            return; // yeni tab / pəncərə — adi link (tam səhifə drill-down-u)
        }
        if (openTeacher(link.getAttribute("data-ac-detail-url"))) {
            event.preventDefault();
        }
    });

    window.EMSDelegate.on("click", "[data-ac-root] tr[data-ac-row]", function (event, row) {
        if (!plainClick(event) || event.target.closest("a, button, input, select, textarea, label")) {
            return;
        }
        var selection = window.getSelection ? String(window.getSelection() || "") : "";
        if (selection.trim()) {
            return; // mətn seçilirdi — pəncərə açılmasın
        }
        var link = row.querySelector("[data-ac-open]");
        if (link) {
            link.focus(); // bağlananda fokus sətrin linkinə qayıtsın (EMSOverlay açılış anının fokusunu yadda saxlayır)
        }
        openTeacher(row.getAttribute("data-ac-detail-url"));
    });

    /* ---- «Daha çox» ---------------------------------------------------- */

    window.EMSDelegate.on("click", "[data-ac-more]", function (event, btn) {
        event.preventDefault();
        var url = btn.getAttribute("data-ac-more");
        var modal = btn.closest("[data-ac-modal]");
        var tbody = modal ? modal.querySelector("[data-ac-lessons-body]") : null;
        if (!url || !tbody || btn.disabled || !window.EMSCore) {
            return;
        }
        btn.disabled = true;
        btn.setAttribute("aria-busy", "true");
        window.EMSCore.fetchJSON(url)
            .then(function (payload) {
                var before = tbody.rows.length;
                tbody.insertAdjacentHTML("beforeend", (payload && payload.rows) || "");
                var first = tbody.rows[before];
                if (first) {
                    var head = first.querySelector("th") || first.cells[0];
                    head.setAttribute("tabindex", "-1");
                    head.focus();
                }
                var wrap = btn.closest(".ac-more");
                if (payload && payload.more_url) {
                    btn.setAttribute("data-ac-more", payload.more_url);
                    btn.disabled = false;
                    btn.removeAttribute("aria-busy");
                    var label = btn.querySelector("[data-ac-more-label]");
                    if (label && typeof payload.remaining === "number") {
                        label.textContent = label.textContent.replace(/\d+/, String(payload.remaining));
                    }
                } else if (wrap) {
                    wrap.parentNode.removeChild(wrap);
                }
            })
            .catch(function () {
                btn.disabled = false;
                btn.removeAttribute("aria-busy");
            });
    });

    /* ---- Tarix aralığı ------------------------------------------------- */

    function rangeParts(form) {
        return {
            from: form.querySelector('[data-ac-range-input="from"]'),
            to: form.querySelector('[data-ac-range-input="to"]'),
            appliedFrom: form.querySelector('[data-ac-range-applied="from"]'),
            appliedTo: form.querySelector('[data-ac-range-applied="to"]'),
            error: form.querySelector("[data-ac-range-error]"),
        };
    }

    /** Doğrulama: {ok, code} — code: "incomplete" | "bounds" | "order". ISO sətirlər leksik müqayisə olunur. */
    function validateRange(from, to, min, max) {
        if (!ISO_RE.test(from || "") || !ISO_RE.test(to || "")) {
            return { ok: false, code: "incomplete" };
        }
        if ((min && (from < min || to < min)) || (max && (from > max || to > max))) {
            return { ok: false, code: "bounds" };
        }
        if (from > to) {
            return { ok: false, code: "order" };
        }
        return { ok: true, code: "" };
    }

    function showRangeError(p, code) {
        if (!p.error) {
            return;
        }
        var text = code === "order" ? p.error.getAttribute("data-msg-order") : code === "bounds" ? p.error.getAttribute("data-msg-bounds") : "";
        p.error.textContent = text || "";
        p.error.hidden = !text;
        [p.from, p.to].forEach(function (input) {
            if (input) {
                input.setAttribute("aria-invalid", text ? "true" : "false");
            }
        });
    }

    function commitRange(form) {
        var p = rangeParts(form);
        if (!p.from || !p.to || !p.appliedFrom || !p.appliedTo) {
            return false;
        }
        var result = validateRange(p.from.value, p.to.value, p.from.getAttribute("min"), p.from.getAttribute("max"));
        showRangeError(p, result.code);
        if (!result.ok) {
            return false;
        }
        if (p.appliedFrom.value === p.from.value && p.appliedTo.value === p.to.value) {
            return false;
        }
        p.appliedFrom.value = p.from.value;
        p.appliedTo.value = p.to.value;
        if (window.EMSFilterBar) {
            window.EMSFilterBar.apply(form);
        }
        return true;
    }

    window.EMSDelegate.on("change", "[data-ac-root] [data-ac-range-input]", function (event, input) {
        var form = input.closest("form");
        if (!form) {
            return;
        }
        window.clearTimeout(rangeTimer);
        rangeTimer = window.setTimeout(function () {
            if (document.contains(form)) {
                commitRange(form);
            }
        }, RANGE_DEBOUNCE_MS);
    });

    window.EMSDelegate.on("keydown", "[data-ac-root] [data-ac-range-input]", function (event, input) {
        if (event.key !== "Enter") {
            return;
        }
        event.preventDefault(); // forma submit-i köhnə gizli dəyərlə tətbiq etməsin
        window.clearTimeout(rangeTimer);
        var form = input.closest("form");
        if (form) {
            commitRange(form);
        }
    });

    // «Ay» aralıqdan çıxanda / semestr dəyişəndə gizli tarixlər filtr panelinin tətbiqindən ƏVVƏL boşalsın (capture).
    window.EMSReady.once("ac-range-reset", function () {
        document.addEventListener(
            "change",
            function (event) {
                var select = event.target;
                if (!select || !select.matches) {
                    return;
                }
                // Semestr dəyişəndə köhnə tarixlər yeni semestrə sıxılmasın — server defolt aralığı qurur.
                var isSemester = select.matches('[data-ac-root] select[name="ac_semester"]');
                if (!isSemester && !select.matches('[data-ac-root] select[name="ac_month"]')) {
                    return;
                }
                if (!isSemester && select.value === "range") {
                    return;
                }
                var form = select.closest("form");
                var p = form ? rangeParts(form) : null;
                if (p && p.appliedFrom && p.appliedTo) {
                    p.appliedFrom.value = "";
                    p.appliedTo.value = "";
                }
            },
            true
        );
    });

    window.EMSAccounting = {
        openTeacher: openTeacher,
        validateRange: validateRange,
        commitRange: commitRange,
    };
})(window, document);
