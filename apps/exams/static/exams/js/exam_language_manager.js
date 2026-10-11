/* =========================================================================
   exam_language_manager.js — «Dil variantları» səhifəsi (sahib 2026-10-10).

   Aktiv sətirdəki «Deaktiv et» birbaşa göndərilmir: EMSConfirm dialoqu
   (təhlükə tonu, düymə mətni əməlin adıdır) təsdiq istəyir; ləğvdə fokus
   düyməyə qayıdır. «Aktiv et» zərərsizdir — təsdiqsiz göndərilir.
   Mətnlər serverdən data-atributlarla gəlir (tərcümə olunur).
   AJAX-safe: EMSDelegate (document-ə bir dəfə); EMSConfirm yoxdursa forma
   adi qaydada göndərilir (heç vaxt sınmır).
   ========================================================================= */
(function () {
    "use strict";

    function onDeactivateClick(event, button) {
        var form = button.form;
        if (!form || !window.EMSConfirm) {
            return;
        }
        event.preventDefault();
        window.EMSConfirm.open({
            title: button.getAttribute("data-confirm-title") || "",
            body: button.getAttribute("data-confirm-body") || "",
            confirmLabel: button.getAttribute("data-confirm-label") || "",
            danger: true
        }).then(function (ok) {
            if (!ok) {
                button.focus();
                return;
            }
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit(button);
            } else {
                form.submit();
            }
        });
    }

    if (window.EMSDelegate) {
        window.EMSDelegate.on("click", "[data-elm-deactivate]", onDeactivateClick);
    }
})();
