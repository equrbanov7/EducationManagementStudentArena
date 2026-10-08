/* =========================================================================
   workbench_default_a.js — «Düzgün cavab həmişə A variantıdır» (müəllim rəyi S1, 2026-10-08).

   Toplu sual workbench-i (sual göndərişi). Müəllim 50 sual yükləyib; hamısında
   düzgün cavab A idi, amma hər biri «düzgün cavab işarəsi tapılmadı» deyirdi.
     • Yükləmə panelindəki seçim [data-wb-default-a] — önizləmədə server işarəsiz
       sualların A variantını mətndə «*A)» edir (core: parsing/answer_markers.py).
       Nəticə artıq görünürkən seçim işarələnsə önizləmə dərhal təkrarlanır ki,
       göndərilən mətn də işarəli olsun.
     • «Hamısını təsdiqlə — A düzgündür (N)» [data-wb-confirm-default-a] — təsdiqdən
       sonra eyni seçimlə önizləməni təkrarlayır.
   AJAX-safe: EMSDelegate (document səviyyəsində, bir dəfə); inline JS yoxdur.
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.__emsWorkbenchDefaultA) {
        return;
    }
    window.__emsWorkbenchDefaultA = true;

    function previewForm(node) {
        var wrap = (node && node.closest && node.closest(".bulk-page-wrapper")) || document;
        return wrap.querySelector("form.split-layout");
    }

    function rerunPreview(node) {
        var form = previewForm(node);
        if (!form) {
            return;
        }
        var box = form.querySelector("[data-wb-default-a]");
        if (box) {
            box.checked = true;
        }
        if (form.requestSubmit) {
            form.requestSubmit();
        } else {
            form.submit();
        }
    }

    function onConfirmAll(event, button) {
        event.preventDefault();
        var text = button.getAttribute("data-confirm-text") || "";
        if (window.EMSConfirm && typeof window.EMSConfirm.open === "function") {
            window.EMSConfirm.open({ title: "", body: text, danger: false }).then(function (ok) {
                if (ok) {
                    rerunPreview(button);
                }
            });
        } else if (window.confirm(text)) {
            rerunPreview(button);
        }
    }

    function onToggle(event, box) {
        if (box.checked && document.querySelector(".results-container")) {
            rerunPreview(box);
        }
    }

    function bind() {
        if (!window.EMSDelegate || typeof window.EMSDelegate.on !== "function") {
            return;
        }
        window.EMSDelegate.on("click", "[data-wb-confirm-default-a]", onConfirmAll);
        window.EMSDelegate.on("change", "[data-wb-default-a]", onToggle);
    }

    bind();
})(window, document);
