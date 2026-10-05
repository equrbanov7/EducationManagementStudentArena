/* Jurnal grid: sağdakı «N q/b» sayğacı davamiyyət dəyişəndə CANLI yenilənir (UX2 2026-10-05).

   Əvvəl sayğac yalnız «Yadda saxla»-dan sonra (server render) dəyişirdi: müəllim q/b seçir,
   sağdakı rəqəm yerində qalırdı. Server sayı (`row.absence_count`) görünən pəncərədən kənar
   dərsləri və birləşmədən gələn əvvəlki jurnalı da daxil edir — ona görə rəqəm sıfırdan
   yenidən sayılmır: «server sayı + (indi q/b olan xanalar − render olunanda q/b olan xanalar)».
   Render vəziyyəti `option.defaultSelected`-dir (server `selected` atributu; `.value` təyini onu
   dəyişmir — gizli input üçün isə `.value` atributun özünü dəyişir, ona görə select-ə baxılır), yəni
   qaralama bərpası və ya toplu düymə də düzgün hesablanır. Limit/xəbərdarlıq rəngi (is-warning /
   is-barred) saat və fərdi hədd üzrədir — onu yalnız server hesablayır, saxlayandan sonra yenilənir.

   Yalnız UX-dir; server qaydaları dəyişmir. AJAX-safe: sənəd səviyyəli delegasiya + EMSReady. */
(function () {
    "use strict";

    // q/b olan xana: select hazırda «qb»-dir (toplu düymə də select-ə dəyər verir).
    function renderedAbsent(select) {
        var opt = select.querySelector('option[value="qb"]');
        return !!(opt && opt.defaultSelected);
    }

    function rowDelta(row) {
        var delta = 0;
        row.querySelectorAll("select[data-jd-semselect]").forEach(function (select) {
            if (select.value === "qb") delta += 1;
            if (renderedAbsent(select)) delta -= 1;
        });
        return delta;
    }

    function recount(root) {
        (root || document).querySelectorAll("tr.jd2-row").forEach(function (row) {
            var chip = row.querySelector(".jd2-qchip");
            if (!chip) return;
            if (chip.dataset.qbBase === undefined) {
                var base = parseInt(chip.textContent, 10);
                if (isNaN(base)) return;
                chip.dataset.qbBase = String(base);
            }
            var total = Math.max(0, parseInt(chip.dataset.qbBase, 10) + rowDelta(row));
            var text = total + " q/b";
            if (chip.textContent !== text) chip.textContent = text;
            chip.classList.toggle("is-live", total !== parseInt(chip.dataset.qbBase, 10));
        });
    }

    // Başqa dinləyicilər (journal_grid.js) gizli att sahəsini həmin hadisədə yazır —
    // sayğac onlardan SONRA oxusun deyə növbəti tikdə yenilənir.
    var pending = null;
    function schedule() {
        if (pending) return;
        pending = setTimeout(function () {
            pending = null;
            recount();
        }, 0);
    }

    function wire() {
        // Seçim, toplu düymə (setSelectValue) və qaralama bərpası hamısı select-də «change» yaradır.
        window.EMSDelegate.on("change", "[data-jd-semselect]", schedule);
    }

    window.EMSJournalAbsence = { recount: recount };
    if (window.EMSReady) {
        window.EMSReady(function () {
            if (window.EMSReady.once) window.EMSReady.once("journal-absence-wire", wire);
            else wire();
            schedule(); // qaralama bərpasından sonrakı ilkin vəziyyət
        });
    }
})();
