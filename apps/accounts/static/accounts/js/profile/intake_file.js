/* Toplu əlavə axınlarının FAYL SEÇİMİ səthi (tələbə · müəllim · ekran 08).
 *
 * Niyə ayrı fayl? `student_intake.js` axının məntiqidir (quru icra → nəticə →
 * parol CSV-si) və modul ölçüsü büdcəsinə (SOFT_CAP=600) dayanmışdı. Sürüşdürüb
 * atma səthi ondan MÜSTƏQİLDİR: heç bir sorğu göndərmir, yalnız `<input type=
 * file>`-ın vəziyyətini görünən hala çevirir. Ona görə burada saxlanılır.
 *
 * Qaydalar (CLAUDE.md + docs/frontend/AJAX_SAFE_JS_PATTERN.md):
 *   · inline JS yoxdur — mətnlər `data-six-empty` atributundadır;
 *   · `EMSDelegate.on` ilə document səviyyəsində delegasiya (swap-safe);
 *   · çəngəl (`[data-six-file]`) yoxdursa heç nə etmir (null-safe).
 *
 * ⚠️ DELEQAT AÇARLARI: `change|[data-six-file]` və `drag*|[data-six-drop]`
 * YALNIZ bu faylda qeyd olunur (bax `test_static_js_delegate_keys.py`) —
 * eyni açar ikinci faylda yazılsa əvvəlki dinləyici SİLİNİR.
 */
(function (window, document) {
    "use strict";

    var DELEGATE = window.EMSDelegate;
    if (!DELEGATE) {
        return;
    }

    function host() {
        return document.querySelector("[data-six-root]");
    }

    /* Seçilmiş faylı görünən hala gətirir: ad, «doldu» tonu, xəta qutusunun
     * təmizlənməsi. Fayl silinəndə boş mətn `data-six-empty`-dən qayıdır. */
    function sync(scope) {
        var input = scope.querySelector("[data-six-file]");
        var label = scope.querySelector("[data-six-file-label]");
        var drop = scope.querySelector("[data-six-drop]");
        var error = scope.querySelector("[data-six-error]");
        var file = input && input.files && input.files.length ? input.files[0] : null;
        if (label) {
            label.dataset.sixEmpty = label.dataset.sixEmpty || label.textContent;
            label.textContent = file ? file.name : label.dataset.sixEmpty;
        }
        if (drop) {
            drop.classList.toggle("is-filled", !!file);
            drop.classList.remove("is-over");
        }
        if (error) {
            error.textContent = "";
            error.hidden = true;
        }
    }

    //: `student_intake.js` tətbiqdən sonra sahəni sıfırlayanda çağırır.
    window.EMSIntakeFile = { sync: sync };

    DELEGATE.on("change", "[data-six-file]", function () {
        var scope = host();
        if (scope) {
            sync(scope);
        }
    });

    DELEGATE.on("dragover", "[data-six-drop]", function (event, drop) {
        event.preventDefault();
        drop.classList.add("is-over");
    });

    DELEGATE.on("dragleave", "[data-six-drop]", function (event, drop) {
        drop.classList.remove("is-over");
    });

    DELEGATE.on("drop", "[data-six-drop]", function (event, drop) {
        event.preventDefault();
        var input = drop.querySelector("[data-six-file]");
        var transfer = event.dataTransfer;
        if (input && transfer && transfer.files && transfer.files.length) {
            input.files = transfer.files;
        }
        var scope = host();
        if (scope) {
            sync(scope);
        }
    });
})(window, document);
