/* =========================================================================
   ems_confirm.js — Qlobal, promise-based təsdiq dialoqu (EMSConfirm)

   YER: `static/js/` (kabinetin `ems_ui/` komponent qatında DEYİL) — bu utiliti
   kabinetdən kənar səhifələr də (imtahan, kurs, blog) işlədir və `base.html`-dən
   yüklənir; `ems_ui/` qatının asset/AJAX-safe müqaviləsi kabinet komponentlərinə aiddir.

   NİYƏ
   ----
   Layihədə 100+ native `confirm()` çağırışı var idi (UX audit UX-15) — hər
   ekranda fərqli görünür, əməliyyat thread-i bloklayır. Bu fayl TƏK bir
   Bootstrap 5 modal-ı (artıq layihədə geniş istifadə olunan komponent,
   markup: templates/partials/ems_ui/_confirm_modal.html) proqramla idarə
   edən kiçik köməkçidir.

   İSTİFADƏ
   --------
     EMSConfirm.open({
         title: "...",           // başlıq (məcburi deyil, boş ola bilər)
         body: "...",            // mətn (\n dəstəklənir — white-space: pre-line)
         confirmLabel: "...",    // defolt: dialoqun öz mətni ("Təsdiqlə")
         cancelLabel: "...",     // defolt: dialoqun öz mətni ("Ləğv et")
         danger: true|false,     // true → təsdiq düyməsi qırmızı (destruktiv əməl)
     }).then(function (ok) {
         if (ok) { / əməliyyatı davam etdir / }
     });

   Bootstrap yüklənməyibsə (nəzəri hal — bütün səhifələrdə qlobaldır) native
   `window.confirm()`-ə geri qayıdır ki, çağıran kod heç vaxt sınmasın.

   AJAX-SAFE: idempotent IIFE, `window.EMSConfirm` bir dəfə yaradılır; DOM
   elementləri hər `open()` çağırışında YENİDƏN oxunur (panel swap-dan sonra
   köhnə referans saxlanmır).
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSConfirm) {
        return; // idempotent
    }

    var MODAL_ID = "emsConfirmModal";
    var pendingResolve = null;
    var boundModalEl = null;

    function settle(result) {
        var resolve = pendingResolve;
        pendingResolve = null;
        if (resolve) {
            resolve(result);
        }
    }

    function bindOnce(modalEl, okBtn) {
        if (boundModalEl === modalEl) {
            return;
        }
        boundModalEl = modalEl;

        okBtn.dataset.emsDefaultLabel = okBtn.dataset.emsDefaultLabel || okBtn.textContent;

        okBtn.addEventListener("click", function () {
            settle(true);
            if (window.bootstrap && window.bootstrap.Modal) {
                var instance = window.bootstrap.Modal.getInstance(modalEl);
                if (instance) {
                    instance.hide();
                }
            }
        });

        // Ləğv et / X / scrim / Escape — hamısı Bootstrap-ın öz `hide()`-ı
        // ilə bura gətirir. Əgər OK artıq settle etmişdisə (pendingResolve
        // artıq null-dur) burda ikinci dəfə resolve OLMUR.
        modalEl.addEventListener("hidden.bs.modal", function () {
            settle(false);
        });
    }

    function open(options) {
        var opts = options || {};
        var modalEl = document.getElementById(MODAL_ID);
        var okBtn = modalEl && document.getElementById("emsConfirmOkBtn");
        var cancelBtn = modalEl && document.getElementById("emsConfirmCancelBtn");
        var titleEl = modalEl && document.getElementById("emsConfirmModalTitle");
        var bodyEl = modalEl && document.getElementById("emsConfirmModalBody");

        if (!modalEl || !okBtn || !cancelBtn || !titleEl || !bodyEl || !window.bootstrap || !window.bootstrap.Modal) {
            // Ehtiyat yolu — heç vaxt sınmasın (məs. testlərdə bootstrap.js yoxdursa).
            return Promise.resolve(window.confirm(opts.body || opts.title || ""));
        }

        // Əvvəlki açıq sorğu (nəzəri) ləğv sayılır.
        settle(false);

        bindOnce(modalEl, okBtn);

        cancelBtn.dataset.emsDefaultLabel = cancelBtn.dataset.emsDefaultLabel || cancelBtn.textContent;

        titleEl.textContent = opts.title || "";
        titleEl.hidden = !opts.title;
        bodyEl.textContent = opts.body || "";
        okBtn.textContent = opts.confirmLabel || okBtn.dataset.emsDefaultLabel;
        cancelBtn.textContent = opts.cancelLabel || cancelBtn.dataset.emsDefaultLabel;
        okBtn.className = "btn " + (opts.danger ? "btn-danger" : "btn-primary");

        return new Promise(function (resolve) {
            pendingResolve = resolve;
            window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
        });
    }

    window.EMSConfirm = { open: open };
})(window, document);
