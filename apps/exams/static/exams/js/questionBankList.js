/*
 * questionBankList.js - profil Sual Banki siyahisi ucun modal bindleri.
 * Kartlar adi link kimi yeni sehifeye kecir; drawer/iframe acilis mentiqi yoxdur.
 */
(function () {
  "use strict";

  // Axtarış "debounce" ilə avtomatik işləyir (düymə yoxdur) və hər sorğuda bütün
  // profil bölməsi AJAX ilə yenidən qurulur. Panel dəyişdiyi üçün input yeni DOM
  // elementi olur və fokus itir — istifadəçi yazmağa davam edə bilmir. Ona görə
  // caret + son yazı vaxtını yadda saxlayıb, swap istifadəçinin öz yazısından
  // qaynaqlanıbsa (qısa pəncərə), təzə input-a fokusu bərpa edirik.
  var qbSearchState = { caret: null, ts: 0 };
  var QB_REFOCUS_WINDOW_MS = 2500;

  function initQuestionBankSearch(root) {
    var input = root.querySelector(".qb-banklist-search input[name='bank_search']");
    if (!input) return;

    if (qbSearchState.ts && (Date.now() - qbSearchState.ts) < QB_REFOCUS_WINDOW_MS) {
      try {
        input.focus();
        var pos = qbSearchState.caret == null
          ? input.value.length
          : Math.min(qbSearchState.caret, input.value.length);
        input.setSelectionRange(pos, pos);
      } catch (e) { /* ignore */ }
    }

    if (input.getAttribute("data-qb-search-ready") === "1") return;
    input.setAttribute("data-qb-search-ready", "1");
    input.addEventListener("input", function () {
      qbSearchState.caret = input.selectionStart;
      qbSearchState.ts = Date.now();
    });
  }

  // Axtarışlı fənn/müəllim seçiciləri (EMSSearchableSelect) — yaratma kartı və
  // edit modalı. Hər seçici yanındakı hidden inputa dəyərini yazır; komponent
  // ikiqat init-ə qarşı özü qorunur (rootEl._emsSearchable).
  function bindPicker(pickerEl, url, hiddenInput) {
    if (!pickerEl || !url || !hiddenInput || !window.EMSSearchableSelect) return null;
    var pick = window.EMSSearchableSelect.create(pickerEl, { url: url });
    if (!pick) return null;
    pick.on("change", function () { hiddenInput.value = pick.value(); });
    return pick;
  }

  function initCreateCardPickers(root) {
    var card = root.querySelector(".js-qb-create-card");
    if (!card) return;
    var form = card.querySelector(".js-qb-create-form");
    if (!form) return;
    bindPicker(card.querySelector(".js-qbk-subject"), card.getAttribute("data-subject-url"),
      form.querySelector("[data-qbk-subject-input]"));
    bindPicker(card.querySelector(".js-qbk-teacher"), card.getAttribute("data-teacher-url"),
      form.querySelector("[data-qbk-teacher-input]"));
  }

  function initEditModalPickers() {
    var editForm = document.getElementById("editBankForm");
    if (!editForm) return { subject: null, teacher: null };
    return {
      subject: bindPicker(editForm.querySelector(".js-qbk-edit-subject"),
        editForm.getAttribute("data-subject-url"), editForm.querySelector("[data-qbk-subject-input]")),
      teacher: bindPicker(editForm.querySelector(".js-qbk-edit-teacher"),
        editForm.getAttribute("data-teacher-url"), editForm.querySelector("[data-qbk-teacher-input]"))
    };
  }

  // Modal açılanda seçicini bankın cari dəyəri ilə doldur. Köhnə sərbəst-mətn
  // fənn (kataloq id-siz) "text:<ad>" xüsusi id-si ilə saxlanır — server bu
  // dəyəri mətn kimi qoruyur (bax crud._resolve_bank_subject).
  function presetPicker(pick, hiddenInput, id, label, legacyPrefix) {
    if (!pick || !hiddenInput) return;
    pick.reset();
    hiddenInput.value = "";
    if (id) {
      pick.setValue(id, label || id);
    } else if (label && legacyPrefix) {
      pick.setValue(legacyPrefix + label, label);
    }
  }

  function initQuestionBankList(root) {
    root = root && typeof root.querySelectorAll === "function" ? root : document;

    initQuestionBankSearch(root);
    initCreateCardPickers(root);
    var editPickers = initEditModalPickers();

    root.querySelectorAll(".js-edit-bank").forEach(function (btn) {
      if (btn.getAttribute("data-qb-list-ready") === "1") return;
      btn.setAttribute("data-qb-list-ready", "1");
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();

        var editForm = document.getElementById("editBankForm");
        if (!editForm) return;

        editForm.action = btn.getAttribute("data-update-url") || "";
        var set = function (id, val) {
          var el = document.getElementById(id);
          if (!el) return;
          el.value = val;
          // Bootstrap-select toggle native dəyər dəyişimini "change" event-i kimi
          // eşitmir (proqramla təyin olunub) — görünüşü əl ilə sinxronlaşdırırıq.
          if (el._syncBootstrapSelect) el._syncBootstrapSelect();
        };

        set("editBankName2", btn.getAttribute("data-name") || "");
        set("editBankKind2", btn.getAttribute("data-kind") || "");
        set("editBankLanguage2", btn.getAttribute("data-language") || "");
        set("editBankFormat2", btn.getAttribute("data-format") || "test");

        presetPicker(editPickers.subject, editForm.querySelector("[data-qbk-subject-input]"),
          btn.getAttribute("data-subject-id") || "", btn.getAttribute("data-subject-label") || "", "text:");
        presetPicker(editPickers.teacher, editForm.querySelector("[data-qbk-teacher-input]"),
          btn.getAttribute("data-teacher-id") || "", btn.getAttribute("data-teacher-label") || "", "");

        var modalEl = document.getElementById("editBankModal");
        if (typeof bootstrap !== "undefined" && modalEl) {
          bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }
      });
    });

    root.querySelectorAll(".js-delete-bank").forEach(function (btn) {
      if (btn.getAttribute("data-qb-list-ready") === "1") return;
      btn.setAttribute("data-qb-list-ready", "1");
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();

        var deleteForm = document.getElementById("deleteBankForm");
        if (!deleteForm) return;

        deleteForm.action = btn.getAttribute("data-delete-url") || "";
        var deleteBody = document.getElementById("deleteBankBody");
        var name = btn.getAttribute("data-name") || "";
        if (deleteBody) {
          deleteBody.textContent = "\"" + name + gettext("\" bankı və içindəki bütün suallar həmişəlik silinəcək. Davam edək?");
        }

        var modalEl = document.getElementById("deleteBankModal");
        if (typeof bootstrap !== "undefined" && modalEl) {
          bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }
      });
    });
  }

  function run(detail) {
    if (detail && detail.section && detail.section !== "question-bank") return;
    initQuestionBankList(detail && detail.panel ? detail.panel : document);
  }

  window.EMSQuestionBankList = { init: initQuestionBankList };
  if (window.EMSReady) {
    window.EMSReady(run);
  } else {
    document.addEventListener("DOMContentLoaded", function () { run(null); });
  }
})();
