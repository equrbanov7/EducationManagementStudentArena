(function (ns, document) {
    "use strict";

    function start() {
        var ctx = ns.config.createContext();
        ns.filters.init(ctx);
        ctx.selection = ns.selection.init(ctx);
        ns.modals.init(ctx);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})(window.EMSStaffManagement = window.EMSStaffManagement || {}, document);
