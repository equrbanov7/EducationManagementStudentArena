/*
 * «Kadr analitikası» — panelin kiçik davranışları (sahib 2026-10-11).
 *
 * 1) KPI kartı → filtr: `nav.js` kartı klikləyəndə `ems:kpi-filter` hadisəsini atır; burada kartın
 *    açarı (`data-hr-kpi-map` JSON: {active: "active", blocked: "stopped", …}) `hr_status` select-inə
 *    yazılır və `filter_bar.js`-in tətbiq yolu çağırılır (URL + bölmənin yerində yenilənməsi).
 * 2) «Tarixçə» düyməsi sətrin altındakı gizli tarixçə sətrini açıb-bağlayır (aria-expanded).
 *
 * AJAX-safe: yalnız EMSDelegate (sənəd səviyyəsində, bir dəfə); `data-hr-root` olmayan panellərə
 * toxunmur. CSP: inline kod yoxdur, konfiqurasiya data-atributdan oxunur.
 */
(function (window, document) {
    "use strict";

    if (window.EMSHrAnalytics) {
        return;
    }

    function readMap(root) {
        try {
            return JSON.parse(root.getAttribute("data-hr-kpi-map") || "{}") || {};
        } catch (err) {
            return {};
        }
    }

    function applyStatus(root, value) {
        var form = root.querySelector("form[data-ems-filters]");
        var select = form ? form.querySelector('select[name="hr_status"]') : null;
        if (!form || !select) {
            return;
        }
        select.value = value || "";
        if (select.value !== (value || "")) {
            select.selectedIndex = 0; // tanınmayan dəyər → «Hamısı»
        }
        if (window.EMSBootstrapSelect) {
            window.EMSBootstrapSelect.sync(select);
        }
        if (window.EMSFilterBar) {
            window.EMSFilterBar.apply(form);
        } else {
            form.requestSubmit ? form.requestSubmit() : form.submit();
        }
    }

    document.addEventListener("ems:kpi-filter", function (event) {
        var btn = event.target;
        var root = btn && btn.closest ? btn.closest("[data-hr-root]") : null;
        if (!root) {
            return;
        }
        var key = event.detail ? event.detail.filter : null;
        var map = readMap(root);
        // Kart söndürüləndə (ikinci klik) və ya «Müəllimlər» kartında filtr götürülür.
        applyStatus(root, key && Object.prototype.hasOwnProperty.call(map, key) ? map[key] : "");
    });

    window.EMSDelegate.on("click", "[data-hr-history-toggle]", function (event, btn) {
        event.preventDefault();
        var id = btn.getAttribute("data-hr-history-toggle");
        var row = id ? document.getElementById(id) : null;
        if (!row) {
            return;
        }
        var open = row.hasAttribute("hidden");
        if (open) {
            row.removeAttribute("hidden");
        } else {
            row.setAttribute("hidden", "");
        }
        btn.setAttribute("aria-expanded", open ? "true" : "false");
        btn.classList.toggle("is-open", open);
    });

    window.EMSHrAnalytics = { applyStatus: applyStatus };
})(window, document);
