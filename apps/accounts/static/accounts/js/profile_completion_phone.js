/*
 * profile_completion_phone.js
 * Source: apps/accounts/templates/accounts/profile_completion.html
 * «Məlumatlarınızı tamamlayın» — telefon: operator (050, 055 …) seçilir, xanaya qalan 7 rəqəm yazılır.
 * «Xarici nömrə» seçiləndə placeholder tam beynəlxalq formata keçir. Server həmişə özü yoxlayır
 * (apps/accounts/profile_completion.py::combine_phone) — bu yalnız ipucudur.
 * NOTE: base_auth.html ems_ajax_init.js yükləmir (EMSReady yoxdur), səhifə AJAX ilə dəyişmir — sadə IIFE.
 */
(function () {
    "use strict";
    var box = document.querySelector("[data-pc-phone]");
    if (!box || box.dataset.pcPhoneReady === "1") {
        return;
    }
    box.dataset.pcPhoneReady = "1";
    var select = box.querySelector("[data-pc-phone-operator]");
    var input = box.querySelector("[data-pc-phone-input]");
    if (!select || !input) {
        return;
    }
    function sync() {
        var other = select.value === box.dataset.other;
        input.placeholder = other ? box.dataset.placeholderOther : box.dataset.placeholderLocal;
        box.classList.toggle("pc-phone--other", other);
    }
    select.addEventListener("change", sync);
    sync();
})();
