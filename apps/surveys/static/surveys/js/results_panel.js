/* =========================================================================
   results_panel.js — «Sorğu nəticələri» bölməsinin açılışı (AJAX-safe)

   * Panelin qrafiklərini JSON adalarından çəkir (`EMSSurveyResults.charts`).
   * Filtr panelinin müəllim sahəsi: SERVER axtarışlı seçici (`EMSSearchableSelect`,
     dözümlü ad axtarışı). Seçim gizli `er_teacher` `[data-ems-filter]` sahəsinə
     yazılır və `change` hadisəsi atılır — `filter_bar.js` avto rejimdə bölməni
     yerində yenidən yükləyir (URL sinxron qalır).
   * `EMSReady` hər swap-dan sonra işləyir; kök elementin `data-svr-init`
     bayrağı ikiqat açılışın qarşısını alır. Skriptlərin icra sırası AJAX-da
     zəmanətli olmadığı üçün nüvə/qrafik modulları qısa müddət gözlənilir.
   ========================================================================= */
(function (window, document) {
    "use strict";

    var NS = (window.EMSSurveyResults = window.EMSSurveyResults || {});
    if (NS.panel) {
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

    function initPicker(root) {
        var host = root.querySelector("[data-svr-teacher-picker]");
        var input = root.querySelector("#f-er_teacher");
        if (!host || !input || host.dataset.svrReady === "1" || !window.EMSSearchableSelect) {
            return;
        }
        var el = host.querySelector(".js-svr-teacher");
        if (!el) {
            return;
        }
        host.dataset.svrReady = "1";
        var t = root.dataset;
        var booting = true;
        var pick = window.EMSSearchableSelect.create(el, {
            url: host.dataset.url,
            multi: false,
            skeleton: true,
            emptyText: t.i18nEmptyTeacher,
            removeLabel: t.i18nRemove,
            onChange: function () {
                if (booting || !pick) {
                    return;
                }
                var value = pick.value();
                if (input.value === value) {
                    return;
                }
                input.value = value;
                input.dispatchEvent(new Event("change", { bubbles: true }));
            }
        });
        if (pick && host.dataset.value) {
            pick.setValue(host.dataset.value, host.dataset.text || host.dataset.value);
        }
        booting = false;
    }

    function boot() {
        document.querySelectorAll(".svr[data-svr-root]").forEach(function (root) {
            if (root.dataset.svrInit === "1") {
                return;
            }
            root.dataset.svrInit = "1";
            root.querySelectorAll("[data-svr-charts]").forEach(function (container) {
                NS.charts.render(container);
            });
            initPicker(root);
        });
    }

    window.EMSReady(function () {
        whenReady(boot);
    });

    NS.panel = { boot: boot };
})(window, document);
