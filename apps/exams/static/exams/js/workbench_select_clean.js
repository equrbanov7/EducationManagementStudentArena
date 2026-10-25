/* =========================================================================
   workbench_select_clean.js — toplu sual önizləməsində «Yalnız təmiz sualları
   seç» düyməsi (sahib 2026-10-26).

   Qayda serverdədir (bulk_confidence.refresh_question_meta → meta.is_clean);
   kart onu `data-q-clean="1|0"` kimi daşıyır — JS qaydanı yenidən hesablamır.
   Klik: təmiz kartların checkbox-u işarələnir, qalanlarınınkı götürülür
   (süzgəclə gizlədilmiş kartlar da daxil). Göndəriş mövcud axınla gedir:
   testQuestionBank.js `.qcheck:checked`-i `selected_indices`-ə yazır.

   AJAX-safe: EMSDelegate (document-ə bir dəfə; təkrar yüklənmədə qoruyucu).
   ========================================================================= */
(function () {
    "use strict";

    if (window.__emsWbSelectCleanBound) {
        return;
    }
    window.__emsWbSelectCleanBound = true;

    function selectClean(event, button) {
        event.preventDefault();
        var wrap = button.closest(".bulk-page-wrapper") || document;
        var cards = wrap.querySelectorAll(".q-card[data-q-index]");
        var selectedCount = 0;
        Array.prototype.forEach.call(cards, function (card) {
            var checkbox = card.querySelector(".qcheck");
            if (!checkbox) {
                return;
            }
            var isClean = card.getAttribute("data-q-clean") === "1";
            if (checkbox.checked !== isClean) {
                checkbox.checked = isClean;
                checkbox.dispatchEvent(new Event("change", { bubbles: true }));
            }
            card.classList.toggle("is-selected", isClean);
            if (isClean) {
                selectedCount += 1;
            }
        });

        var status = wrap.querySelector("#wbSelectCleanStatus");
        if (status) {
            var template = status.getAttribute("data-msg-template") || "{count}";
            status.textContent = template.replace("{count}", String(selectedCount));
            status.hidden = false;
        }
    }

    function hideStatus() {
        var status = document.getElementById("wbSelectCleanStatus");
        if (status) {
            status.hidden = true;
        }
    }

    function bind() {
        if (!window.EMSDelegate) {
            return false;
        }
        window.EMSDelegate.on("click", "[data-wb-select-clean]", selectClean);
        // Əl ilə seçim dəyişəndə (və ya «Hamısını seç/götür») köhnə status mesajı gizlənir.
        window.EMSDelegate.on("click", "[data-toggle-all]", hideStatus);
        return true;
    }

    if (!bind()) {
        document.addEventListener("DOMContentLoaded", bind, { once: true });
    }
})();
