/* Embed (standalone) səhifələr üçün profil sidebar aktivasiyası.
 *
 * SPA-da akkordeonu init.js qurur, amma o, bölmə panelləri (section panels)
 * olmayan səhifələrdə işə düşmür. profile_embed_base.html bu faylı ui.js-dən
 * SONRA, profile.entry.js-dən ƏVVƏL yükləyir: yalnız sidebar davranışını
 * tamamlayır (akkordeon qruplar + mobil Escape-lə bağlama). SPA səhifəsində
 * özünü söndürür — orada init.js məsuliyyət daşıyır.
 */
(function (ns) {
    "use strict";

    ns.register(function installProfileEmbed(ctx) {
        if (!ctx.profilePage || ctx.sectionPanels.length) {
            return; // SPA: init.js işləyəcək
        }

        ctx.initSidebarAccordionMenu();

        document.addEventListener("keydown", function (event) {
            if (
                event.key === "Escape" &&
                ctx.isMobileViewport() &&
                ctx.sidebar &&
                !ctx.sidebar.classList.contains("collapsed")
            ) {
                ctx.setSidebarCollapsed(true);
            }
        });
    });
})(window.EMSProfile = window.EMSProfile || {});
