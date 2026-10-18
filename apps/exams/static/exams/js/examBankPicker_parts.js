/*
 * examBankPicker_parts.js — «Suallar bankından seç» modalının köməkçiləri (2026-10-19).
 * --------------------------------------------------------------------------
 * examBankPicker.js-dən ƏVVƏL yüklənir (600 sətir qapısı üçün ayrılıb). DOM-a bağlı vəziyyət
 * saxlamır — hər funksiya modal gövdəsini (`getRoot()`) özü soruşur, ona görə AJAX swap-dan
 * sonra da düzgün işləyir.
 *
 *   EMSBankPickerParts.selection(getRoot) → seçim anbarı:
 *       açıq rejim (selected) və «Bütün N sualı seç» rejimi (selectAll + excluded); sayğac,
 *       «Görünənlərin hamısını seç» (tri-state) və «Əlavə et» düyməsinin vəziyyəti.
 *   EMSBankPickerParts.errorState(tr, status) → `ems-state--error` kartı (+ «Yenidən cəhd et»).
 *   EMSBankPickerParts.cloneTemplate(id)      → <template> məzmununun klonu (skeleton).
 *   EMSBankPickerParts.visibleFocusable(root) → fokus tələsi üçün görünən elementlər.
 */
(function () {
  "use strict";

  if (window.EMSBankPickerParts) return;

  var FOCUSABLE = [
    "a[href]",
    "button:not([disabled])",
    "input:not([disabled]):not([type=hidden])",
    "select:not([disabled]):not(.is-enhanced)",
    "textarea:not([disabled])",
    '[tabindex]:not([tabindex="-1"])',
  ].join(",");

  function visibleFocusable(root) {
    return Array.prototype.slice.call(root.querySelectorAll(FOCUSABLE)).filter(function (el) {
      return el.offsetWidth || el.offsetHeight || el.getClientRects().length;
    });
  }

  function cloneTemplate(id) {
    var tpl = document.getElementById(id);
    if (!tpl || !tpl.content) return document.createDocumentFragment();
    return tpl.content.cloneNode(true);
  }

  function errorState(tr, status) {
    var box = document.createElement("div");
    box.className = "ems-state ems-state--error bankpicker-state";
    box.setAttribute("role", "alert");
    var icon = document.createElement("i");
    icon.className = "fas fa-triangle-exclamation ems-state__icon";
    icon.setAttribute("aria-hidden", "true");
    var title = document.createElement("p");
    title.className = "ems-state__title";
    title.textContent = tr("load-error", "Siyahı yüklənmədi");
    var text = document.createElement("p");
    text.className = "ems-state__body";
    text.textContent =
      status === 403
        ? tr("forbidden", "Bu imtahana sual əlavə etmək icazəniz yoxdur.")
        : tr("load-error-body", "Bağlantını yoxlayıb yenidən cəhd edin.");
    box.appendChild(icon);
    box.appendChild(title);
    box.appendChild(text);
    if (status !== 403) {
      var retry = document.createElement("button");
      retry.type = "button";
      retry.className = "ems-btn";
      retry.setAttribute("data-picker-retry", "");
      retry.textContent = tr("retry", "Yenidən cəhd et");
      box.appendChild(retry);
    }
    return box;
  }

  function selection(getRoot) {
    var api = {
      selected: new Set(),
      excluded: new Set(),
      selectAll: false,
      total: 0,
      busy: false, // «Əlavə et» gedərkən düymə açılmasın
    };

    api.reset = function () {
      api.selectAll = false;
      api.selected.clear();
      api.excluded.clear();
    };

    api.boxes = function (enabledOnly) {
      var root = getRoot();
      if (!root) return [];
      var list = Array.prototype.slice.call(root.querySelectorAll("[data-picker-checkbox]"));
      return enabledOnly ? list.filter(function (cb) { return !cb.disabled; }) : list;
    };

    api.isChosen = function (id) {
      return api.selectAll ? !api.excluded.has(id) : api.selected.has(id);
    };

    api.set = function (id, on) {
      if (api.selectAll) {
        if (on) api.excluded.delete(id);
        else api.excluded.add(id);
      } else if (on) {
        api.selected.add(id);
      } else {
        api.selected.delete(id);
      }
    };

    api.count = function () {
      return api.selectAll ? Math.max(0, api.total - api.excluded.size) : api.selected.size;
    };

    api.chooseAllMatching = function () {
      api.selectAll = true;
      api.excluded.clear();
      api.sync();
    };

    api.togglePage = function (on) {
      api.boxes(true).forEach(function (cb) {
        cb.checked = on;
        api.set(cb.value, on);
      });
      api.render();
    };

    // Content yeniləndikdən sonra: ümumi sayı oxu (yalnız SEÇİLƏ BİLƏN — imtahanda olmayan) və sinxronla.
    api.readTotal = function () {
      var root = getRoot();
      var totalEl = root && root.querySelector("[data-picker-total]");
      api.total = totalEl ? parseInt(totalEl.getAttribute("data-picker-total"), 10) || 0 : 0;
    };

    api.sync = function () {
      api.boxes(false).forEach(function (cb) {
        cb.checked = !cb.disabled && api.isChosen(cb.value);
      });
      api.render();
    };

    api.render = function () {
      var root = getRoot();
      if (!root) return;
      var n = api.count();
      var label = root.querySelector("[data-picker-selected-count]");
      if (label) {
        var tpl = label.getAttribute("data-count-template") || "{n}";
        label.textContent = n ? tpl.replace("{n}", String(n)) : label.getAttribute("data-count-empty") || "0";
        label.classList.toggle("has-selection", n > 0);
      }
      var attach = root.querySelector("[data-picker-attach]");
      if (attach && !api.busy) attach.disabled = n === 0;

      var pageToggle = root.querySelector("[data-picker-page-toggle]");
      if (pageToggle) {
        var list = api.boxes(true);
        var checked = list.filter(function (cb) { return cb.checked; }).length;
        pageToggle.disabled = list.length === 0;
        pageToggle.checked = list.length > 0 && checked === list.length;
        pageToggle.indeterminate = checked > 0 && checked < list.length;
      }
    };

    return api;
  }

  window.EMSBankPickerParts = {
    selection: selection,
    errorState: errorState,
    cloneTemplate: cloneTemplate,
    visibleFocusable: visibleFocusable,
  };
})();
