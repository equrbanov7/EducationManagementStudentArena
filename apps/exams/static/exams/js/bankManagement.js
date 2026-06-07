/*
 * bankManagement.js — yalnız müstəqil bank idarəetmə səhifəsi üçün.
 * Bankı redaktə (modal), bankı sil, dil üzrə toplu sil — təsdiq modalı ilə.
 * Təsdiq üçün teacher_questions_bank.js-dəki window.qbConfirm istifadə olunur.
 */
document.addEventListener("DOMContentLoaded", function () {
  var confirmFn = window.qbConfirm || function (o) {
    if (window.confirm(o.body || "?") && typeof o.onConfirm === "function") o.onConfirm();
  };

  // ── Bankı redaktə (modal aç/bağla) ──
  var editModal = document.getElementById("bankEditModal");
  function openEdit() {
    if (!editModal) return;
    editModal.classList.add("is-open");
    editModal.setAttribute("aria-hidden", "false");
  }
  function closeEdit() {
    if (!editModal) return;
    editModal.classList.remove("is-open");
    editModal.setAttribute("aria-hidden", "true");
  }
  document.querySelectorAll(".js-edit-bank-open").forEach(function (b) { b.addEventListener("click", openEdit); });
  document.querySelectorAll(".js-edit-bank-close").forEach(function (b) { b.addEventListener("click", closeEdit); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeEdit(); });

  // ── Bütün bankı sil ──
  var deleteForm = document.getElementById("bankDeleteForm");
  document.querySelectorAll(".js-delete-bank").forEach(function (b) {
    b.addEventListener("click", function () {
      confirmFn({
        variant: "danger",
        title: "Bankı sil",
        body: "Bütün sual bankı və içindəki bütün suallar həmişəlik silinəcək. Davam edək?",
        okLabel: "Bəli, sil",
        onConfirm: function () { if (deleteForm) deleteForm.submit(); },
      });
    });
  });

  // ── Dil üzrə bütün sualları sil ──
  var langForm = document.getElementById("bankLangDeleteForm");
  var langVal = document.getElementById("bankLangDeleteValue");
  document.querySelectorAll(".js-delete-language").forEach(function (b) {
    b.addEventListener("click", function () {
      var lang = b.getAttribute("data-language") || "";
      var count = b.getAttribute("data-count") || "0";
      confirmFn({
        variant: "danger",
        title: "Dil üzrə sil",
        body: "Seçilmiş dildəki " + count + " sual həmişəlik silinəcək. Davam edək?",
        okLabel: "Bəli, sil",
        onConfirm: function () {
          if (langForm && langVal) { langVal.value = lang; langForm.submit(); }
        },
      });
    });
  });
});
