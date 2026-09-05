/* Jurnal bal formalarında İKİQAT GÖNDƏRİŞ qapısı (QA 2026-09-05 P3-11).

   Ayrı fayldır: `journal_grid.js` modul ölçü büdcəsinin (672 sətir) tam
   həddindədir və bu qapı ondan müstəqildir. */
(function () {
    "use strict";

    // QA 2026-09-05 (P3-11): «Yadda saxla» düyməsi göndərişdən sonra aktiv
    // qalırdı — ikiqat klik iki POST göndərirdi. Qapı YALNIZ bal formasına
    // (`form[data-jd-draft]`) aiddir və BUBBLE fazasındadır: bu faylda başqa
    // handler-lər (silmə/təsdiq modalları) capture-da `preventDefault()` edir,
    // ona görə `defaultPrevented` yoxlanılır — əks halda modal açılan formanın
    // düymələri həmişəlik bloklanardı.
    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form || !form.matches || !form.matches("form[data-jd-draft]")) {
            return;
        }
        if (event.defaultPrevented) {
            return;
        }
        if (form.dataset.jdSubmitting === "1") {
            event.preventDefault();
            return;
        }
        form.dataset.jdSubmitting = "1";
        var buttons = form.querySelectorAll('button[type="submit"], input[type="submit"]');
        window.setTimeout(function () {
            for (var i = 0; i < buttons.length; i += 1) {
                buttons[i].disabled = true;
                buttons[i].setAttribute("aria-busy", "true");
            }
        }, 0);
    });
})();
