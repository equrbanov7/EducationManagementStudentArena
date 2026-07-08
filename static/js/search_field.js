/* Reusable search input (partials/_search_input.html) davranışı.
 *
 * Delegasiyalı dinləyicilər — səhifədəki (o cümlədən sonradan əlavə olunan)
 * bütün `.search-field`-lər üçün işləyir:
 *   • yazdıqca təmizlə (×) düyməsi görünür/gizlənir;
 *   • ×-a klik input-u təmizləyir və (formda olsa) formu göndərir.
 */
(function () {
    "use strict";

    function fieldOf(el) {
        return el && el.closest ? el.closest(".search-field") : null;
    }

    document.addEventListener("input", function (event) {
        var input = event.target;
        if (!input.classList || !input.classList.contains("search-field__input")) {
            return;
        }
        var field = fieldOf(input);
        var clear = field ? field.querySelector(".js-search-clear") : null;
        if (clear) {
            clear.hidden = !input.value;
        }
    });

    document.addEventListener("click", function (event) {
        var btn = event.target.closest ? event.target.closest(".js-search-clear") : null;
        if (!btn) {
            return;
        }
        event.preventDefault();
        var field = fieldOf(btn);
        var input = field ? field.querySelector(".search-field__input") : null;
        if (!input) {
            return;
        }
        input.value = "";
        btn.hidden = true;
        var form = input.form || (field ? field.closest("form") : null);
        if (form) {
            form.submit();
        } else {
            input.focus();
        }
    });
})();
