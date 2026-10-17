/* «Sual təsdiqi» bölməsi — KPI kartı → status filtri (Paket C 2026-10-17).
 *
 * KPI kartına klik (`ems:kpi-filter`, `ems_ui/nav.js`) filtr panelinin `qchair_status`
 * seçicisini dəyişir və AVTO tətbiqi işə salır — kart və select eyni vəziyyəti göstərir
 * (tək həqiqət mənbəyi URL-dir). «Sual göndərişləri» bölməsi ilə eyni naxış.
 *
 * AJAX-SAFE: document səviyyəsində bir dəfə (`EMSReady.once`); panel swap olunsa da
 * dinləyici yığılmır, kök tapılmasa heç nə etmir.
 */
(function () {
    "use strict";

    function bind() {
        document.addEventListener("ems:kpi-filter", function (event) {
            var root = event.target && event.target.closest ? event.target.closest("[data-qchair-root]") : null;
            if (!root) {
                return;
            }
            var form = root.querySelector("[data-ems-filters]");
            var select = form ? form.querySelector('select[name="qchair_status"]') : null;
            if (!form || !select || !window.EMSFilterBar) {
                return;
            }
            var wanted = event.detail && event.detail.filter ? event.detail.filter : "";
            select.value = wanted === "all" ? "" : wanted;
            if (window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(select);
            }
            window.EMSFilterBar.apply(form);
        });
    }

    if (window.EMSReady && window.EMSReady.once) {
        window.EMSReady.once("qchair-kpi-status-filter", bind);
    }
})();
