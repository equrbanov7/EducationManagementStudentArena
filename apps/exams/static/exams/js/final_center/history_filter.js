/**
 * Oturum tarixçəsi — tələbə adı üzrə sadə süzgəc (client-side).
 */
(function () {
    "use strict";
    var input = document.getElementById("fxc-hist-filter");
    var list = document.getElementById("fxc-timeline");
    var noResult = document.getElementById("fxc-hist-noresult");
    if (!input || !list) return;

    var items = Array.prototype.slice.call(list.querySelectorAll(".fxc-tl-item"));

    input.addEventListener("input", function () {
        var q = input.value.trim().toLowerCase();
        var shown = 0;
        items.forEach(function (item) {
            var student = item.getAttribute("data-student") || "";
            var match = !q || student.indexOf(q) !== -1;
            item.hidden = !match;
            if (match) shown += 1;
        });
        if (noResult) noResult.hidden = shown !== 0;
    });
})();
