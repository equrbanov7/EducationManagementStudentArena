/* «İmtahan şansı ver» — filtr formunun avto-submit-i.
 *
 * Select dəyişən kimi forma göndərilir (fakültə dəyişəndə kafedra sıfırlanır —
 * server onsuz da yad kafedranı rədd edir, URL təmiz qalsın); axtarış
 * inputları (imtahan + tələbə) vahid EMSSearchInput qaydası ilə (2026-10-14:
 * yazı dayananda 1500 ms, ≥ 2 simvol, Enter dərhal, IME) — göndəriş «quiet»
 * bölmə yükləməsidir: input əvəzlənmir, fokus və yazılan hərflər qalır.
 *
 * QEYD: profil SPA-sı bölmə swap-ında paneldəki <script> taqlarını yenidən
 * icra edir — dinləyicilər document səviyyəsində DELEGATED qoşulur və qlobal
 * bayraqla ikiqat qoşulma önlənir (CSP: inline handler yoxdur).
 */
(function () {
    "use strict";

    if (window.__exchInit) {
        return;
    }
    window.__exchInit = true;

    function submitForm(form, input) {
        window.EMSSearchInput.submitForm(form, { input: input || null });
    }

    document.addEventListener("change", function (event) {
        var select = event.target;
        if (!select || select.tagName !== "SELECT") {
            return;
        }
        var form = select.closest("form.js-exch-filter");
        if (!form) {
            return;
        }
        if (select.classList.contains("js-exch-faculty")) {
            var kafedra = form.querySelector('select[name="chance_kafedra"]');
            if (kafedra) {
                kafedra.value = "";
            }
        }
        submitForm(form);
    });

    window.EMSSearchInput.delegate("form.js-exch-filter input[data-exch-debounce]", {
        onSearch: function (value, meta) {
            submitForm(meta.input.closest("form.js-exch-filter"), meta.input);
        },
    });
})();
