/* =========================================================================
   ems_ui/nav.js — Tab · ağac · addım naviqasiyası · KPI filtr açarı · görünüş açarı
   (handoff §4 komponentləri 1, 6, 11 · §7 «klaviatura ilə tam keçid»)

   Hamısı panel-daxili, YALNIZ KLİYENT vəziyyəti. Sol sidebar-a TOXUNMUR —
   kabinet qabığı və sidebar həmişə yerində qalır.

   MARKUP MÜQAVİLƏLƏRİ
   -------------------
   Tab:      <div data-ems-tabs>
               <button class="ems-tabs__btn" data-ems-tab="queue" aria-current="page">
               …
             <div data-ems-tabpanel="queue">
   Ağac:     <ul class="ems-tree" role="tree">
               <li role="none">
                 <button class="ems-tree__row" role="treeitem"
                         aria-expanded="false" aria-selected="false"
                         data-ems-tree-node="42">
   Addım nav:<button class="ems-stepnav__btn" data-ems-step="week">
   KPI filtr:<button class="ems-kpi" data-ems-kpi-filter="revision" aria-pressed="false">
   Görünüş:  <div class="ems-viewtoggle"><button data-ems-view="table" aria-pressed="true">

   KPI və görünüş açarları `ems:kpi-filter` / `ems:view` CustomEvent-i atır —
   ekran onları dinləyib öz sorğusunu qurur (bu fayl data bilmir).
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSNav) {
        return;
    }

    function emit(el, name, detail) {
        el.dispatchEvent(new CustomEvent(name, { bubbles: true, detail: detail }));
    }

    /* ---- Tab-lar --------------------------------------------------------- */

    function activateTab(btn) {
        var root = btn.closest("[data-ems-tabs]");
        if (!root) {
            return;
        }
        var key = btn.getAttribute("data-ems-tab");
        var buttons = root.querySelectorAll("[data-ems-tab]");
        for (var i = 0; i < buttons.length; i += 1) {
            var on = buttons[i] === btn;
            if (on) {
                buttons[i].setAttribute("aria-current", "page");
            } else {
                buttons[i].removeAttribute("aria-current");
            }
            buttons[i].tabIndex = on ? 0 : -1;
        }
        // Panellər eyni kökdə OLMAYA bilər — sənəd üzrə axtarırıq.
        var scope = root.closest("[data-profile-section-panel]") || document;
        var panels = scope.querySelectorAll("[data-ems-tabpanel]");
        for (var j = 0; j < panels.length; j += 1) {
            panels[j].hidden = panels[j].getAttribute("data-ems-tabpanel") !== key;
        }
        emit(btn, "ems:tab", { tab: key });
    }

    window.EMSDelegate.on("click", "[data-ems-tabs] [data-ems-tab]", function (event, btn) {
        event.preventDefault();
        activateTab(btn);
    });

    window.EMSDelegate.on("keydown", "[data-ems-tabs] [data-ems-tab]", function (event, btn) {
        var next = null;
        if (event.key === "ArrowRight") {
            next = btn.nextElementSibling;
        } else if (event.key === "ArrowLeft") {
            next = btn.previousElementSibling;
        } else {
            return;
        }
        while (next && !next.hasAttribute("data-ems-tab")) {
            next = event.key === "ArrowRight" ? next.nextElementSibling : next.previousElementSibling;
        }
        if (next) {
            event.preventDefault();
            next.focus();
            activateTab(next);
        }
    });

    /* ---- Ağac naviqasiyası ----------------------------------------------- */

    function treeRows(tree) {
        // Yalnız GÖRÜNƏN sətirlər (bağlı qovşağın uşaqları keçilmir).
        var all = tree.querySelectorAll(".ems-tree__row");
        var out = [];
        for (var i = 0; i < all.length; i += 1) {
            var group = all[i].closest(".ems-tree__group");
            var hidden = false;
            while (group) {
                if (group.hidden) {
                    hidden = true;
                    break;
                }
                group = group.parentElement ? group.parentElement.closest(".ems-tree__group") : null;
            }
            if (!hidden) {
                out.push(all[i]);
            }
        }
        return out;
    }

    function setExpanded(row, expanded) {
        if (row.getAttribute("aria-expanded") === null) {
            return;
        }
        row.setAttribute("aria-expanded", expanded ? "true" : "false");
        var group = row.parentElement ? row.parentElement.querySelector(".ems-tree__group") : null;
        if (group) {
            group.hidden = !expanded;
        }
        emit(row, "ems:tree-toggle", { node: row.getAttribute("data-ems-tree-node"), expanded: expanded });
    }

    function selectRow(row) {
        var tree = row.closest(".ems-tree");
        if (!tree) {
            return;
        }
        var rows = tree.querySelectorAll(".ems-tree__row");
        for (var i = 0; i < rows.length; i += 1) {
            rows[i].setAttribute("aria-selected", rows[i] === row ? "true" : "false");
            rows[i].tabIndex = rows[i] === row ? 0 : -1;
        }
        emit(row, "ems:tree-select", { node: row.getAttribute("data-ems-tree-node") });
    }

    window.EMSDelegate.on("click", ".ems-tree__row", function (event, row) {
        event.preventDefault();
        selectRow(row);
        if (event.target.closest(".ems-tree__twisty")) {
            setExpanded(row, row.getAttribute("aria-expanded") !== "true");
        }
    });

    window.EMSDelegate.on("keydown", ".ems-tree__row", function (event, row) {
        var tree = row.closest(".ems-tree");
        if (!tree) {
            return;
        }
        var rows = treeRows(tree);
        var index = rows.indexOf(row);
        var key = event.key;

        if (key === "ArrowDown" && index < rows.length - 1) {
            event.preventDefault();
            rows[index + 1].focus();
            selectRow(rows[index + 1]);
        } else if (key === "ArrowUp" && index > 0) {
            event.preventDefault();
            rows[index - 1].focus();
            selectRow(rows[index - 1]);
        } else if (key === "ArrowRight") {
            event.preventDefault();
            if (row.getAttribute("aria-expanded") === "false") {
                setExpanded(row, true);
            } else if (index < rows.length - 1) {
                rows[index + 1].focus();
                selectRow(rows[index + 1]);
            }
        } else if (key === "ArrowLeft") {
            event.preventDefault();
            if (row.getAttribute("aria-expanded") === "true") {
                setExpanded(row, false);
            } else {
                var parentGroup = row.closest(".ems-tree__group");
                var parentRow = parentGroup && parentGroup.parentElement
                    ? parentGroup.parentElement.querySelector(".ems-tree__row")
                    : null;
                if (parentRow) {
                    parentRow.focus();
                    selectRow(parentRow);
                }
            }
        } else if (key === "Home" && rows.length) {
            event.preventDefault();
            rows[0].focus();
            selectRow(rows[0]);
        } else if (key === "End" && rows.length) {
            event.preventDefault();
            rows[rows.length - 1].focus();
            selectRow(rows[rows.length - 1]);
        }
    });

    /* ---- Addım naviqasiyası ---------------------------------------------- */

    window.EMSDelegate.on("click", "[data-ems-step]", function (event, btn) {
        event.preventDefault();
        var nav = btn.closest(".ems-stepnav");
        if (!nav) {
            return;
        }
        var key = btn.getAttribute("data-ems-step");
        var buttons = nav.querySelectorAll("[data-ems-step]");
        for (var i = 0; i < buttons.length; i += 1) {
            if (buttons[i] === btn) {
                buttons[i].setAttribute("aria-current", "step");
            } else {
                buttons[i].removeAttribute("aria-current");
            }
        }
        var scope = nav.closest("[data-profile-section-panel]") || document;
        var panels = scope.querySelectorAll("[data-ems-steppanel]");
        for (var j = 0; j < panels.length; j += 1) {
            panels[j].hidden = panels[j].getAttribute("data-ems-steppanel") !== key;
        }
        emit(btn, "ems:step", { step: key });
    });

    /* ---- KPI filtr açarı (aria-pressed, tək seçim) ------------------------ */

    window.EMSDelegate.on("click", "[data-ems-kpi-filter]", function (event, btn) {
        event.preventDefault();
        var row = btn.closest(".ems-kpis") || document;
        var was = btn.getAttribute("aria-pressed") === "true";
        var tiles = row.querySelectorAll("[data-ems-kpi-filter]");
        for (var i = 0; i < tiles.length; i += 1) {
            tiles[i].setAttribute("aria-pressed", "false");
        }
        if (!was) {
            btn.setAttribute("aria-pressed", "true");
        }
        emit(btn, "ems:kpi-filter", { filter: was ? null : btn.getAttribute("data-ems-kpi-filter") });
    });

    /* ---- Cədvəl ⇄ Kart açarı --------------------------------------------- */

    window.EMSDelegate.on("click", "[data-ems-view]", function (event, btn) {
        event.preventDefault();
        var group = btn.closest(".ems-viewtoggle");
        if (!group) {
            return;
        }
        var key = btn.getAttribute("data-ems-view");
        var buttons = group.querySelectorAll("[data-ems-view]");
        for (var i = 0; i < buttons.length; i += 1) {
            buttons[i].setAttribute("aria-pressed", buttons[i] === btn ? "true" : "false");
        }
        var scope = group.closest("[data-profile-section-panel]") || document;
        var views = scope.querySelectorAll("[data-ems-viewpanel]");
        for (var j = 0; j < views.length; j += 1) {
            views[j].hidden = views[j].getAttribute("data-ems-viewpanel") !== key;
        }
        emit(btn, "ems:view", { view: key });
    });

    /* İlk render + AJAX swap: roving tabindex baseline-ı qur. */
    window.EMSReady(function () {
        var trees = document.querySelectorAll(".ems-tree");
        for (var i = 0; i < trees.length; i += 1) {
            var rows = trees[i].querySelectorAll(".ems-tree__row");
            var hasSelected = trees[i].querySelector('.ems-tree__row[aria-selected="true"]');
            for (var j = 0; j < rows.length; j += 1) {
                rows[j].tabIndex = hasSelected ? (rows[j] === hasSelected ? 0 : -1) : j === 0 ? 0 : -1;
            }
        }
        var tabGroups = document.querySelectorAll("[data-ems-tabs]");
        for (var k = 0; k < tabGroups.length; k += 1) {
            var btns = tabGroups[k].querySelectorAll("[data-ems-tab]");
            for (var m = 0; m < btns.length; m += 1) {
                btns[m].tabIndex = btns[m].hasAttribute("aria-current") ? 0 : -1;
            }
        }
    });

    window.EMSNav = {
        activateTab: activateTab,
        selectTreeRow: selectRow,
        setTreeExpanded: setExpanded,
    };
})(window, document);
