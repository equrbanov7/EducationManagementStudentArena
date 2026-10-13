/*
 * profile_auto_filter_form.js
 * Source: extracted verbatim from the inline <script> shared by
 *   _pending_review_content.html, _review_results_content.html and
 *   _pending_answers_content.html (CSP inline-removal, 2026-07).
 * Auto-submits any [data-auto-filter-form] on text input, Enter, or select change.
 *
 * 2026-10-14 (sahib: «yazarkən search gedir, render olur, axtardığım itir»):
 * mətn sahəsi vahid EMSSearchInput qaydası ilə — yazı dayananda 1500 ms,
 * ≥ 2 simvol, Enter dərhal, IME gözlənilir; göndəriş `submitForm` ilədir
 * (kabinetdə «quiet» bölmə yükləməsi — input əvəzlənmir, fokus qalır).
 * Dinləyicilər delegasiyalıdır (element-ə bağlanmır) → AJAX swap-dan sonra da
 * işləyir və yığılmır.
 */
(function () {
    "use strict";

    var FORM = "form[data-auto-filter-form]";
    var TEXT = FORM + ' input[type="text"], ' + FORM + ' input[type="search"]';

    function submit(form, input) {
        if (window.EMSSearchInput && window.EMSSearchInput.submitForm) {
            window.EMSSearchInput.submitForm(form, { input: input || null });
        } else if (typeof form.requestSubmit === "function") {
            form.requestSubmit();
        } else {
            form.submit();
        }
    }

    window.EMSSearchInput.delegate(TEXT, {
        onSearch: function (value, meta) {
            if (meta.input.form) {
                submit(meta.input.form, meta.input);
            }
        },
    });

    window.EMSDelegate.on("change", FORM + " select", function (event, select) {
        if (select.form) {
            submit(select.form, null);
        }
    });
})();
