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

   2026-11-11: (a) `questions_have_answers` + təsdiq mətni → «istifadə olunmuş N sual silinə bilməz —
   deaktiv edilsin?»; razılıqda `on_used=deactivate` ilə təkrar; (b) QBLive (live.js) varsa sorğu
   `X-QB-Partial: 1` ilə gedir, cavabdakı mesajlar toast olur və yalnız canlı bölgələr yenilənir.

   Yalnız `[data-qm-context="exam"]` səhifəsində işləyir (2026-10-10 redizaynda
   kök `.etp-page` oldu — sinif yox, data-atribut yoxlanır) (müstəqil
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
      document.querySelector('[data-qm-context="exam"]') &&
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

  function live() {
    var api = window.QBLive;
    return api && typeof api.enabled === "function" && api.enabled() ? api : null;
  }

  function confirmAndResend(form, fields, payload, extraName, extraValue) {
    if (!window.EMSConfirm || typeof window.EMSConfirm.open !== "function") {
      plainSubmit(form, fields); // server tərəfi təsdiq səhifəsi / izah göstərir
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
      next[extraName] = extraValue;
      return send(form, next);
    });
  }

  function send(form, fields) {
    var data = new window.FormData(form);
    Object.keys(fields || {}).forEach(function (name) {
      data.set(name, fields[name]);
    });
    inFlight = true;
    var liveApi = live();
    var headers = {};
    if (liveApi) headers[liveApi.PARTIAL_HEADER || "X-QB-Partial"] = "1";
    return window.EMSCore.fetchJSON(form.action || window.location.href, { method: "POST", body: data, headers: headers })
      .then(function (payload) {
        inFlight = false;
        // 2026-11-11: səhifə yenidən yüklənmir — mesajlar toast, siyahı fraqmentlə yenilənir.
        if (liveApi && payload && payload.redirect_url && Array.isArray(payload.messages)) {
          liveApi.showMessages(payload.messages);
          liveApi.refresh(payload.redirect_url, { push: false });
          return;
        }
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
            return confirmAndResend(form, fields, payload, payload.confirm_field || DEFAULT_CONFIRM_FIELD, "1");
          }
          // 2026-11-11: istifadə olunmuş suallar silinmir — «deaktiv edilsin?» təklifi.
          if (payload.code === "questions_have_answers" && payload.confirm && payload.fallback_field) {
            return confirmAndResend(form, fields, payload, payload.fallback_field, payload.fallback_value || "deactivate");
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
