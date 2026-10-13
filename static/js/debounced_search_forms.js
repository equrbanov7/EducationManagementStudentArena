/* debounced_search_forms.js — ümumi GET axtarış formaları (adında «search»
   olan mətn sahəsi) yazdıqca, select-lər isə dəyişən kimi göndərilir.

   2026-10-14 (sahib: «debounce düzgün işləmir, çox sürətli olur; yazarkən
   search gedir, render olur, axtardığım itir»): öz 1000 ms taymeri silindi —
   vahid EMSSearchInput qaydası (yazı DAYANANDAN 1500 ms sonra, ≥ 2 simvol,
   Enter dərhal, IME gözlənilir, dəyişməyən dəyər göndərilmir). Göndəriş
   `EMSSearchInput.submitForm` ilədir: kabinet bölməsində «quiet» AJAX yükləmə
   (input əvəzlənmir, fokus/kursor qalır), tam səhifədə adi göndəriş + fokus
   bərpası. Dinləyicilər document səviyyəsindədir → AJAX swap-dan sonra
   yenidən bağlamaq lazım deyil (`EMSDebouncedSearchForms.init` uyğunluq üçün
   no-op olaraq qalır).

   Öz axtarış JS-i olan formalar burada İŞLƏNMİR: `[data-auto-filter-form]`
   (profile_auto_filter_form.js), `.js-profile-debounce-search` (profile/ui.js),
   `[data-ems-filters]` (ems_ui/filter_bar.js), `[data-ems-search-own]`. */
(function () {
    "use strict";

    var SKIP = ":not([data-auto-filter-form]):not([data-ems-filters]):not([data-ems-search-own])";
    var GET_FORM = "form" + SKIP + ':not([method="post" i])';
    var TEXT = GET_FORM + ':not(.js-profile-debounce-search) input[name*="search" i]';

    function submit(form, input) {
        window.EMSSearchInput.submitForm(form, { input: input || null });
    }

    window.EMSSearchInput.delegate(TEXT + '[type="text"], ' + TEXT + '[type="search"]', {
        fallback: true, // öz JS-i olan sahə (EMSSearchInput qeydiyyatı) üstündür
        onSearch: function (value, meta) {
            if (meta.input.form) {
                submit(meta.input.form, meta.input);
            }
        },
    });

    function hasSearchInput(form) {
        var inputs = form.querySelectorAll('input[name][type="text"], input[name][type="search"]');
        for (var i = 0; i < inputs.length; i += 1) {
            if (/search/i.test(inputs[i].name || "")) {
                return true;
            }
        }
        return false;
    }

    window.EMSDelegate.on("change", GET_FORM + " select[name]", function (event, select) {
        var form = select.form;
        if (!form || select.disabled || select.hasAttribute("data-no-auto-submit")) {
            return;
        }
        if (hasSearchInput(form) || form.hasAttribute("data-auto-submit-selects")) {
            if (window.EMSSearchInput.cancel) {
                form.querySelectorAll("input").forEach(window.EMSSearchInput.cancel);
            }
            submit(form, null);
        }
    });

    // Uyğunluq: profile/section_loader.js swap-dan sonra çağırır — artıq lazım deyil.
    window.EMSDebouncedSearchForms = { init: function () {} };
})();
