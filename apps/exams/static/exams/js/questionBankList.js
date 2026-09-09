/*
 * questionBankList.js — «Sual Bankı» bölməsinin dialoq davranışı.
 *
 * 2026-09-09: ekran `ems_ui` komponentlərinə keçdi — Bootstrap modalları
 * (`editBankModal` / `deleteBankModal`) əvəzinə `EMSOverlay` dialoqları,
 * silmə isə `EMSConfirm` təsdiqi ilə adi POST forması.  Axtarış artıq
 * `ems_ui/filter_bar.js`-in avto filtr panelindədir (fokus bərpası orada),
 * ona görə köhnə `qb-banklist-search` refokus məntiqi silindi.
 *
 * AJAX-SAFE: bütün dinləyicilər `EMSDelegate` ilə document səviyyəsindədir;
 * seçicilər isə hər panel swap-ından sonra `EMSReady` ilə yenidən qurulur
 * (komponent ikiqat init-ə qarşı özü qorunur).
 */
(function () {
  "use strict";

  // Axtarışlı fənn/müəllim seçiciləri (EMSSearchableSelect) — yaratma və
  // redaktə dialoqları. Hər seçici yanındakı hidden inputa dəyərini yazır.
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

  var editPickers = { subject: null, teacher: null };

  function initEditDialogPickers() {
    var editForm = document.getElementById("editBankForm");
    if (!editForm) {
      editPickers = { subject: null, teacher: null };
      return;
    }
    editPickers = {
      subject: bindPicker(editForm.querySelector(".js-qbk-edit-subject"),
        editForm.getAttribute("data-subject-url"), editForm.querySelector("[data-qbk-subject-input]")),
      teacher: bindPicker(editForm.querySelector(".js-qbk-edit-teacher"),
        editForm.getAttribute("data-teacher-url"), editForm.querySelector("[data-qbk-teacher-input]"))
    };
  }

  // Dialoq açılanda seçicini bankın cari dəyəri ilə doldur. Köhnə sərbəst-mətn
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

  function setField(id, value) {
    var el = document.getElementById(id);
    if (!el) return;
    el.value = value;
    // Bootstrap-select toggle proqramla təyin olunmuş dəyəri "change" kimi
    // eşitmir — görünüşü əl ilə sinxronlaşdırırıq.
    if (window.EMSBootstrapSelect) {
      window.EMSBootstrapSelect.sync(el);
    } else if (el._syncBootstrapSelect) {
      el._syncBootstrapSelect();
    }
  }

  function initQuestionBankList(root) {
    root = root && typeof root.querySelectorAll === "function" ? root : document;
    initCreateCardPickers(root);
    initEditDialogPickers();
  }

  window.EMSDelegate.on("click", "[data-qb-edit]", function (event, btn) {
    event.preventDefault();
    var editForm = document.getElementById("editBankForm");
    if (!editForm) return;

    editForm.action = btn.getAttribute("data-update-url") || "";
    setField("editBankName2", btn.getAttribute("data-name") || "");
    setField("editBankKind2", btn.getAttribute("data-kind") || "");
    setField("editBankLanguage2", btn.getAttribute("data-language") || "");
    setField("editBankFormat2", btn.getAttribute("data-format") || "test");

    presetPicker(editPickers.subject, editForm.querySelector("[data-qbk-subject-input]"),
      btn.getAttribute("data-subject-id") || "", btn.getAttribute("data-subject-label") || "", "text:");
    presetPicker(editPickers.teacher, editForm.querySelector("[data-qbk-teacher-input]"),
      btn.getAttribute("data-teacher-id") || "", btn.getAttribute("data-teacher-label") || "", "");

    if (window.EMSOverlay) {
      window.EMSOverlay.open("qbEditDialog");
    }
  });

  // Silmə: ayrıca modal YOX — qlobal təsdiq dialoqu (EMSConfirm), sonra POST.
  window.EMSDelegate.on("submit", "form[data-qb-delete-form]", function (event, form) {
    if (form.getAttribute("data-qb-confirmed") === "1") return;
    var message = form.getAttribute("data-confirm") || "";
    if (!message || !window.EMSConfirm) return;
    event.preventDefault();
    window.EMSConfirm.open({ body: message, danger: true }).then(function (ok) {
      if (!ok) return;
      form.setAttribute("data-qb-confirmed", "1");
      form.submit();
    });
  });

  window.EMSQuestionBankList = { init: initQuestionBankList };

  function run(detail) {
    if (detail && detail.section && detail.section !== "question-bank") return;
    initQuestionBankList(detail && detail.panel ? detail.panel : document);
  }

  if (window.EMSReady) {
    window.EMSReady(run);
  } else {
    document.addEventListener("DOMContentLoaded", function () { run(null); });
  }
})();
