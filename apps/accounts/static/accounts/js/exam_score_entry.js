/*
 * exam_score_entry.js — İmtahan Mərkəzi: kağız imtahan balının daxil edilməsi.
 *
 * CSP: bu bölmədə inline <script> YOXDUR — bütün davranış buradadır. Dinamik
 * dəyərlər DOM-dan oxunur: i18n sətirləri `#eseI18n` data-atributlarından,
 * sətrin vəziyyəti isə `[data-ese-row]`-un data-has-score / data-initial
 * atributlarından.
 *
 * Nə edir:
 *   1. dəyişdirilmiş bal xanasını işarələyir (sarı «is-dirty»);
 *   2. ARTIQ yazılmış balı dəyişəndə səbəb + qeyd + sənəd sahələrini MƏCBURİ
 *      edir (server qatı da eyni qaydanı tətbiq edir — bu, yalnız erkən UX);
 *   3. göndərişdən əvvəl belə sətirləri yoxlayır və təsdiq istəyir.
 *
 * journal_close.js kimi plain IIFE: bölmə full-page render olunur, ona görə
 * hər yüklənişdə bir dəfə bağlanır.
 */
(function () {
  "use strict";

  var root = document.querySelector(".ese");
  if (!root) return;

  var i18nEl = document.getElementById("eseI18n");
  function t(key) {
    return i18nEl ? i18nEl.getAttribute(key) || "" : "";
  }

  function rowIsChanged(row) {
    var input = row.querySelector("[data-ese-score]");
    if (!input) return false;
    var initial = (input.getAttribute("data-initial") || "").trim();
    var current = (input.value || "").trim();
    return current !== "" && current !== initial;
  }

  /* Sonrakı dəyişiklik = təqdimatlı: bal ARTIQ yazılıbsa və dəyişdirilirsə,
     səbəb + qeyd + sənəd üçü də tələb olunur (sahibin qaydası E7). */
  function needsJustification(row) {
    return row.getAttribute("data-has-score") === "1" && rowIsChanged(row);
  }

  function justificationComplete(row) {
    var reason = row.querySelector("select[name^='reason__']");
    var note = row.querySelector("input[name^='note__']");
    var file = row.querySelector("input[type='file']");
    return !!(
      reason &&
      reason.value &&
      note &&
      (note.value || "").trim() &&
      file &&
      file.files &&
      file.files.length
    );
  }

  function syncRow(row) {
    var input = row.querySelector("[data-ese-score]");
    var just = row.querySelector("[data-ese-just]");
    if (input) input.classList.toggle("is-dirty", rowIsChanged(row));
    if (just) just.classList.toggle("is-required", needsJustification(row));
  }

  var rows = Array.prototype.slice.call(root.querySelectorAll("[data-ese-row]"));
  rows.forEach(function (row) {
    syncRow(row);
    row.addEventListener("input", function () {
      syncRow(row);
    });
    row.addEventListener("change", function () {
      syncRow(row);
    });
  });

  var form = root.querySelector("[data-ese-form]");
  if (!form) return;

  form.addEventListener("submit", function (event) {
    var pending = rows.filter(needsJustification);
    if (!pending.length) return;

    var incomplete = pending.filter(function (row) {
      return !justificationComplete(row);
    });
    if (incomplete.length) {
      event.preventDefault();
      var focusTarget = incomplete[0].querySelector("select[name^='reason__']");
      if (focusTarget) focusTarget.focus();
      window.alert(t("data-need-justification"));
      return;
    }
    if (!window.confirm(t("data-confirm-change"))) event.preventDefault();
  });
})();
