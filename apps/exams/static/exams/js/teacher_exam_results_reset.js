/*
 * teacher_exam_results_reset.js — «Nəticəni sil (cəhdi sıfırla)» (sahib 2026-11-04).
 *
 *  - Sətir düyməsi `.js-reset-attempt` → #resetAttemptsModal (tək cəhd, tələbənin adı ilə).
 *  - Seçilmişlər: `.js-reset-checkbox` + `[data-reset-selected]` → eyni modal (say ilə).
 *  - 2026-11-11: başlıq qutusu `[data-reset-page-all]` (səhifədəkilərin hamısı) və
 *    `[data-reset-all-matching]` («Bütün N nəticəni seç» — süzgəcə uyğun bütün səhifələr; modalda say +
 *    xəbərdarlıq; forma ID yox, `select_scope=all_matching` + süzgəc sorğusu + gözlənilən say daşıyır).
 *  - Qrup: `[data-reset-group-select]` + `[data-reset-group-open]` → ön baxış (JSON, EMSCore.fetchJSON)
 *    → #resetGroupModal; təsdiq düyməsi yalnız sıfırlanacaq cəhd varsa aktivdir.
 *  - Səbəb məcburidir (textarea `required` + `minlength`; server də yoxlayır).
 *
 * AJAX-safe: yalnız EMSDelegate (document səviyyəsi) + EMSReady (null-safe, idempotent sayğac).
 * Heç bir mətn burada yazılmır — bütün etiketlər şablondadır (i18n).
 */
(function () {
    "use strict";

    var CHECKBOX = ".js-reset-checkbox";

    function modalFor(element) {
        if (!element || !window.bootstrap || !window.bootstrap.Modal) {
            return null;
        }
        return window.bootstrap.Modal.getOrCreateInstance(element);
    }

    /* Sahib 2026-11-11: «Bütün N nəticəni seç» — cari süzgəcə uyğun bütün səhifələr. ID göndərilmir:
       forma `select_scope=all_matching` + süzgəc sorğusu + gözlənilən say daşıyır, siyahını server qurur. */
    var allMatching = false;

    function boxes() {
        return Array.prototype.slice.call(document.querySelectorAll(CHECKBOX));
    }

    function selectedIds() {
        return boxes()
            .filter(function (box) { return box.checked; })
            .map(function (box) { return box.value; });
    }

    function allButton() {
        return document.querySelector("[data-reset-all-matching]");
    }

    function matchingTotal() {
        var button = allButton();
        var total = parseInt(button ? button.getAttribute("data-total") : "", 10);
        return isFinite(total) ? total : 0;
    }

    function syncSelection() {
        var all = boxes();
        var checked = selectedIds().length;
        if (allMatching && (!allButton() || checked !== all.length)) {
            allMatching = false; // düymə yoxdur və ya sətir əl ilə dəyişib — yalnız işarəlilər qalır
        }
        var count = allMatching ? matchingTotal() : checked;
        var counter = document.querySelector("[data-reset-selected-count]");
        var button = document.querySelector("[data-reset-selected]");
        var header = document.querySelector("[data-reset-page-all]");
        var allBtn = allButton();
        if (counter) {
            counter.textContent = String(count);
        }
        if (button) {
            button.disabled = count === 0;
        }
        if (header) {
            header.checked = all.length > 0 && checked === all.length;
            header.indeterminate = checked > 0 && checked < all.length;
        }
        if (allBtn) {
            allBtn.setAttribute("aria-pressed", allMatching ? "true" : "false");
        }
    }

    function setPage(value) {
        boxes().forEach(function (box) { box.checked = value; });
    }

    function hiddenInput(name, value) {
        var input = document.createElement("input");
        input.type = "hidden";
        input.name = name;
        input.value = value;
        return input;
    }

    function openAttemptsModal(ids, studentLabel, everything) {
        var modalEl = document.getElementById("resetAttemptsModal");
        if (!modalEl || (!everything && !ids.length)) {
            return;
        }
        var inputs = modalEl.querySelector("[data-reset-inputs]");
        var one = modalEl.querySelector("[data-reset-one]");
        var many = modalEl.querySelector("[data-reset-many]");
        var name = modalEl.querySelector("[data-reset-name]");
        var count = modalEl.querySelector("[data-reset-count]");
        var note = modalEl.querySelector("[data-reset-all-note]");
        var reason = modalEl.querySelector("textarea[name='reason']");
        var total = everything ? matchingTotal() : ids.length;
        if (inputs) {
            inputs.textContent = "";
            if (everything) {
                var source = allButton();
                inputs.appendChild(hiddenInput("select_scope", "all_matching"));
                inputs.appendChild(hiddenInput("filter_query", source ? source.getAttribute("data-filter-query") || "" : ""));
                inputs.appendChild(hiddenInput("expected_count", String(total)));
            } else {
                ids.forEach(function (id) {
                    inputs.appendChild(hiddenInput("attempt_ids", id));
                });
            }
        }
        var single = !everything && ids.length === 1 && studentLabel;
        if (one) {
            one.hidden = !single;
        }
        if (name) {
            name.textContent = single ? studentLabel : "";
        }
        if (many) {
            many.hidden = !!single;
        }
        if (count) {
            count.textContent = String(total);
        }
        if (note) {
            note.hidden = !everything;
        }
        if (reason) {
            reason.value = "";
        }
        var modal = modalFor(modalEl);
        if (modal) {
            modal.show();
        }
    }

    function setField(root, field, value) {
        var node = root.querySelector("[data-field='" + field + "']");
        if (node) {
            node.textContent = value === undefined || value === null ? "" : String(value);
        }
    }

    function renderPreview(modalEl, payload) {
        var loading = modalEl.querySelector("[data-reset-group-loading]");
        var error = modalEl.querySelector("[data-reset-group-error]");
        var summary = modalEl.querySelector("[data-reset-group-summary]");
        var blockers = modalEl.querySelector("[data-reset-group-blockers]");
        var submit = modalEl.querySelector("[data-reset-group-submit]");
        if (loading) {
            loading.hidden = true;
        }
        var ok = payload && payload.ok;
        if (error) {
            error.hidden = !!ok;
            if (!ok && payload && payload.error) {
                error.textContent = payload.error;
            }
        }
        if (summary) {
            summary.hidden = !ok;
            if (ok) {
                ["group", "attempts", "students", "resettable", "blocked"].forEach(function (key) {
                    setField(summary, key, payload[key]);
                });
            }
        }
        if (blockers) {
            blockers.textContent = "";
            var list = ok && payload.blocker_list ? payload.blocker_list : [];
            list.forEach(function (item) {
                var li = document.createElement("li");
                li.textContent = item.label + ": " + item.count;
                blockers.appendChild(li);
            });
            blockers.hidden = list.length === 0;
        }
        if (submit) {
            submit.disabled = !(ok && payload.resettable > 0);
        }
    }

    function openGroupModal(card) {
        var modalEl = document.getElementById("resetGroupModal");
        var select = card.querySelector("[data-reset-group-select]");
        var url = card.getAttribute("data-preview-url");
        if (!modalEl || !select || !select.value || !url || !window.EMSCore) {
            return;
        }
        var hidden = modalEl.querySelector("[data-reset-group-value]");
        var reason = modalEl.querySelector("textarea[name='reason']");
        var loading = modalEl.querySelector("[data-reset-group-loading]");
        var submit = modalEl.querySelector("[data-reset-group-submit]");
        if (hidden) {
            hidden.value = select.value;
        }
        if (reason) {
            reason.value = "";
        }
        if (submit) {
            submit.disabled = true;
        }
        ["[data-reset-group-error]", "[data-reset-group-summary]", "[data-reset-group-blockers]"].forEach(function (sel) {
            var node = modalEl.querySelector(sel);
            if (node) {
                node.hidden = true;
            }
        });
        if (loading) {
            loading.hidden = false;
        }
        var modal = modalFor(modalEl);
        if (modal) {
            modal.show();
        }
        var target = url + (url.indexOf("?") === -1 ? "?" : "&") + "group=" + encodeURIComponent(select.value);
        window.EMSCore.fetchJSON(target).then(function (payload) {
            renderPreview(modalEl, payload);
        }).catch(function (err) {
            renderPreview(modalEl, err && err.payload && typeof err.payload === "object" ? err.payload : { ok: false });
        });
    }

    function bind() {
        if (!window.EMSDelegate) {
            return;
        }
        window.EMSDelegate.on("click", ".js-reset-attempt", function (event, button) {
            event.preventDefault();
            openAttemptsModal([button.getAttribute("data-attempt-id")], button.getAttribute("data-student") || "");
        });
        window.EMSDelegate.on("change", CHECKBOX, syncSelection);
        // Köhnə «Hamısını seç / Seçimi sıfırla» qutuları proqramla dəyişir (change hadisəsi yoxdur).
        window.EMSDelegate.on("click", "#selectAllAttemptsBtn, #clearAttemptsBtn", function () {
            window.setTimeout(syncSelection, 0);
        });
        window.EMSDelegate.on("change", "[data-reset-page-all]", function (event, header) {
            allMatching = false;
            setPage(!!header.checked);
            syncSelection();
        });
        window.EMSDelegate.on("click", "[data-reset-all-matching]", function (event) {
            event.preventDefault();
            var enable = !allMatching;
            setPage(enable);
            allMatching = enable;
            syncSelection();
        });
        window.EMSDelegate.on("click", "[data-reset-selected]", function (event) {
            event.preventDefault();
            openAttemptsModal(selectedIds(), "", allMatching);
        });
        window.EMSDelegate.on("change", "[data-reset-group-select]", function (event, select) {
            var card = select.closest("[data-reset-group-card]");
            var button = card ? card.querySelector("[data-reset-group-open]") : null;
            if (button) {
                button.disabled = !select.value;
            }
        });
        window.EMSDelegate.on("click", "[data-reset-group-open]", function (event, button) {
            event.preventDefault();
            var card = button.closest("[data-reset-group-card]");
            if (card) {
                openGroupModal(card);
            }
        });
        // İkiqat göndərişin qarşısı: forma etibarlıdırsa göndəriş düyməsi bağlanır.
        window.EMSDelegate.on("submit", "[data-reset-form], [data-reset-group-form]", function (event, form) {
            var submit = form.querySelector("button[type='submit']");
            if (submit) {
                window.setTimeout(function () { submit.disabled = true; }, 0);
            }
        });
    }

    if (window.EMSReady) {
        window.EMSReady.once("etr-attempt-reset", bind);
        window.EMSReady(syncSelection);
    }
})();
