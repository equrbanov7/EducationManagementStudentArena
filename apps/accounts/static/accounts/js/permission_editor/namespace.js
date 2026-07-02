/* Permission editor namespace shared by ordered classic scripts. */
(function (window) {
    "use strict";

    var ns = window.EMSPermissionEditor = window.EMSPermissionEditor || {};
    ns._initializedRoots = ns._initializedRoots || [];

    ns.markInitialized = function markInitialized(root) {
        if (!root || ns._initializedRoots.indexOf(root) !== -1) {
            return false;
        }
        ns._initializedRoots.push(root);
        return true;
    };
})(window);
