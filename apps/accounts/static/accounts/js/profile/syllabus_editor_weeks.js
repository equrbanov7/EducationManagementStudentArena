/* Sillabus redaktoru — əlavə olunmuş həftə sətrini SİLMƏK (sahib 2026-10-23).
 *
 * «+ Sətir əlavə et» var idi, əlavə olunmuş sətri silmək olmurdu. Düymə (`data-syl-week-remove`) yalnız planın
 * ÜSTÜNDƏN əlavə olunan sətirdə göstərilir (`_editor_week_row.html`). Silinəndən sonra qalan sətirlər yenidən
 * nömrələnir və avtosaxlama MÖVCUD yolla işə düşür: qalan sətrin mövzu sahəsinə `input` hadisəsi göndərilir —
 * redaktorun öz dinləyicisi (`syllabus_editor.js`) cədvəli toplayıb saxlayır (ayrıca saxlama məntiqi yoxdur).
 * AJAX-safe: yalnız `EMSDelegate` (sənəd səviyyəsində, bir dəfə).
 */
(function (window, document) {
    "use strict";

    if (window.EMSSyllabusWeeks || !window.EMSDelegate) {
        return;
    }

    window.EMSDelegate.on("click", "[data-syl-week-remove]", function (event, button) {
        event.preventDefault();
        var tr = button.disabled ? null : button.closest("[data-syl-week-row]");
        if (!tr) {
            return;
        }
        var body = tr.parentNode;
        body.removeChild(tr);
        var rows = body.querySelectorAll("[data-syl-week-row]");
        Array.prototype.forEach.call(rows, function (row, i) {
            row.setAttribute("data-syl-week-row", String(i + 1));
            var num = row.querySelector("[data-syl-week-num]");
            if (num) {
                num.textContent = String(i + 1);
            }
        });
        var topic = body.querySelector("[data-syl-week-row] [data-week='topic']");
        if (topic) {
            topic.dispatchEvent(new Event("input", { bubbles: true }));
        }
    });

    window.EMSSyllabusWeeks = { version: 1 };
})(window, document);
