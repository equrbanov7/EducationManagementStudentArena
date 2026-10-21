(function (ns, window, document) {
    "use strict";

    function start() {
        if (window._EMS_TAKE_EXAM_INIT) {
            return;
        }
        window._EMS_TAKE_EXAM_INIT = true;

        var ctx = ns.config.createContext();
        if (!ctx) {
            return;
        }

        ns.writer.init(ctx);
        ns.progress.init(ctx);
        ns.timers.initTimeWarning(ctx);
        ns.files.init(ctx);
        ns.draft.init(ctx);
        ns.syncStatus.init(ctx);
        ns.resync.init(ctx);
        ns.timers.initExamTimer(ctx);
        ns.timers.initVisibilityRefresh(ctx);
        // Zal imtahanında ikinci tab yoxlaması (writer.js) bitənə qədər naviqasiya (ilk sual taymeri) gözləyir.
        ns.writer.settled(ctx).then(function () {
            ns.navigation.init(ctx);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})(window.EMSTakeExam = window.EMSTakeExam || {}, window, document);
