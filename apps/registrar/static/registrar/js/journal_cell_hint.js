/* Jurnal cədvəli: xananın üstünə gələndə (və ya klaviatura ilə fokuslananda) onun KİMƏ aid
   olduğu görünür — «Soyad Ad Ata adı» + sütunun qısa etiketi («09.10.2026 · Seminar»).
   Sahib 2026-10-10: «q/b, i/e nə yazırsansa, kimin üzərində olduğun bilinsin».

   Ad sətirdə BİR dəfə saxlanılır (`[data-jd-hint-name]`), sütun etiketi başlıqdadır
   (`th[data-jd-hint-col]`) — xanaya atribut yazılmır: 555 × 20 xanalı jurnalda hər xanaya
   mətn əlavə etmək HTML-i yüzlərlə KB böyüdərdi (bax `_jd_grid.html`-dəki `spaceless` qeydi).

   Tooltip `position: fixed`-dir və `<body>`-yə qoşulur — cədvəlin `overflow:auto` qabı onu
   kəsmir. Xananın seçim menyusu açıqdırsa tooltip menyunun ƏKS tərəfinə keçir.
   Mətn yalnız `textContent` ilə yazılır. AJAX-safe: sənəd səviyyəli dinləyicilər bir dəfə
   (`EMSReady.once`); cədvəl yerində yenilənəndə (journal_guest.js) köhnə xana atılır. */
(function () {
    "use strict";

    var CELL = "table[data-jd-hint] > tbody > tr > td";
    var GAP = 8;

    var tip = null;
    var current = null;

    function ensureTip() {
        if (tip && document.body.contains(tip)) return tip;
        tip = document.createElement("div");
        tip.className = "jd-hint";
        tip.id = "jd-cell-hint";
        tip.setAttribute("role", "tooltip");
        tip.hidden = true;
        var name = document.createElement("div");
        name.className = "jd-hint__name";
        var meta = document.createElement("div");
        meta.className = "jd-hint__meta";
        tip.appendChild(name);
        tip.appendChild(meta);
        document.body.appendChild(tip);
        return tip;
    }

    function headerFor(td) {
        var table = td.closest("table");
        var head = table && table.tHead;
        if (!head || !head.rows.length) return null;
        return head.rows[head.rows.length - 1].cells[td.cellIndex] || null;
    }

    function nameFor(td) {
        var row = td.parentElement;
        var el = row && row.querySelector("[data-jd-hint-name]");
        // Ad xanasının özündə tooltip lazım deyil — ad onsuz da oradadır.
        if (!el || td.contains(el)) return "";
        return (el.textContent || "").replace(/\s+/g, " ").trim();
    }

    function clearMarks() {
        if (!current) return;
        current.classList.remove("is-hint-cell");
        if (current.parentElement) current.parentElement.classList.remove("is-hint-row");
        var th = headerFor(current);
        if (th) th.classList.remove("is-hint-col");
        current.querySelectorAll("[aria-describedby='jd-cell-hint']").forEach(function (el) {
            el.removeAttribute("aria-describedby");
        });
    }

    function hide() {
        clearMarks();
        current = null;
        if (tip) tip.hidden = true;
    }

    function openMenu(td) {
        return td.querySelector(".dropdown-menu.show");
    }

    function place() {
        if (!current || !tip || tip.hidden) return;
        if (!document.contains(current)) {
            hide();
            return;
        }
        var cell = current.getBoundingClientRect();
        var width = tip.offsetWidth;
        var height = tip.offsetHeight;
        var viewportW = document.documentElement.clientWidth || window.innerWidth;
        var viewportH = document.documentElement.clientHeight || window.innerHeight;
        var left = Math.min(Math.max(GAP, cell.left + cell.width / 2 - width / 2), Math.max(GAP, viewportW - width - GAP));
        var above = cell.top - height - GAP;
        var below = cell.bottom + GAP;
        var fitsAbove = above >= GAP;
        var fitsBelow = below + height <= viewportH - GAP;
        // Menyu düyməyə 4 px yapışır, düymə isə xananın içindədir — tərəf xananın ORTASINA görə təyin olunur.
        var menu = openMenu(current);
        var menuRect = menu ? menu.getBoundingClientRect() : null;
        var middle = cell.top + cell.height / 2;
        var top;
        if (menuRect && menuRect.bottom <= middle) top = fitsBelow ? below : null;
        else if (menuRect && menuRect.top >= middle) top = fitsAbove ? above : null;
        else top = fitsAbove ? above : below;
        if (top === null) {
            // Menyunun əks tərəfində yer yoxdur — tooltip menyunun üstünə düşməsin.
            tip.hidden = true;
            return;
        }
        tip.style.left = Math.round(left) + "px";
        tip.style.top = Math.round(top) + "px";
        tip.classList.toggle("is-below", top === below);
    }

    function show(td, focused) {
        if (td === current) {
            if (focused) focused.setAttribute("aria-describedby", "jd-cell-hint");
            place();
            return;
        }
        var name = nameFor(td);
        hide();
        if (!name) return;
        var box = ensureTip();
        var th = headerFor(td);
        var label = th ? (th.getAttribute("data-jd-hint-col") || "").trim() : "";
        box.firstChild.textContent = name;
        box.lastChild.textContent = label;
        box.lastChild.hidden = !label;
        current = td;
        td.classList.add("is-hint-cell");
        td.parentElement.classList.add("is-hint-row");
        if (th) th.classList.add("is-hint-col");
        if (focused) focused.setAttribute("aria-describedby", "jd-cell-hint");
        box.hidden = false;
        place();
    }

    function onPointer(event) {
        var target = event.target;
        if (!target || typeof target.closest !== "function") return;
        var td = target.closest(CELL);
        if (td) {
            show(td, null);
            return;
        }
        // Fokus hələ xanadadırsa (klaviatura ilə seçim) siçan çıxanda gizlətmə.
        if (current && current.contains(document.activeElement)) return;
        hide();
    }

    function onFocusIn(event) {
        var target = event.target;
        if (!target || typeof target.closest !== "function") return;
        var td = target.closest(CELL);
        if (td) show(td, target);
    }

    function onFocusOut(event) {
        if (!current) return;
        var next = event.relatedTarget;
        if (next && current.contains(next)) return;
        if (current.matches(":hover")) return;
        hide();
    }

    function wire() {
        document.addEventListener("mouseover", onPointer);
        document.addEventListener("focusin", onFocusIn);
        document.addEventListener("focusout", onFocusOut);
        // Seçim menyusu açılanda tooltip onun əks tərəfinə keçir (Bootstrap hadisəsi baloncuklanır).
        document.addEventListener("shown.bs.dropdown", place);
        document.addEventListener("hidden.bs.dropdown", function () {
            if (current && tip) {
                tip.hidden = false;
                place();
            }
        });
        window.addEventListener("scroll", hide, true);
        window.addEventListener("resize", hide);
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") hide();
        });
    }

    window.EMSJournalCellHint = { show: show, hide: hide };
    if (window.EMSReady) {
        window.EMSReady(function () {
            if (window.EMSReady.once) window.EMSReady.once("journal-cell-hint", wire);
            else wire();
        });
    }
})();
