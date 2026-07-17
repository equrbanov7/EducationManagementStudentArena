/* «İmtahan şansı ver» — filtr formunun avto-submit-i.
 *
 * Select dəyişən kimi forma göndərilir (fakültə dəyişəndə kafedra sıfırlanır —
 * server onsuz da yad kafedranı rədd edir, URL təmiz qalsın); axtarış
 * inputları (imtahan + tələbə) 500ms debounce ilə göndərilir.
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

    var timers = new WeakMap();

    function submitForm(form) {
        if (typeof form.requestSubmit === "function") {
            form.requestSubmit();
        } else {
            form.submit();
        }
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

    document.addEventListener("input", function (event) {
        var input = event.target;
        if (!input || !input.matches || !input.matches("form.js-exch-filter input[data-exch-debounce]")) {
            return;
        }
        var form = input.closest("form.js-exch-filter");
        window.clearTimeout(timers.get(input));
        timers.set(
            input,
            window.setTimeout(function () {
                submitForm(form);
            }, 500)
        );
    });

    document.addEventListener("keydown", function (event) {
        if (event.key !== "Enter") {
            return;
        }
        var input = event.target;
        if (input && input.matches && input.matches("form.js-exch-filter input[data-exch-debounce]")) {
            event.preventDefault();
            window.clearTimeout(timers.get(input));
            submitForm(input.closest("form.js-exch-filter"));
        }
    });
})();
