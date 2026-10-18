/* «Tələbə reyestri» çekməcəsi — semestr kredit yükü + alt qrup yerləşdirmə izi (sahib 2026-10-18).
 *
 * Əsas çekməcə modulu (student_registry.js) kart datasını `sr:card` hadisəsi ilə yayır; bu modul yalnız
 * `[data-sr-subgroup]` blokunu doldurur (mətnlər `textContent` ilə). AJAX-safe: dinləyici BİR DƏFƏ qoşulur.
 */
(function (window, document) {
    "use strict";

    if (window.EMSRegistrySubgroup) {
        return;
    }
    window.EMSRegistrySubgroup = true;

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text) {
            node.textContent = String(text);
        }
        return node;
    }

    function item(row, block) {
        var li = el("li", "ems-tl__item");
        var gutter = el("div", "ems-tl__gutter");
        gutter.setAttribute("aria-hidden", "true");
        gutter.appendChild(el("span", "ems-tl__dot " + (row.undone ? "ems-tl__dot--muted" : "ems-tl__dot--warning")));
        gutter.appendChild(el("span", "ems-tl__line"));
        var main = el("div", "ems-tl__main");
        var head = el("div", "ems-tl__head");
        head.appendChild(el("span", "ems-tl__who", row.subject_name + (row.undone ? " · " + block.getAttribute("data-label-undone") : "")));
        head.appendChild(el("span", "ems-tl__when", row.created_at + " · " + (row.actor || "—")));
        main.appendChild(head);
        main.appendChild(el("div", "ems-tl__what", row.source_group + " → " + row.target_group + " · " + row.period));
        var order = [row.order_number, row.order_date].filter(Boolean).join(" · ");
        if (order) {
            main.appendChild(el("div", "ems-tl__what", block.getAttribute("data-label-order") + ": " + order));
        }
        main.appendChild(el("div", "ems-tl__reason", row.reason));
        if (row.undo) {
            main.appendChild(el("div", "ems-tl__reason", row.undo.created_at + " · " + row.undo.actor + " · " + row.undo.reason));
        }
        if (row.document_url) {
            var link = el("a", "stsvc__doclink", block.getAttribute("data-label-document"));
            link.href = row.document_url;
            link.target = "_blank";
            link.rel = "noopener";
            main.appendChild(link);
        }
        li.appendChild(gutter);
        li.appendChild(main);
        return li;
    }

    function fill(payload) {
        var block = document.querySelector("[data-sr-subgroup]");
        if (!block || !payload) {
            return;
        }
        var credit = payload.semester_credit;
        var creditNode = block.querySelector("[data-sr-subgroup-credit]");
        if (creditNode) {
            creditNode.textContent = credit
                ? block.getAttribute("data-label-credit") + ": " + credit.total + " / " + credit.limit + " " +
                  block.getAttribute("data-label-credits") +
                  (credit.subgroup ? " (" + block.getAttribute("data-label-subgroup") + ": " + credit.subgroup + ")" : "")
                : "—";
            creditNode.classList.toggle("is-over", !!(credit && credit.over_limit));
        }
        var rows = payload.subgroup_placements || [];
        var list = block.querySelector("[data-sr-subgroup-list]");
        if (list) {
            list.textContent = "";
            rows.forEach(function (row) {
                list.appendChild(item(row, block));
            });
        }
        var empty = block.querySelector("[data-sr-subgroup-empty]");
        if (empty) {
            empty.hidden = rows.length > 0;
        }
        var link = block.querySelector("[data-sr-subgroup-link]");
        if (link) {
            link.hidden = !payload.subgroup_placement_url;
            if (payload.subgroup_placement_url) {
                link.href = payload.subgroup_placement_url;
                link.setAttribute("data-source-url", payload.subgroup_placement_url);
            }
        }
        block.hidden = false;
    }

    window.EMSReady.once("registry-subgroup-card", function () {
        document.addEventListener("sr:card", function (event) {
            fill(event.detail);
        });
    });

    window.EMSRegistrySubgroupFill = fill;
})(window, document);
