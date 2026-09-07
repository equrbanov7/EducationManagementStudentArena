/* «Müraciətlərim» — TARİX ARALIĞI süzgəci (göndərilmə tarixi üzrə).
 *
 * Niyə ayrı fayl? `applications.js` ölçü büdcəsinin (600 sətir) yaxınlığındadır;
 * süzgəcin öz qeydiyyatları burada saxlanılır. Vəziyyət eyni yerdədir
 * (`NS.state.from` / `NS.state.to`) və sorğuya `applications.js`-in `loadList`
 * funksiyası göndərir — bu fayl yalnız DOM ↔ vəziyyət sinxronudur.
 *
 * Server dəyəri fail-soft oxuyur (`views.endpoints._date_param`): yararsız
 * tarix süzgəci sadəcə söndürür, sorğunu qırmır.
 */
(function () {
    "use strict";

    var NS = (window.EMSApplications = window.EMSApplications || {});

    function input(which) {
        return NS.root && NS.root.querySelector("[data-apx-date-" + which + "]");
    }

    /* Vəziyyət → DOM (sıfırlama və swap-dan sonra) + «təmizlə» düyməsinin görünüşü. */
    function sync() {
        var from = input("from");
        var to = input("to");
        if (from) {
            from.value = NS.state.from || "";
        }
        if (to) {
            to.value = NS.state.to || "";
        }
        var clear = NS.root && NS.root.querySelector("[data-apx-dates-clear]");
        if (clear) {
            clear.hidden = !(NS.state.from || NS.state.to);
        }
        var box = NS.root && NS.root.querySelector("[data-apx-dates]");
        if (box) {
            box.classList.toggle("is-active", !!(NS.state.from || NS.state.to));
        }
    }

    /* DOM → vəziyyət → yenidən yüklə. Bir uc boş qala bilər: «filan tarixdən
     * sonra» / «filan tarixə qədər» də qanuni aralıqdır. */
    function apply() {
        var from = input("from");
        var to = input("to");
        NS.state.from = from ? from.value : "";
        NS.state.to = to ? to.value : "";
        NS.state.page = 1;
        sync();
        NS.loadList();
    }

    function reset() {
        NS.state.from = "";
        NS.state.to = "";
        sync();
    }

    NS.filters = { sync: sync, apply: apply, reset: reset };

    function start() {
        if (NS.__filtersWired) {
            return;
        }
        NS.__filtersWired = true;

        window.EMSDelegate.on("change", "[data-apx-date-from]", apply);
        window.EMSDelegate.on("change", "[data-apx-date-to]", apply);
        window.EMSDelegate.on("click", "[data-apx-dates-clear]", function () {
            reset();
            NS.state.page = 1;
            NS.loadList();
        });
        // Swap-dan sonra panel yeni DOM-la gəlir — seçilmiş aralıq görünsün.
        window.EMSReady(function () {
            if (NS.state) {
                sync();
            }
        });
    }

    /* Panel script-ləri `<body>` içindədir və `ems_ajax_init.js`-dən ƏVVƏL
     * parse oluna bilər; qeydiyyat primitivlər hazır olana qədər gözləyir. */
    (function ready(attempt) {
        if (window.EMSDelegate && window.EMSReady) {
            start();
            return;
        }
        if (attempt > 200) {
            return;
        }
        window.setTimeout(function () {
            ready(attempt + 1);
        }, 25);
    })(0);
})();
