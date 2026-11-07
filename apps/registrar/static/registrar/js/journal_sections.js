/* Jurnal bölmələri — «Mühazirə · 234 K», «234 K1 · Seminar», «234 K1 · Lab-1» (sahib 2026-11-07).

   Düymə yalnız GÖRÜNÜŞÜ dəyişir: seçilmiş bölmənin dərs sütunları (`th/td[data-jd-col]`, növ + alt qrup / lab qrupu)
   və tələbə sətirləri (`tr[data-jd-row-sem|lab]`) göstərilir, qalanı gizlənir. Yazı qaydaları serverdədir
   (lab_groups.applies). «Hamısı» hər şeyi qaytarır. AJAX-safe: yalnız EMSDelegate. */
(function () {
    "use strict";

    var HIDDEN = "jd2-sec-hidden";

    function columnGroup(th, kind) {
        return th.getAttribute(kind === "seminar" ? "data-jd-col-sem" : "data-jd-col-lab") || "";
    }

    function apply(grid, kind, group) {
        if (!grid) return;
        grid.querySelectorAll("th[data-jd-col]").forEach(function (th) {
            var own = columnGroup(th, kind);
            var show = !kind || (th.getAttribute("data-jd-col-kind") === kind && (!group || !own || own === group));
            var id = th.getAttribute("data-jd-col");
            th.classList.toggle(HIDDEN, !show);
            grid.querySelectorAll("td[data-jd-col='" + id + "']").forEach(function (td) {
                td.classList.toggle(HIDDEN, !show);
            });
        });
        grid.querySelectorAll("tr[data-jd-enrollment]").forEach(function (tr) {
            var own = tr.getAttribute(kind === "seminar" ? "data-jd-row-sem" : "data-jd-row-lab") || "";
            var show = !group || kind === "lecture" || own === group;
            tr.classList.toggle(HIDDEN, !show);
        });
    }

    window.EMSDelegate.on("click", "[data-jd-section]", function (event, button) {
        var bar = button.closest(".jd2-sections");
        if (bar) {
            bar.querySelectorAll("[data-jd-section]").forEach(function (other) {
                var active = other === button;
                other.classList.toggle("is-active", active);
                other.setAttribute("aria-pressed", active ? "true" : "false");
            });
        }
        apply(document.querySelector("[data-journal-grid]"), button.getAttribute("data-kind") || "",
            button.getAttribute("data-group") || "");
    });
})();
