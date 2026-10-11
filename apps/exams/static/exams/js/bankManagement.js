/*
 * bankManagement.js — yalnız kitabxana bankının idarəetmə səhifəsi (question_bank_detail).
 *
 * 2026-10-10 redizayn: «Bankı redaktə et» artıq Bootstrap dialoqudur (data-bs-toggle —
 * JS lazım deyil); burada yalnız «Bankı sil» qalır: qlobal EMSConfirm (təhlükə tonu),
 * ləğvdə fokus düyməyə qayıdır. AJAX-safe: EMSDelegate (document-ə bir dəfə).
 */
(function () {
  "use strict";

  function onDeleteBank(event, button) {
    var form = document.getElementById("bankDeleteForm");
    if (!form) return;
    var i18n = window.TEACHER_QUESTIONS_BANK_I18N || {};
    var opts = {
      title: i18n.bankDeleteTitle || gettext("Bankı sil"),
      body: i18n.bankDeleteBody || gettext("Bütün sual bankı və içindəki bütün suallar həmişəlik silinəcək. Davam edək?"),
      confirmLabel: i18n.okDelete || gettext("Bəli, sil"),
      danger: true,
    };
    // EMSConfirm base.html-də qlobal yüklənir; yoxdursa (skript xətası) dağıdıcı əməl
    // təsdiqsiz İCRA OLUNMUR — native confirm() qadağandır (FE-F19).
    if (!window.EMSConfirm || typeof window.EMSConfirm.open !== "function") return;
    window.EMSConfirm.open(opts).then(function (ok) {
      if (ok) form.submit();
      else if (document.contains(button)) button.focus();
    });
  }

  if (window.EMSDelegate) window.EMSDelegate.on("click", ".js-delete-bank", onDeleteBank);
})();
