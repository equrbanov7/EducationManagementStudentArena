/**
 * Permission editor interactions:
 * - Multi-language user-friendly labels/descriptions (AZ/EN/RU/TR)
 * - Smooth module open/close animation
 * - Module-level select all / deselect all / bulk add / bulk remove
 * - Per-permission toggle with immediate row state update
 */
(function (ns, document, window) {
    "use strict";

    function initRoot(root) {
        if (!root || !ns.markInitialized(root)) {
            return;
        }

        var ctx = ns.labels.createContext();
        var searchInput = root.querySelector("[data-permission-search]");
        var searchSubmitButton = root.querySelector("[data-permission-search-submit]");
        var searchClearButton = root.querySelector("[data-permission-search-clear]");
        var modules = Array.from(root.querySelectorAll("[data-permission-module]"));
        var emptyState = root.querySelector("[data-permission-empty]");

        ns.matrix.localizeGuide(ctx, root);
        ns.matrix.localizeModuleHeaders(ctx, root);
        ns.matrix.localizeTopMeta(ctx, root, searchInput, searchSubmitButton, emptyState);
        ns.matrix.bindPermissionLabels(ctx, root);
        ns.matrix.bindActivePermissionBadges(ctx, root);
        ns.saveState.bindToggleForms(ctx, root);
        ns.interactions.bindModuleAccordionAnimation(modules);

        var moduleApis = modules.map(function (module) {
            return ns.saveState.createModuleApi(module);
        });

        ns.matrix.initializeRows(ctx, root);
        ns.interactions.bindSearch(root, searchInput, searchSubmitButton, searchClearButton, emptyState, moduleApis);
    }

    function initAll(scope) {
        var container = scope || document;
        var editors = container.querySelectorAll("[data-permission-editor]");
        if (!editors.length && container.matches && container.matches("[data-permission-editor]")) {
            editors = [container];
        }
        Array.from(editors).forEach(initRoot);
    }

    ns.init = initRoot;
    ns.initAll = initAll;

    if (window.EMSProfileReinitHooks && typeof window.EMSProfileReinitHooks === "object") {
        window.EMSProfileReinitHooks.permissionEditor = function (panel) {
            initAll(panel || document);
        };
    }

    document.addEventListener("profile:section:loaded", function (event) {
        initAll(event.detail && event.detail.panel ? event.detail.panel : document);
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            initAll(document);
        });
    } else {
        initAll(document);
    }
})(window.EMSPermissionEditor = window.EMSPermissionEditor || {}, document, window);
