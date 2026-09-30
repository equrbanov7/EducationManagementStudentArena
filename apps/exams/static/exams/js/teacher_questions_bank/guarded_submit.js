/* =========================================================================
   Sual bankı (imtahan) — «son aktiv suallar» təsdiq axını (QB 2026-09-30)

   NİYƏ: canlı imtahandan sonra müəllim bütün aktiv sualları seçib silmək
   istəyəndə server «aktiv imtahanın son aktiv sualı…» deyib dalana dirənirdi.
   İndi sil/deaktiv formaları AJAX ilə göndərilir; server 409 +
   `exam_deactivation_required` qaytaranda EMSConfirm açılır ("imtahan deaktiv
   ediləcək — davam edilsin?"), razılıqda `confirm_exam_deactivation=1` ilə
   təkrar göndərilir. `exam_in_use` (açıq cəhd / canlı sessiya / final zal) və
   digər imtinalar EMSToast ilə göstərilir. Uğurda server `redirect_url` verir
   (Django mesajları orada toast kimi görünür).

   Yalnız `.qb-page[data-qm-context="exam"]` səhifəsində işləyir (müstəqil
   sual bankı səhifəsi adi form göndərişində qalır). Gözlənilməz cavabda
   (şəbəkə, HTML xəta səhifəsi) köhnə yol — adi form göndərişi.

   AJAX-SAFE: idempotent IIFE, yükləmədə DOM-a bağlanmır; DOM hər çağırışda oxunur.
   ========================================================================= */
(function (window, document) {
  "use strict";

  if (window.QBGuardedSubmit) {
    return;
  }

  var DEFAULT_CONFIRM_FIELD = "confirm_exam_deactivation";
  var inFlight = false;

  function enabled() {
    return !!(
      document.querySelector('.qb-page[data-qm-context="exam"]') &&
      window.EMSCore &&
      typeof window.EMSCore.fetchJSON === "function" &&
      typeof window.FormData === "function"
    );
  }

  function plainSubmit(form, fields) {
    Object.keys(fields || {}).forEach(function (name) {
      var input = null;
      Array.prototype.forEach.call(form.querySelectorAll("input[data-qb-extra-field]"), function (item) {
        if (item.name === name) input = item;
      });
      if (!input) {
        input = document.createElement("input");
        input.type = "hidden";
        input.name = name;
        input.setAttribute("data-qb-extra-field", "");
        form.appendChild(input);
      }
      input.value = fields[name];
    });
    form.submit();
  }

  function showError(message) {
    if (window.EMSToast && typeof window.EMSToast.show === "function") {
      window.EMSToast.show(message, "error", 8000);
    }
  }

  function send(form, fields) {
    var data = new window.FormData(form);
    Object.keys(fields || {}).forEach(function (name) {
      data.set(name, fields[name]);
    });
    inFlight = true;
    return window.EMSCore.fetchJSON(form.action || window.location.href, { method: "POST", body: data })
      .then(function (payload) {
        inFlight = false;
        if (payload && payload.redirect_url) {
          window.location.assign(payload.redirect_url);
          return;
        }
        window.location.reload();
      })
      .catch(function (error) {
        inFlight = false;
        var payload = error && error.payload;
        if (payload && typeof payload === "object") {
          if (payload.code === "exam_deactivation_required" && payload.confirm) {
            if (!window.EMSConfirm || typeof window.EMSConfirm.open !== "function") {
              plainSubmit(form, fields); // server tərəfi təsdiq səhifəsi göstərir
              return;
            }
            return window.EMSConfirm.open({
              title: payload.confirm.title || "",
              body: payload.confirm.body || "",
              confirmLabel: payload.confirm.confirm_label || "",
              danger: true,
            }).then(function (ok) {
              if (!ok) return;
              var next = Object.assign({}, fields || {});
              next[payload.confirm_field || DEFAULT_CONFIRM_FIELD] = "1";
              return send(form, next);
            });
          }
          if (payload.message) {
            showError(payload.message);
            return;
          }
          if (payload.view_as_blocked) {
            return; // EMSCore.fetchJSON səbəbi artıq toast ilə göstərib.
          }
        }
        plainSubmit(form, fields);
      });
  }

  function submit(form, fields) {
    if (!form || inFlight) return;
    send(form, fields || {});
  }

  window.QBGuardedSubmit = { enabled: enabled, submit: submit };
})(window, document);
