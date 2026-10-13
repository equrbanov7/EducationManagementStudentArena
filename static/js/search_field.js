/* Reusable search input (partials/_search_input.html) davranışı.
 *
 * Delegasiyalı dinləyicilər — səhifədəki (o cümlədən sonradan əlavə olunan)
 * bütün `.search-field`-lər üçün işləyir:
 *   • yazdıqca təmizlə (×) düyməsi görünür/gizlənir;
 *   • ×-a klik input-u təmizləyir və (formda olsa) formu göndərir; input vahid
 *     EMSSearchInput qaydası ilə idarə olunursa səhifə yenilənmədən sıfırlanır.
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
        btn.hidden = true;
        // 2026-10-14: vahid EMSSearchInput idarə edirsə — səhifə yenilənmədən dərhal
        // sıfırlanır (input yerində qalır, fokus input-da).
        if (window.EMSSearchInput && window.EMSSearchInput.clear(input)) {
            input.focus();
            return;
        }
        input.value = "";
        var form = input.form || (field ? field.closest("form") : null);
        if (form) {
            form.submit();
        } else {
            input.focus();
        }
    });
})();
