/* Qrupun «ilk giriş» çap vərəqi — «Çap et» düyməsi (inline onclick yoxdur, CSP). */
(function () {
    "use strict";

    function init() {
        var button = document.querySelector("[data-actsheet-print]");
        if (!button || button.dataset.actsheetInit === "1") {
            return;
        }
        button.dataset.actsheetInit = "1";
        button.addEventListener("click", function () {
            window.print();
        });
    }

    if (typeof window.EMSReady === "function") {
        window.EMSReady(init);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
