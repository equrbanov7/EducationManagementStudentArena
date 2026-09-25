/* =========================================================================
   results_print.js — müəllim kartının çap səhifəsi: qrafikləri çəkir, «Çap et»
   düyməsi, çapdan əvvəl bütün cədvəl qarşılıqlarını (<details>) və şərhləri
   açır, qrafikləri kağız eninə uyğunlaşdırır. Animasiya çapda söndürülür.
   ========================================================================= */
(function (window, document) {
    "use strict";

    var NS = (window.EMSSurveyResults = window.EMSSurveyResults || {});
    if (NS.print) {
        return;
    }

    function whenReady(fn, attempt) {
        if (NS.core && NS.charts) {
            fn();
            return;
        }
        if ((attempt || 0) > 150) {
            return;
        }
        window.setTimeout(function () {
            whenReady(fn, (attempt || 0) + 1);
        }, 30);
    }

    function prepare() {
        document.querySelectorAll(".svr-print details").forEach(function (details) {
            details.open = true;
        });
        if (NS.text) {
            document.querySelectorAll(".svr-print [data-svr-text]").forEach(NS.text.reveal);
        }
        document.querySelectorAll(".svr-print canvas").forEach(function (canvas) {
            if (canvas._svrChart) {
                canvas._svrChart.options.animation = false;
                canvas._svrChart.resize();
            }
        });
    }

    window.EMSReady(function () {
        whenReady(function () {
            document.querySelectorAll(".svr-print [data-svr-charts]").forEach(function (container) {
                if (container.dataset.svrPrintInit !== "1") {
                    container.dataset.svrPrintInit = "1";
                    NS.charts.render(container);
                }
            });
        });
    });

    window.EMSDelegate.on("click", "[data-svr-print]", function (event) {
        event.preventDefault();
        prepare();
        window.setTimeout(function () {
            window.print();
        }, 150);
    });

    window.EMSReady.once("svr-beforeprint", function () {
        window.addEventListener("beforeprint", prepare);
    });

    NS.print = { prepare: prepare };
})(window, document);
