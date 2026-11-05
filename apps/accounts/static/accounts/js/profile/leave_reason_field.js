/* «Dondur» (akademik məzuniyyət) — səbəb kateqoriyası seçicisi (sahib 2026-11-04).
 *
 * Şablon: `student_services/_leave_reason_field.html` (qrup çekmecəsinin «Dondur» dialoqu və
 * «Tələbə reyestri»nin hərəkət dialoqu). Bu modul YALNIZ bir qaydanı UI-da göstərir:
 * «Digər» seçiləndə dialoqun səbəb mətni (`[data-ems-reason-field]`) məcburi olur — textarea-ya
 * `data-ems-required` qoyulur və `overlay.js`-in təsdiq qapısı onu yoxlayır. Faktiki qayda
 * serverdədir (`registrar.movements.normalize_leave_reason`).
 *
 * AJAX-safe: hadisələr sənəd səviyyəsində delegasiya olunur (`EMSDelegate`), bağlama idempotentdir.
 */
(function (window, document) {
    "use strict";

    var OTHER = "other";

    function sync(select) {
        if (!select || !select.closest) {
            return;
        }
        var form = select.closest("form");
        if (!form) {
            return;
        }
        var box = select.closest(".ems-field");
        // Gizli blok (reyestr dialoqunda başqa növ seçilib) heç nəyi məcburi etmir.
        var needNote = !(box && box.hidden) && select.value === OTHER;
        var reason = form.querySelector("[data-ems-reason-field]");
        if (reason) {
            if (needNote) {
                reason.setAttribute("data-ems-required", "");
            } else {
                reason.removeAttribute("data-ems-required");
            }
            // `overlay.js` təsdiq düyməsini `input` hadisəsində yenidən hesablayır.
            reason.dispatchEvent(new Event("input", { bubbles: true }));
        }
        var hint = box ? box.querySelector("[data-leave-reason-hint]") : null;
        if (hint) {
            hint.textContent = (needNote ? hint.getAttribute("data-hint-other") : hint.getAttribute("data-hint")) || "";
        }
    }

    function syncWithin(scope) {
        var selects = scope && scope.querySelectorAll ? scope.querySelectorAll("[data-leave-reason-select]") : [];
        Array.prototype.forEach.call(selects, function (select) {
            // `form.reset()` / prefill native dəyəri dəyişir — görünən menyu da uyğunlaşsın.
            if (window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(select);
            }
            sync(select);
        });
    }

    window.EMSLeaveReason = { sync: sync, syncWithin: syncWithin };

    window.EMSReady(function () {
        if (window.__emsLeaveReasonBound) {
            return;
        }
        window.__emsLeaveReasonBound = true;
        window.EMSDelegate.on("change", "[data-leave-reason-select]", function (event, select) {
            sync(select);
        });
        // Dialoq hər açılanda vəziyyət seçicinin CARİ dəyərindən qurulur (əvvəlki «Digər» qalmasın).
        document.addEventListener("ems:overlay:open", function (event) {
            syncWithin(event.target);
        });
    });
})(window, document);
