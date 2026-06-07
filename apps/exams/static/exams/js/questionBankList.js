/*
 * questionBankList.js - profil Sual Banki siyahisi ucun modal bindleri.
 * Kartlar adi link kimi yeni sehifeye kecir; drawer/iframe acilis mentiqi yoxdur.
 */
(function () {
  "use strict";

  function initQuestionBankList(root) {
    root = root && typeof root.querySelectorAll === "function" ? root : document;

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
          if (el) el.value = val;
        };

        set("editBankName2", btn.getAttribute("data-name") || "");
        set("editBankSubject2", btn.getAttribute("data-subject") || "");
        set("editBankLanguage2", btn.getAttribute("data-language") || "");
        set("editBankFormat2", btn.getAttribute("data-format") || "test");

        var shared = document.getElementById("editBankShared2");
        if (shared) shared.checked = btn.getAttribute("data-shared") === "1";

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
          deleteBody.textContent = "\"" + name + "\" bankı və içindəki bütün suallar həmişəlik silinəcək. Davam edək?";
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
