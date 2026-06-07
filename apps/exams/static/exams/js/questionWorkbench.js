/*
 * questionWorkbench.js
 * --------------------------------------------------------------------------
 * Ortaq toplu sual workbench-i üçün kiçik UI köməkçiləri:
 *   - Test / Yazılı format pill keçidi (+ hidden q_format sinxronu)
 *   - Formata uyğun placeholder və qayda bələdçisinin dəyişdirilməsi
 *
 * testQuestionBank.js (preview/filter/file UI) ilə yanaşı işləyir, onu əvəz
 * ETMİR. Yalnız format/dil seçicisi olan səhifələrdə yüklənir.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const wrapper = document.querySelector(".bulk-page-wrapper");
    if (!wrapper) return;

    const formatInput = document.getElementById("qFormatInput");
    const editor = document.getElementById("testRawEditor");
    const pills = Array.from(document.querySelectorAll(".wb-format-pill"));
    if (!pills.length || !formatInput) return;

    function applyFormat(format) {
      const value = format === "written" ? "written" : "test";
      formatInput.value = value;

      pills.forEach((pill) => {
        const isActive = pill.dataset.format === value;
        pill.classList.toggle("is-active", isActive);
        pill.setAttribute("aria-pressed", isActive ? "true" : "false");
      });

      // Qayda bələdçilərini göstər/gizlət
      document.querySelectorAll("[data-format-guide]").forEach((guide) => {
        guide.hidden = guide.getAttribute("data-format-guide") !== value;
      });

      // Placeholder (yalnız editor boşdursa dəyişdiririk ki, yazılan mətn itməsin)
      if (editor) {
        const next =
          value === "written"
            ? editor.getAttribute("data-placeholder-written")
            : editor.getAttribute("data-placeholder-test");
        if (next) editor.setAttribute("placeholder", next);
      }

      // AI bloku da seçilmiş formata uyğun sual yaratsın (bank səhifəsi).
      document.querySelectorAll("[data-ai-format-mirror]").forEach((input) => {
        input.value = value;
      });
      const aiPanel = document.querySelector("[data-ai-question-form]");
      if (aiPanel) aiPanel.setAttribute("data-ai-context", value);
    }

    pills.forEach((pill) => {
      pill.addEventListener("click", function () {
        applyFormat(pill.dataset.format);
      });
    });

    // İlkin vəziyyəti tətbiq et (server-side seçimi qoru)
    applyFormat(formatInput.value || "test");
  });
})();
