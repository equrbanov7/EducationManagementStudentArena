/*
 * my_results_filters.js
 * Source: apps/accounts/templates/accounts/profile/sections/_my_results.html
 *
 * "Nəticələrim" — akademik (jurnal) fənn nəticələrinin il/semestr süzgəci.
 * Select dəyişəndə forma GET ilə göndərilir (süzgəc + səhifələmə server tərəflidir).
 * `bootstrap_select.js` seçim dəyişəndə native select üzərində `change` yayımlayır,
 * ona görə delegasiya kifayətdir.
 *
 * AJAX-safe: `EMSDelegate.on` sənəd səviyyəsində (event+selector üzrə idempotent)
 * bağlanır, `EMSReady.once` isə panel hər swap-da yenidən icra olunanda təkrar
 * qeydiyyatın qarşısını alır. Script teqi `defer`-lidir — `ems_ajax_init.js`
 * base.html-də məzmundan SONRA yüklənir, defer olmasa EMSDelegate hələ mövcud olmur.
 */
(function () {
    "use strict";

    function submitFilterForm(select) {
        var form = select && typeof select.closest === "function" ? select.closest("form[data-my-results-filter-form]") : null;
        if (!form) {
            return;
        }
        if (typeof form.requestSubmit === "function") {
            form.requestSubmit();
            return;
        }
        form.submit();
    }

    function bind() {
        if (!window.EMSDelegate || typeof window.EMSDelegate.on !== "function") {
            return;
        }
        window.EMSDelegate.on("change", "[data-my-results-filter]", function (event) {
            submitFilterForm(event.target);
        });
    }

    if (window.EMSReady && typeof window.EMSReady.once === "function") {
        window.EMSReady.once("accounts.my_results_filters", bind);
    } else if (window.EMSReady) {
        window.EMSReady(bind);
    } else {
        document.addEventListener("DOMContentLoaded", bind);
    }
})();
