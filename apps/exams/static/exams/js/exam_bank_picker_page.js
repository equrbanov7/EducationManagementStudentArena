/*
 * exam_bank_picker_page.js — müstəqil «Bankdan sual əlavə et» səhifəsi (2026-10-10 redizayn).
 *
 *  - Filtrlər dəyişəndə dərhal tətbiq olunur (seçicilər — change; axtarış — 500 ms debounce).
 *  - Seçim: «N sual seçildi» sayğacı (aria-live), «Bu səhifədəkiləri seç», «Bütün N sualı seç»
 *    (serverin mövcud rejimi: select_all=1 + görünən səhifədə seçimdən çıxarılanlar excluded_ids),
 *    «Təmizlə». Seçim yoxdursa «Seçilənləri əlavə et» söndürülür.
 *
 * AJAX-safe: hadisələr EMSDelegate ilə document-ə bir dəfə; ilkin vəziyyət EMSReady ilə.
 */
(function () {
    "use strict";


    function attachForm(node) {
        return (node && node.closest && node.closest("[data-ebp-attach]")) || document.querySelector("[data-ebp-attach]");
    }

    function boxes(form) {
        return Array.prototype.slice.call(form.querySelectorAll("[data-ebp-check]:not(:disabled)"));
    }

    function selectAllInput(form) {
        return form.querySelector("[data-ebp-select-all-input]");
    }

    function isSelectAll(form) {
        var input = selectAllInput(form);
        return !!(input && input.value === "1");
    }

    function setSelectAll(form, on) {
        var input = selectAllInput(form);
        if (input) {
            input.value = on ? "1" : "";
        }
    }

    function writeExcluded(form, list, selectAll) {
        var holder = form.querySelector("[data-ebp-excluded]");
        if (!holder) {
            return;
        }
        holder.textContent = "";
        if (!selectAll) {
            return;
        }
        list.forEach(function (box) {
            if (box.checked) {
                return;
            }
            var hidden = document.createElement("input");
            hidden.type = "hidden";
            hidden.name = "excluded_ids";
            hidden.value = box.value;
            holder.appendChild(hidden);
        });
    }

    function sync(form) {
        if (!form) {
            return;
        }
        var list = boxes(form);
        var checked = list.filter(function (box) { return box.checked; }).length;
        var total = parseInt(form.getAttribute("data-total"), 10) || 0;
        var selectAll = isSelectAll(form);
        var count = selectAll ? Math.max(0, total - (list.length - checked)) : checked;

        writeExcluded(form, list, selectAll);

        var submit = form.querySelector("[data-ebp-submit]");
        var label = form.querySelector("[data-ebp-count]");
        if (label) {
            var template = form.getAttribute("data-count-template") || "{n}";
            label.textContent = count ? template.replace("{n}", String(count)) :
                ((submit && submit.getAttribute("data-empty-label")) || "0");
        }
        if (submit) {
            submit.disabled = count === 0;
        }
        var pageToggle = form.querySelector("[data-ebp-page-toggle]");
        if (pageToggle) {
            pageToggle.checked = list.length > 0 && checked === list.length;
            pageToggle.indeterminate = checked > 0 && checked < list.length;
        }
        var allButton = form.querySelector("[data-ebp-select-all]");
        if (allButton) {
            allButton.setAttribute("aria-pressed", selectAll ? "true" : "false");
        }
    }

    function setPage(form, value) {
        boxes(form).forEach(function (box) {
            box.checked = value;
        });
    }

    function submitFilters(control) {
        var form = control.form;
        if (!form) {
            return;
        }
        if (typeof form.requestSubmit === "function") {
            form.requestSubmit();
        } else {
            form.submit();
        }
    }

    if (window.EMSDelegate) {
        window.EMSDelegate.on("change", "[data-ebp-check]", function (event, box) {
            sync(attachForm(box));
        });
        window.EMSDelegate.on("change", "[data-ebp-page-toggle]", function (event, toggle) {
            var form = attachForm(toggle);
            if (!toggle.checked) {
                setSelectAll(form, false);
            }
            setPage(form, toggle.checked);
            sync(form);
        });
        window.EMSDelegate.on("click", "[data-ebp-select-all]", function (event, button) {
            var form = attachForm(button);
            setSelectAll(form, true);
            setPage(form, true);
            sync(form);
        });
        window.EMSDelegate.on("click", "[data-ebp-clear]", function (event, button) {
            var form = attachForm(button);
            setSelectAll(form, false);
            setPage(form, false);
            sync(form);
        });
        window.EMSDelegate.on("change", "[data-ebp-auto]", function (event, control) {
            submitFilters(control);
        });
    }
    // 2026-10-14: vahid EMSSearchInput (1500 ms, ≥ 2 simvol, Enter dərhal, IME); yeni
    // səhifədə fokus + kursor axtarış sahəsinə qayıdır.
    if (window.EMSSearchInput) {
        window.EMSSearchInput.delegate("[data-ebp-search]", {
            onSearch: function (value, meta) {
                if (meta.input.form) {
                    window.EMSSearchInput.submitForm(meta.input.form, { input: meta.input });
                }
            },
        });
    }

    if (window.EMSReady) {
        window.EMSReady(function () {
            sync(document.querySelector("[data-ebp-attach]"));
        });
    }
})();
