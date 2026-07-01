/* Profile page entry point. Keep this script last in the ordered profile bundle. */
(function (ns) {
    "use strict";

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", ns.start);
    } else {
        ns.start();
    }
})(window.EMSProfile = window.EMSProfile || {});
