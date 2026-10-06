/* Elan formu — rahatlıq qatı (bütün yoxlamalar serverdədir):
 *   * auditoriya bölmələrində axtarış (diakritikaya dözümlü) + seçilmiş say;
 *   * «Müraciət et» rejiminə görə sahələrin göstərilməsi;
 *   * başlıq/xülasə simvol sayğacı (`data-annm-count`).
 * AJAX-safe: `EMSDelegate` + `EMSReady` (idempotent; qoruyucu bayraq təkrar qeydiyyatı kəsir).
 */
(function () {
    "use strict";

    if (window.__emsAnnouncementsManage) {
        return;
    }
    window.__emsAnnouncementsManage = true;

    function fold(text) {
        return (text || "")
            .toLowerCase()
            .replace(/ə/g, "e").replace(/ı/g, "i").replace(/ö/g, "o").replace(/ü/g, "u")
            .replace(/ğ/g, "g").replace(/ş/g, "s").replace(/ç/g, "c")
            .normalize("NFD").replace(/[̀-ͯ]/g, "");
    }

    function updateCount(root) {
        var counter = root.querySelector("[data-annm-unit-count]");
        if (!counter) { return; }
        var checked = root.querySelectorAll("input[name='audience_units']:checked").length;
        counter.textContent = checked ? (counter.getAttribute("data-label") || "") + ": " + checked : "";
    }

    function updateApplyPanes(root) {
        var selected = root.querySelector("[data-annm-apply-mode]:checked");
        var mode = selected ? selected.value : "none";
        root.querySelectorAll("[data-annm-apply-pane]").forEach(function (pane) {
            var modes = (pane.getAttribute("data-annm-apply-pane") || "").split(" ");
            pane.hidden = modes.indexOf(mode) === -1;
        });
    }

    function updateCounter(input) {
        var max = parseInt(input.getAttribute("data-annm-count"), 10);
        if (!max) { return; }
        var hint = input.parentNode.querySelector(".annm-counter");
        if (!hint) {
            hint = document.createElement("span");
            hint.className = "annm-counter";
            hint.setAttribute("aria-hidden", "true");
            input.parentNode.appendChild(hint);
        }
        hint.textContent = input.value.length + " / " + max;
    }

    window.EMSDelegate.on("input", "[data-annm-unit-search]", function (event, input) {
        var root = input.closest("[data-annm-audience]");
        if (!root) { return; }
        var needle = fold(input.value.trim());
        root.querySelectorAll("[data-annm-unit]").forEach(function (row) {
            var checked = row.querySelector("input:checked");
            row.hidden = Boolean(needle) && !checked && fold(row.getAttribute("data-label")).indexOf(needle) === -1;
        });
    });

    window.EMSDelegate.on("change", "[data-annm-audience] input[name='audience_units']", function (event, input) {
        var root = input.closest("[data-annm-audience]");
        if (root) { updateCount(root); }
    });

    window.EMSDelegate.on("change", "[data-annm-apply-mode]", function (event, input) {
        var root = input.closest("[data-annm-apply]");
        if (root) { updateApplyPanes(root); }
    });

    window.EMSDelegate.on("input", "[data-annm-count]", function (event, input) {
        updateCounter(input);
    });

    window.EMSReady(function () {
        document.querySelectorAll("[data-annm-audience]").forEach(updateCount);
        document.querySelectorAll("[data-annm-apply]").forEach(updateApplyPanes);
        document.querySelectorAll("[data-annm-count]").forEach(updateCounter);
    });
})();
