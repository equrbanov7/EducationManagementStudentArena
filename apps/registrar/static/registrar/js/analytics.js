/*
 * Akademik analitika (U10) — progressive enhancement.
 * - The period <select data-autosubmit> submits its form on change (a <noscript>
 *   submit button covers the no-JS case).
 * - .analytics-risk-fill bars receive their width from data-width (0–100) so the
 *   template stays free of inline styles (CSP).
 */
(function () {
  "use strict";

  var select = document.querySelector(".analytics-period-select[data-autosubmit]");
  if (select && select.form) {
    select.addEventListener("change", function () {
      select.form.submit();
    });
  }

  document.querySelectorAll(".analytics-risk-fill[data-width]").forEach(function (bar) {
    var value = parseFloat(bar.getAttribute("data-width"));
    if (!isNaN(value)) {
      bar.style.width = Math.max(0, Math.min(100, value)) + "%";
    }
  });
})();
