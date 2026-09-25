/**
 * Oturum tarixçəsi — tələbə adı üzrə sadə süzgəc (client-side).
 */
(function () {
    "use strict";

    // Tolerant axtarış (EMSSearch: az↔en hərfləri, «234king» → «234 K ing»).
    // «İ».toLowerCase() = «i» + U+0307 (birləşən nöqtə) — mətndən atılır.
    function searchMatcher(query) {
        var q = String(query || "").trim();
        var m = window.EMSSearch ? window.EMSSearch.matcher(q) : null;
        var low = q.toLowerCase();
        return function (text) {
            var t = String(text || "").replace(/\u0307/g, "");
            return m ? m(t) : !low || t.toLowerCase().indexOf(low) !== -1;
        };
    }

    var input = document.getElementById("fxc-hist-filter");
    var list = document.getElementById("fxc-timeline");
    var noResult = document.getElementById("fxc-hist-noresult");
    if (!input || !list) return;

    var items = Array.prototype.slice.call(list.querySelectorAll(".fxc-tl-item"));

    input.addEventListener("input", function () {
        var q = input.value.trim();
        var matcher = searchMatcher(q);
        var shown = 0;
        items.forEach(function (item) {
            var student = item.getAttribute("data-student") || "";
            var match = !q || matcher(student);
            item.hidden = !match;
            if (match) shown += 1;
        });
        if (noResult) noResult.hidden = shown !== 0;
    });
})();
