/*
 * journal_close.js — RİM semestr-sonu jurnal bağlaması (profil bölməsi).
 *
 * CSP: bu bölmədə inline <script> YOXDUR — bütün davranış buradadır. Dinamik
 * dəyərlər DOM-dan oxunur: fakültə/kafedra siyahıları `json_script` bloklarından,
 * i18n sətirləri `#jcI18n` data-atributlarından, cari seçim isə `.jc` konteynerinin
 * data-scope / data-unit atributlarından.
 *
 * Nə edir:
 *   1. əhatə (org / fakültə / kafedra) seçiminə görə «Bölmə» select-ini doldurur;
 *   2. seçimi POST formalarındakı gizli sahələrə güzgüləyir (server GET önizləməsi
 *      ilə eyni əhatəni bağlasın);
 *   3. dağıdıcı əməliyyatlar üçün təsdiq istəyir;
 *   4. mövcud xəbərdarlığı «Redaktə» ilə formaya yükləyir.
 *
 * kollokvium_windows.js kimi plain IIFE: bölmə full-page render olunur, ona görə
 * hər yüklənişdə bir dəfə bağlanır.
 */
(function () {
  "use strict";

  var root = document.querySelector(".jc");
  if (!root) return;

  var i18nEl = document.getElementById("jcI18n");
  function t(key) {
    return i18nEl ? i18nEl.getAttribute(key) || "" : "";
  }

  function readJson(id) {
    var el = document.getElementById(id);
    if (!el) return [];
    try {
      return JSON.parse(el.textContent) || [];
    } catch (e) {
      return [];
    }
  }

  var FACULTIES = readJson("jc-faculties-data");
  var DEPARTMENTS = readJson("jc-departments-data");

  // bootstrap-select bu bölmə üçün açıq re-init (full-page render).
  try {
    if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.init(document);
  } catch (e) {
    /* seçici olmadan da native <select> işləyir */
  }

  document.querySelectorAll("[data-autosubmit]").forEach(function (sel) {
    sel.addEventListener("change", function () {
      if (sel.form) sel.form.submit();
    });
  });

  function optionsFor(scope) {
    if (scope === "faculty") return FACULTIES;
    if (scope === "department") return DEPARTMENTS;
    return [];
  }

  function fillUnits(select, scope, selectedId) {
    if (!select) return;
    var rows = optionsFor(scope);
    select.innerHTML = "";
    var blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "—";
    select.appendChild(blank);
    rows.forEach(function (row) {
      var opt = document.createElement("option");
      opt.value = String(row.id);
      opt.textContent = row.name;
      if (selectedId && String(row.id) === String(selectedId)) opt.selected = true;
      select.appendChild(opt);
    });
    try {
      if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.refresh(select);
    } catch (e) {
      /* refresh opsionaldır */
    }
  }

  function toggleWrap(wrap, visible) {
    if (!wrap) return;
    wrap.classList.toggle("jc-field--hidden", !visible);
  }

  function bindScope(scopeSel, unitSel, unitWrap, unitLabel, initialUnit, onChange) {
    if (!scopeSel) return;
    function apply() {
      var scope = scopeSel.value;
      var isUnit = scope === "faculty" || scope === "department";
      toggleWrap(unitWrap, isUnit);
      if (unitLabel) unitLabel.textContent = scope === "department" ? t("data-department") : t("data-faculty");
      fillUnits(unitSel, scope, isUnit ? initialUnit : "");
      if (typeof onChange === "function") onChange(scope, unitSel ? unitSel.value : "");
    }
    scopeSel.addEventListener("change", function () {
      initialUnit = "";
      apply();
    });
    if (unitSel && typeof onChange === "function") {
      unitSel.addEventListener("change", function () {
        onChange(scopeSel.value, unitSel.value);
      });
    }
    apply();
  }

  // ── 1) Toplu bağlama: əhatə seçimi + gizli sahələrin güzgülənməsi ──────
  var bulkScope = root.querySelector("[data-jc-scope]");
  var bulkUnit = root.querySelector("[data-jc-unit]");
  var bulkWrap = root.querySelector("[data-jc-unit-wrap]");
  var bulkLabel = root.querySelector("[data-jc-unit-label]");

  function mirror(scope, unitId) {
    root.querySelectorAll("[data-jc-mirror-scope]").forEach(function (el) {
      el.value = scope;
    });
    root.querySelectorAll("[data-jc-mirror-unit]").forEach(function (el) {
      el.value = scope === "organization" ? "" : unitId || "";
    });
  }

  bindScope(bulkScope, bulkUnit, bulkWrap, bulkLabel, root.getAttribute("data-unit") || "", mirror);

  // ── 2) Xəbərdarlıq forması: eyni əhatə davranışı ───────────────────────
  var noticeScope = root.querySelector("[data-jc-notice-scope]");
  var noticeUnit = root.querySelector("[data-jc-notice-unit]");
  var noticeWrap = root.querySelector("[data-jc-notice-unit-wrap]");
  var noticeLabel = root.querySelector("[data-jc-notice-unit-label]");
  bindScope(noticeScope, noticeUnit, noticeWrap, noticeLabel, "");

  // «Redaktə» → mövcud sətri formaya yüklə.
  root.querySelectorAll("[data-jc-edit-notice]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var idField = root.querySelector("[data-jc-notice-id]");
      var dateField = root.querySelector("[data-jc-notice-date]");
      var msgField = root.querySelector("[data-jc-notice-message]");
      if (idField) idField.value = btn.getAttribute("data-id") || "";
      if (dateField) dateField.value = btn.getAttribute("data-date") || "";
      if (msgField) msgField.value = btn.getAttribute("data-message") || "";
      if (noticeScope) {
        noticeScope.value = btn.getAttribute("data-scope") || "organization";
        var unitId = btn.getAttribute("data-unit") || "";
        var isUnit = noticeScope.value !== "organization";
        toggleWrap(noticeWrap, isUnit);
        if (noticeLabel) {
          noticeLabel.textContent =
            noticeScope.value === "department" ? t("data-department") : t("data-faculty");
        }
        fillUnits(noticeUnit, noticeScope.value, unitId);
        try {
          if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.refresh(noticeScope);
        } catch (e) {
          /* refresh opsionaldır */
        }
      }
    });
  });

  // ── 3) Dağıdıcı əməliyyatlar üçün təsdiq ───────────────────────────────
  root.querySelectorAll("[data-jc-confirm-form]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var trigger = form.querySelector("[data-jc-confirm-key]");
      var key = trigger ? trigger.getAttribute("data-jc-confirm-key") : "";
      var message =
        key === "close" ? t("data-confirm-close") : key === "reopen" ? t("data-confirm-reopen") : t("data-confirm-delete");
      if (message && !window.confirm(message)) event.preventDefault();
    });
  });
})();
