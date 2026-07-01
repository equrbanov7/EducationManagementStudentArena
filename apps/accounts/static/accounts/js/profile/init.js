/* Initial profile-page activation. */
(function (ns) {
    "use strict";

    ns.register(function installProfileInit(ctx) {
        if (!ctx.profilePage || !ctx.sectionLinks.length || !ctx.sectionPanels.length) {
            return;
        }

        ctx.initSidebarAccordionMenu();
        ctx.initDebouncedSearchForms();

        var resolvedSection = ctx.resolveSectionFromUrl();
        if (!ctx.setActiveSection(resolvedSection, false)) {
            ctx.setActiveSection(ctx.defaultSection, false);
        }

        window.addEventListener("popstate", function () {
            var section = ctx.resolveSectionFromUrl();
            if (ctx.isAjaxSafeSection(section)) {
                return;
            }
            if (!ctx.setActiveSection(section, false)) {
                window.location.reload();
            }
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && ctx.createExamModal && ctx.createExamModal.classList.contains("active")) {
                ctx.closeCreateExamModal(true);
                return;
            }

            if (event.key === "Escape" && ctx.isAssignedExamInfoOpen && ctx.isAssignedExamInfoOpen()) {
                ctx.closeAssignedExamInfoModal();
                return;
            }

            if (event.key === "Escape" && ctx.isMobileViewport() && ctx.sidebar && !ctx.sidebar.classList.contains("collapsed")) {
                ctx.setSidebarCollapsed(true);
            }
        });
    });
})(window.EMSProfile = window.EMSProfile || {});
