/*
 * bankManagement.js — yalnız müstəqil bank idarəetmə səhifəsi üçün.
 * Bankı redaktə (modal), bankı sil, dil üzrə toplu sil — təsdiq modalı ilə.
 * Təsdiq üçün teacher_questions_bank.js-dəki window.qbConfirm istifadə olunur.
 */
document.addEventListener("DOMContentLoaded", function () {
  var i18n = window.TEACHER_QUESTIONS_BANK_I18N || {};
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
        title: i18n.bankDeleteTitle || "Bankı sil",
        body: i18n.bankDeleteBody || "Bütün sual bankı və içindəki bütün suallar həmişəlik silinəcək. Davam edək?",
        okLabel: i18n.okDelete || "Bəli, sil",
        onConfirm: function () { if (deleteForm) deleteForm.submit(); },
      });
    });
  });
});
