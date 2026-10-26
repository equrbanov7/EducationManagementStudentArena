/* Jurnal: KİLİDLİ xana dialoqu (sahib 2026-10-25).

   «Müəllim kiməsə q/b və ya bal yazıbsa, yazdığından 15 dəqiqə sonra onu geri dəyişə bilməsin, olduğu kimi
   qalsın. Bunun üçün RİM-ə müraciət edib təqdimat yazmaq lazım olduğunu qeyd etsin.»

   Kilidli xana (`[data-jd-lock="time|legacy|entry"]`, _jd_grid.html; 2026-10-26-dan balsız i/e yalnız
   yazma müddəti bitəndə — «entry») yalnız-oxu render olunur — kilidi SERVER
   məcburi edir (gradebook_marks.save_marks + DB trigger; avtomatik yadda saxlama 409 qaytarır). Bu fayl
   yalnız izah edir: klikdə EMSConfirm dialoqu açılır — mətn formanın
   `data-jd-lock-msg-<səbəb>` atributundan (xanaya mətn yazılmır: 555 × 20 xanada HTML böyüməsin), təsdiq
   düyməsi «RİM-ə müraciət yaz» → `data-jd-lock-url` (Müraciətlər, növ öncədən seçilmiş).

   CSP/AJAX-safe: inline yoxdur; mətn yalnız `textContent` ilə (EMSConfirm); hadisə `EMSDelegate.on` ilə
   sənəd səviyyəsində BİR dəfə qoşulur — cədvəl yerində yenilənsə də işləyir. */
(function () {
    "use strict";

    var CELL = "[data-jd-lock]";

    function explain(cell) {
        var form = cell.closest("form[data-jd-lock-url]");
        if (!form) return;
        var reason = cell.getAttribute("data-jd-lock") || "time";
        var body = form.getAttribute("data-jd-lock-msg-" + reason) || form.getAttribute("data-jd-lock-msg-time") || "";
        var url = form.getAttribute("data-jd-lock-url") || "";
        if (!window.EMSConfirm || typeof window.EMSConfirm.open !== "function") {
            if (window.EMSToast && typeof window.EMSToast.show === "function") window.EMSToast.show(body, "warning", 8000);
            return;
        }
        window.EMSConfirm.open({
            title: form.getAttribute("data-jd-lock-title") || "",
            body: body,
            confirmLabel: form.getAttribute("data-jd-lock-confirm") || "",
            cancelLabel: form.getAttribute("data-jd-lock-cancel") || "",
        }).then(function (ok) {
            if (ok && url) api.go(url);
        });
    }

    function wire() {
        window.EMSDelegate.on("click", CELL, function (event, cell) {
            event.preventDefault();
            explain(cell);
        });
    }

    var api = {
        explain: explain,
        go: function (url) {
            window.location.assign(url);
        },
    };
    window.EMSJournalMarkLock = api;
    if (window.EMSReady && window.EMSDelegate) {
        window.EMSReady(function () {
            if (window.EMSReady.once) window.EMSReady.once("journal-mark-lock", wire);
            else wire();
        });
    }
})();
