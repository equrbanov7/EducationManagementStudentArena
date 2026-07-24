/* courses/js/courses_i18n.js
 * Source: courses/partials/_courses_assets_js.html
 * Bridges the shared window.COURSES_I18N labels (consumed by forms.js / modal.js)
 * from data-* attributes so no inline script/nonce is needed.
 */
(function () {
  "use strict";
  var el = document.getElementById("courses-i18n-data");
  if (!el) return;
  window.COURSES_I18N = {
    errorsLabel: el.dataset.errorsLabel,
    pleaseWait: el.dataset.pleaseWait,
    retryError: el.dataset.retryError
  };
})();
