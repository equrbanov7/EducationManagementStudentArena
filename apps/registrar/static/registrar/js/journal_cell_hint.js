/* Jurnal cədvəli: xananın üstünə gələndə (və ya klaviatura ilə fokuslananda) SƏTİR və SÜTUN başlığı
   yüngül fon rəngi ilə işıqlanır — müəllim kimin üzərində olduğunu sətrin rəngindən görür.

   Sahib 2026-10-10: «q/b, i/e nə yazırsansa, kimin üzərində olduğun bilinsin» — əvvəl xananın üstündə
   ad + tarix + dərs tipi olan TOOLTIP çıxırdı, xananın özü isə qalın göy çərçivə alırdı.
   Sahib 2026-10-14: «ehtiyac yoxdu border və üstə çıxan ad olmasın, hover-dəki background rəng olsa
   bəs edir» — tooltip VİZUAL olaraq yoxdur, çərçivə yoxdur (journal_cell_hint.css). Ekran oxuyucusu
   üçün eyni mətn («Soyad Ad Ata adı · 09.10.2026 · Seminar») GÖRÜNMƏZ təsvir kimi qalır
   (`aria-describedby`) — klaviatura/ekran oxuyucusu istifadəçisi kontekstini itirmir.

   Ad sətirdə BİR dəfə saxlanılır (`[data-jd-hint-name]`), sütun etiketi başlıqdadır
   (`th[data-jd-hint-col]`) — xanaya atribut yazılmır: 555 × 20 xanalı jurnalda hər xanaya
   mətn əlavə etmək HTML-i yüzlərlə KB böyüdərdi (bax `_jd_grid.html`-dəki `spaceless` qeydi).
   Mətn yalnız `textContent` ilə yazılır. AJAX-safe: sənəd səviyyəli dinləyicilər bir dəfə
   (`EMSReady.once`); cədvəl yerində yenilənəndə (journal_guest.js) köhnə xana atılır. */
(function () {
    "use strict";

    var CELL = "table[data-jd-hint] > tbody > tr > td";

    var tip = null;
    var current = null;

    function ensureTip() {
        if (tip && document.body.contains(tip)) return tip;
        tip = document.createElement("div");
        // Görünməz (yalnız ekran oxuyucusu üçün) təsvir — üzən tooltip YOX (sahib 2026-10-14).
        tip.className = "jd-hint";
        tip.id = "jd-cell-hint";
        tip.hidden = true;
        var name = document.createElement("span");
        name.className = "jd-hint__name";
        var meta = document.createElement("span");
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
        // Ad xanasının özündə təsvir lazım deyil — ad onsuz da oradadır.
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

    function show(td, focused) {
        if (td === current) {
            if (focused) focused.setAttribute("aria-describedby", "jd-cell-hint");
            return;
        }
        var name = nameFor(td);
        hide();
        if (!name) return;
        var box = ensureTip();
        var th = headerFor(td);
        var label = th ? (th.getAttribute("data-jd-hint-col") || "").trim() : "";
        box.firstChild.textContent = name;
        box.lastChild.textContent = label ? " · " + label : "";
        box.lastChild.hidden = !label;
        current = td;
        td.classList.add("is-hint-cell");
        td.parentElement.classList.add("is-hint-row");
        if (th) th.classList.add("is-hint-col");
        if (focused) focused.setAttribute("aria-describedby", "jd-cell-hint");
        box.hidden = false;
    }

    function onPointer(event) {
        var target = event.target;
        if (!target || typeof target.closest !== "function") return;
        var td = target.closest(CELL);
        if (td) {
            show(td, null);
            return;
        }
        // Fokus hələ xanadadırsa (klaviatura ilə seçim) siçan çıxanda işığı söndürmə.
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
