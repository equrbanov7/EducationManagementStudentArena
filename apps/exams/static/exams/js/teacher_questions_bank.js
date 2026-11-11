/* =========================================================================
   teacher_questions_bank.js — imtahanın «Sual bankı» + kitabxana bankı səhifəsi.

   2026-10-10 redizayn (sahib «modern UX/UI»):
   - təsdiqlər qlobal EMSConfirm dialoqu ilə (səhifənin öz təsdiq modalı yoxdur);
     ləğvdə fokus əməli açan düyməyə qayıdır;
   - «Bütün sual bankını sil» YAZILI təsdiqlə: #qbTypedConfirmModal-da imtahanın
     adı yazılmayınca «Hamısını sil» söndürülüdür;
   - sual modalı (yarat/redaktə) bağlananda fokus onu açan düyməyə qayıdır.
   POST müqaviləsi dəyişməyib: bulk_action = activate|deactivate|delete|
   delete_language|delete_all (+ guarded_submit.js «son aktiv suallar» axını).

   2026-11-11 (sahib «ləngdir» + toplu əməllər): dinləyicilər kökə DELEGASİYA ilə bağlanır — siyahı
   canlı yenilənəndə (teacher_questions_bank/live.js) yenidən bağlamaq lazım deyil; süzgəc / əməl /
   sual modalı səhifəni yenidən yükləmir; «Bütün N sualı seç» (select_scope=all_matching) və
   «Bütün sualları deaktiv et / aktiv et» əlavə olundu.

   AJAX-safe: EMSReady + kök bayrağı (`data-qb-bound`) — document/window-a
   dinləyici yığılmır. Qarmaqlar: partials/_question_management.html,
   qm/_card.html, qm/_danger.html.
   ========================================================================= */
(function () {
  "use strict";

  var SCROLL_FLAG = "qb_scroll_to_top";
  var INTERACTIVE_SELECTOR = "a,button,input,textarea,select,details,summary,label";

  function t(key, fallback) {
    var i18n = window.TEACHER_QUESTIONS_BANK_I18N || {};
    return i18n[key] || gettext(fallback);
  }

  function fill(template, values) {
    return String(template || "").replace(/\{(\w+)\}/g, function (match, name) {
      return Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : match;
    });
  }

  /* Yazılı təsdiq: boşluqlar və i/İ/I/ı fərqi nəzərə alınmır (məqsəd — düşünülmüş əməl). */
  function normalizePhrase(value) {
    return String(value || "")
      .replace(/[İIı]/g, "i")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function phraseMatches(typed, phrase) {
    var expected = normalizePhrase(phrase);
    return expected !== "" && normalizePhrase(typed) === expected;
  }

  function focusBack(node) {
    if (node && document.contains(node) && typeof node.focus === "function") node.focus();
  }

  function modalApi(element) {
    if (!element || !window.bootstrap || !window.bootstrap.Modal) return null;
    return window.bootstrap.Modal.getOrCreateInstance(element);
  }

  /* EMSConfirm → təsdiqdə `onConfirm`, ləğvdə fokus düyməyə qayıdır. */
  function confirmThen(opts, onConfirm, trigger) {
    var api = window.EMSConfirm;
    // EMSConfirm base.html-də qlobal yüklənir; yoxdursa əməl təsdiqsiz İCRA OLUNMUR
    // (native confirm() qadağandır — FE-F19).
    if (!api || typeof api.open !== "function") return;
    api.open({
      title: opts.title || "",
      body: opts.body || "",
      confirmLabel: opts.confirmLabel || "",
      danger: !!opts.danger,
    }).then(function (ok) {
      if (ok) onConfirm();
      else focusBack(trigger);
    });
  }

  /* QB 2026-09-30: imtahan səhifəsində əməllər AJAX ilə gedir (guarded_submit.js);
     köməkçi yoxdursa (kitabxana bankı) false → adi form göndərişi.
     2026-11-11: «aktiv et» də eyni yoldadır — səhifə yenidən yüklənmir (live.js). */
  function guardedSubmit(form, fields) {
    var guard = window.QBGuardedSubmit;
    if (!form || !guard || !guard.enabled()) return false;
    guard.submit(form, fields || {});
    return true;
  }

  function submitWith(form, fields) {
    if (!form) return;
    if (guardedSubmit(form, fields)) return;
    Object.keys(fields || {}).forEach(function (name) {
      var hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = name;
      hidden.value = fields[name];
      form.appendChild(hidden);
    });
    form.submit();
  }

  function liveApi() {
    var api = window.QBLive;
    return api && typeof api.enabled === "function" && api.enabled() ? api : null;
  }

  function closest(target, selector) {
    return target && typeof target.closest === "function" ? target.closest(selector) : null;
  }

  /* ── Axtarış + süzgəclər (dərhal tətbiq) + səhifələmə ─────────────────── */
  function bindFilters(root) {
    var form = document.getElementById("questionSearchForm");
    var input = document.getElementById("questionSearchInput");
    if (!form) return;

    function normalizeInput() {
      if (!input) return;
      var max = parseInt(input.getAttribute("data-max-length") || input.getAttribute("maxlength"), 10);
      var value = (input.value || "").trim();
      if (Number.isFinite(max) && max > 0 && value.length > max) value = value.slice(0, max);
      input.value = value;
    }

    /* 2026-11-11: süzgəc dəyişəndə yalnız canlı bölgələr yenilənir (fokus axtarış sahəsində qalır). */
    function applyLive() {
      var api = liveApi();
      if (!api) return false;
      normalizeInput();
      api.refresh(api.urlFromFilterForm(form), { push: true });
      return true;
    }

    function submitSearch() {
      normalizeInput();
      if (applyLive()) return;
      if (typeof form.requestSubmit === "function") form.requestSubmit();
      else form.submit();
    }

    form.addEventListener("submit", function (event) {
      normalizeInput();
      if (applyLive()) event.preventDefault();
    });
    form.addEventListener("change", function (event) {
      if (event.target && event.target.tagName === "SELECT") submitSearch();
    });
    if (input && window.EMSSearchInput) {
      // 2026-10-14: vahid EMSSearchInput (1500 ms, ≥ 2 simvol, Enter dərhal, IME);
      // yeni səhifədə fokus + kursor axtarış sahəsinə qayıdır.
      window.EMSSearchInput.bind(input, {
        onSearch: function () {
          normalizeInput();
          if (applyLive()) return;
          window.EMSSearchInput.submitForm(form, { input: input });
        }
      });
    }

    // Tam səhifə keçidi (canlı rejim yoxdursa): yeni səhifə yuxarıdan açılsın.
    root.addEventListener("click", function (event) {
      if (liveApi() || !closest(event.target, ".pagination-wrapper .page-link[href]")) return;
      try { window.sessionStorage.setItem(SCROLL_FLAG, "1"); } catch (e) { /* storage bağlıdır */ }
    });
    try {
      if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
      if (window.sessionStorage.getItem(SCROLL_FLAG) === "1") {
        window.sessionStorage.removeItem(SCROLL_FLAG);
        window.requestAnimationFrame(function () { window.scrollTo({ top: 0, behavior: "smooth" }); });
      }
    } catch (e) { /* storage bağlıdır */ }
  }

  /* ── Seçim + toplu əməllər ──────────────────────────────────────────────
     Delegasiya ilə (kökə bir dinləyici) — siyahı canlı yenilənəndə yenidən bağlamaq lazım deyil;
     DOM hər dəfə oxunur. 2026-11-11: «Bütün N sualı seç» — `select_scope=all_matching` gizli sahəsi;
     ID göndərilmir, server cari süzgəci özü tətbiq edir. */
  function bindSelection(root) {
    function boxes() {
      return Array.prototype.slice.call(root.querySelectorAll(".question-checkbox"));
    }

    function scopeInput() { return document.getElementById("qbSelectScope"); }

    function allMatching() {
      var field = scopeInput();
      return !!field && field.value === "all_matching";
    }

    function matchingTotal() {
      var button = document.getElementById("selectAllMatchingBtn");
      var total = parseInt(button ? button.getAttribute("data-total") : "", 10);
      return Number.isFinite(total) ? total : 0;
    }

    function selectedCount() {
      if (allMatching()) return matchingTotal();
      return boxes().filter(function (box) { return box.checked; }).length;
    }

    function setScope(all) {
      var field = scopeInput();
      var button = document.getElementById("selectAllMatchingBtn");
      if (field) field.value = all ? "all_matching" : "";
      if (button) button.setAttribute("aria-pressed", all ? "true" : "false");
    }

    function refresh() {
      var count = selectedCount();
      var countLabel = document.getElementById("selectedCountLabel");
      boxes().forEach(function (box) {
        var card = box.closest(".qb-card");
        if (card) card.classList.toggle("is-selected", box.checked);
      });
      if (countLabel) {
        countLabel.classList.toggle("is-all-matching", allMatching());
        if (allMatching()) {
          countLabel.textContent = fill(t("selectedAllMatching", "Süzgəcə uyğun bütün {count} sual seçilib"), { count: count });
        } else {
          countLabel.textContent = count === 0
            ? t("selectedCountZero", "0 seçilib")
            : fill(t("selectedCount", "{count} seçilib"), { count: count });
        }
      }
      Array.prototype.forEach.call(root.querySelectorAll(".js-bulk-action-btn"), function (button) {
        button.disabled = count === 0;
        button.setAttribute("aria-disabled", count === 0 ? "true" : "false");
      });
    }

    function setAll(value, all) {
      setScope(!!all);
      boxes().forEach(function (box) { box.checked = value; });
      refresh();
    }

    root.addEventListener("change", function (event) {
      if (!closest(event.target, ".question-checkbox")) return;
      setScope(false); // əl ilə dəyişiklik «hamısı» rejimindən çıxarır — yalnız işarəlilər qalır
      refresh();
    });

    root.addEventListener("click", function (event) {
      if (closest(event.target, "#selectAllMatchingBtn")) { setAll(true, true); return; }
      if (closest(event.target, "#selectAllPageBtn")) { setAll(true, false); return; }
      if (closest(event.target, "#clearSelectionBtn")) { setAll(false, false); return; }
      // Kartın boş yerinə klik onu seçir (düymə/keçid/sahə klikləri istisna).
      var card = closest(event.target, ".qb-card");
      if (!card || closest(event.target, INTERACTIVE_SELECTOR)) return;
      var box = card.querySelector(".question-checkbox");
      if (!box) return;
      box.checked = !box.checked;
      setScope(false);
      refresh();
    });

    root.addEventListener("submit", function (event) {
      var bulkForm = closest(event.target, "#bulkForm");
      if (!bulkForm) return;
      var submitter = event.submitter;
      if (!submitter || submitter.name !== "bulk_action") return;
      event.preventDefault();
      var count = selectedCount();
      if (count === 0) {
        if (window.EMSToast) window.EMSToast.show(t("selectAtLeastOne", "Ən azı bir sual seçin."), "warning");
        return;
      }
      var action = submitter.value;
      var cfg = {
        delete: { title: t("confirmDeleteTitle", "Silməyi təsdiqlə"), body: t("bulkDeleteBody", "Seçilmiş {count} sual həmişəlik silinəcək. Davam edək?"), confirmLabel: t("okDelete", "Bəli, sil"), danger: true },
        deactivate: { title: t("confirmDeactivateTitle", "Deaktiv etməyi təsdiqlə"), body: t("bulkDeactivateBody", "Seçilmiş {count} sual deaktiv ediləcək. Davam edək?"), confirmLabel: t("okDeactivate", "Bəli, deaktiv et"), danger: true },
        activate: { title: t("confirmActivateTitle", "Aktiv etməyi təsdiqlə"), body: t("bulkActivateBody", "Seçilmiş {count} sual aktiv ediləcək. Davam edək?"), confirmLabel: t("okActivate", "Bəli, aktiv et"), danger: false },
      }[action];
      if (!cfg) return;
      cfg.body = fill(cfg.body, { count: count });
      if (allMatching()) cfg.body += " " + t("allMatchingNote", "Seçim bütün səhifələri əhatə edir.");
      confirmThen(cfg, function () {
        submitWith(bulkForm, { bulk_action: action });
      }, submitter);
    });

    // Canlı yeniləmədən sonra siyahı təzədir — seçim sıfırdan.
    root.addEventListener("qb:live:updated", refresh);
    refresh();
  }

  /* ── Tək sual: aktiv/deaktiv/sil; dil üzrə sil; bütün suallar üzrə aktiv/deaktiv ── */
  function bindRowActions(root) {
    function onDelete(button) {
      var deleteForm = document.getElementById("singleDeleteForm");
      var deleteId = document.getElementById("singleDeleteQuestionId");
      var qid = button.getAttribute("data-question-id");
      if (!deleteForm || !deleteId || !qid) return;
      confirmThen({
        title: t("confirmDeleteTitle", "Silməyi təsdiqlə"),
        body: fill(t("deleteQuestionBody", "Bu sual silinəcək: {question}"), { question: button.getAttribute("data-question-text") || "" }),
        confirmLabel: t("okDelete", "Bəli, sil"),
        danger: true,
      }, function () {
        deleteId.value = qid;
        submitWith(deleteForm, null);
      }, button);
    }

    function onSingle(button) {
      var actionForm = document.getElementById("singleQuestionActionForm");
      var actionValue = document.getElementById("singleQuestionActionValue");
      var actionId = document.getElementById("singleQuestionActionQuestionId");
      var action = button.getAttribute("data-action-value") || "";
      var qid = button.getAttribute("data-question-id") || "";
      if (!actionForm || !actionValue || !actionId || !qid) return;
      var activate = action === "activate";
      confirmThen({
        title: activate ? t("confirmActivateTitle", "Aktiv etməyi təsdiqlə") : t("confirmDeactivateTitle", "Deaktiv etməyi təsdiqlə"),
        body: activate ? t("singleActivateBody", "Bu sual aktiv ediləcək. Davam edək?") : t("singleDeactivateBody", "Bu sual deaktiv ediləcək. Davam edək?"),
        confirmLabel: activate ? t("okActivate", "Bəli, aktiv et") : t("okDeactivate", "Bəli, deaktiv et"),
        danger: !activate,
      }, function () {
        actionValue.value = action;
        actionId.value = qid;
        submitWith(actionForm, null);
      }, button);
    }

    function onLanguage(button) {
      var langForm = document.getElementById("questionLangDeleteForm");
      var langValue = document.getElementById("questionLangDeleteValue");
      var lang = button.getAttribute("data-language") || "";
      if (!langForm || !langValue || !lang) return;
      confirmThen({
        title: t("languageDeleteTitle", "Dil üzrə sil"),
        body: fill(t("languageDeleteBody", "Seçilmiş dildəki {count} sual həmişəlik silinəcək. Davam edək?"), { count: button.getAttribute("data-count") || "0" }),
        confirmLabel: t("okDelete", "Bəli, sil"),
        danger: true,
      }, function () {
        langValue.value = lang;
        submitWith(langForm, null);
      }, button);
    }

    /* Sahib 2026-11-11: «Bütün sualları deaktiv et / aktiv et» — silmədən, təsdiqlə. */
    function onBulkAll(button) {
      var form = document.getElementById("questionBankBulkAllForm");
      var value = document.getElementById("questionBankBulkAllValue");
      var action = button.getAttribute("data-bulk-all") || "";
      if (!form || !value || (action !== "deactivate_all" && action !== "activate_all")) return;
      var activate = action === "activate_all";
      var count = button.getAttribute("data-count") || "0";
      confirmThen({
        title: activate ? t("activateAllTitle", "Bütün sualları aktiv et") : t("deactivateAllTitle", "Bütün sualları deaktiv et"),
        body: fill(activate
          ? t("activateAllBody", "İmtahanın bütün {count} sualı aktiv ediləcək. Davam edək?")
          : t("deactivateAllBody", "İmtahanın bütün {count} sualı deaktiv ediləcək (silinmir — cavablar və nəticələr qalır). Davam edək?"), { count: count }),
        confirmLabel: activate ? t("okActivate", "Bəli, aktiv et") : t("okDeactivate", "Bəli, deaktiv et"),
        danger: !activate,
      }, function () {
        value.value = action;
        submitWith(form, null);
      }, button);
    }

    root.addEventListener("click", function (event) {
      var button = closest(event.target, ".js-open-delete-modal");
      if (button) { onDelete(button); return; }
      button = closest(event.target, ".js-single-question-action");
      if (button) { onSingle(button); return; }
      button = closest(event.target, ".js-delete-language");
      if (button) { onLanguage(button); return; }
      button = closest(event.target, ".js-bulk-all");
      if (button) onBulkAll(button);
    });
  }

  /* ── «Bütün sual bankını sil» — yazılı təsdiq ─────────────────────────── */
  function bindDeleteAll(root) {
    var modal = document.getElementById("qbTypedConfirmModal");
    var typedForm = modal && modal.querySelector("[data-qb-typed-form]");
    var input = modal && modal.querySelector("[data-qb-typed-input]");
    var okBtn = modal && modal.querySelector("[data-qb-typed-ok]");
    var body = modal && modal.querySelector("[data-qb-typed-body]");
    var trigger = null;
    var confirmed = false;

    // Forma canlı bölgədədir (süzgəc sahələri ilə) — hər dəfə DOM-dan oxunur.
    function form() { return document.getElementById("questionBankDeleteAllForm"); }

    function phrase() {
      return typedForm ? typedForm.getAttribute("data-phrase") || "" : "";
    }

    function sync() {
      var ok = !!input && phraseMatches(input.value, phrase());
      if (okBtn) okBtn.disabled = !ok;
      if (input) input.setAttribute("aria-invalid", input.value && !ok ? "true" : "false");
      return ok;
    }

    if (typedForm && input && okBtn) {
      input.addEventListener("input", sync);
      typedForm.addEventListener("submit", function (event) {
        event.preventDefault();
        if (!sync() || !form()) return;
        confirmed = true;
        var api = modalApi(modal);
        if (api) api.hide();
        submitWith(form(), null);
      });
      modal.addEventListener("shown.bs.modal", function () { input.focus(); });
      modal.addEventListener("hidden.bs.modal", function () {
        if (!confirmed) focusBack(trigger);
        trigger = null;
      });
    }

    root.addEventListener("click", function (event) {
      var button = closest(event.target, ".js-delete-all-questions");
      if (!button || !form()) return;
      var count = button.getAttribute("data-count") || "0";
      var api = modalApi(modal);
      if (!api || !typedForm || !input || !okBtn) {
        // Bootstrap/dialoq yoxdursa — adi təhlükə təsdiqi (heç vaxt sınmır).
        confirmThen({
          title: t("deleteAllTitle", "Sual bankını sil"),
          body: fill(t("deleteAllBody", "Bütün sual bankı və içindəki {count} sual həmişəlik silinəcək. Davam edək?"), { count: count }),
          confirmLabel: t("okDelete", "Bəli, sil"),
          danger: true,
        }, function () { submitWith(form(), null); }, button);
        return;
      }
      trigger = button;
      confirmed = false;
      if (body) body.textContent = fill(body.getAttribute("data-template"), { count: count });
      input.value = "";
      sync();
      api.show();
    });
  }

  /* ── Sual modalı (yarat/redaktə) — mövcud axın ────────────────────────── */
  function bindQuestionModal(root) {
    var element = document.getElementById("questionFormModal");
    var body = document.getElementById("questionFormModalBody");
    var title = document.getElementById("questionFormModalTitle");
    var modal = modalApi(element);
    var trigger = null;
    var inFlight = false;
    if (!element || !body || !modal) return;

    function loadingMarkup() {
      return '<div class="create-exam-modal-loading skeleton" aria-busy="true" role="status">' +
        '<span class="visually-hidden">' + t("loadingForm", "Yüklənir...") + "</span>" +
        '<div class="skeleton-line skeleton-line--lg"></div><div class="skeleton-line"></div><div class="skeleton-line"></div>' +
        '<div class="skeleton-line skeleton-line--sm"></div><div class="skeleton-line skeleton-line--lg"></div><div class="skeleton-line"></div>' +
        "</div>";
    }

    function errorMarkup() {
      var box = document.createElement("div");
      box.className = "create-exam-modal-error";
      box.textContent = t("submitError", "Yenidən cəhd edin.");
      return box.outerHTML;
    }

    function modalUrl(rawUrl) {
      try {
        var parsed = new URL(rawUrl, window.location.origin);
        parsed.searchParams.set("modal", "1");
        return parsed.pathname + parsed.search;
      } catch (error) {
        return rawUrl + (rawUrl.indexOf("?") === -1 ? "?modal=1" : "&modal=1");
      }
    }

    function bindForm() {
      var formRoot = body.querySelector(".js-exam-question-form-root");
      if (window.ExamQuestionForm && formRoot) window.ExamQuestionForm.init(formRoot);
      var closeBtn = body.querySelector(".js-close-question-form-modal");
      if (closeBtn) closeBtn.addEventListener("click", function () { modal.hide(); });
      var form = body.querySelector("form");
      if (!form) return;
      form.addEventListener("submit", async function (event) {
        event.preventDefault();
        if (inFlight) return;
        inFlight = true;
        var submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) submitButton.disabled = true;
        try {
          var live = liveApi();
          var headers = { "X-Requested-With": "XMLHttpRequest" };
          if (live) headers[live.PARTIAL_HEADER || "X-QB-Partial"] = "1";
          var response = await fetch(form.getAttribute("action"), {
            method: "POST", body: new FormData(form), headers: headers,
          });
          var contentType = response.headers.get("content-type") || "";
          if (contentType.indexOf("application/json") !== -1) {
            var payload = await response.json();
            if (response.ok && payload.success) {
              modal.hide();
              // 2026-11-11: səhifə yenidən yüklənmir — yalnız siyahı yenilənir; «yeni versiya» qeydi toast.
              if (live) {
                if (payload.message) live.showMessages([{ level: "success", text: payload.message }]);
                live.refresh(window.location.href, { keepUrl: true });
                return;
              }
              window.location.reload();
              return;
            }
            if (payload.html) { body.innerHTML = payload.html; bindForm(); return; }
          }
          var html = await response.text();
          body.innerHTML = html || errorMarkup();
          bindForm();
        } catch (error) {
          body.innerHTML = errorMarkup();
        } finally {
          inFlight = false;
          if (submitButton) submitButton.disabled = false;
        }
      });
    }

    async function open(rawUrl, mode) {
      var isEdit = mode === "edit";
      if (title) title.textContent = isEdit ? t("questionEditTitle", "Sualı redaktə et") : t("questionCreateTitle", "Sual əlavə et");
      element.classList.toggle("is-edit", isEdit);
      trigger = document.activeElement;
      body.innerHTML = loadingMarkup();
      modal.show();
      try {
        var response = await fetch(modalUrl(rawUrl), { headers: { "X-Requested-With": "XMLHttpRequest" } });
        if (!response.ok) throw new Error("request_failed");
        body.innerHTML = await response.text();
        bindForm();
      } catch (error) {
        body.innerHTML = errorMarkup();
      }
    }

    root.addEventListener("click", function (event) {
      var link = closest(event.target, ".js-open-question-form-modal");
      if (!link) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      var url = link.getAttribute("data-question-modal-url") || link.getAttribute("href");
      if (!url) return;
      event.preventDefault();
      open(url, link.getAttribute("data-question-modal-mode") || "edit");
    });

    element.addEventListener("hidden.bs.modal", function () {
      inFlight = false;
      body.innerHTML = loadingMarkup();
      focusBack(trigger); // a11y: fokus modalı açan düyməyə qayıdır
      trigger = null;
    });
  }

  function init() {
    var root = document.querySelector("[data-qm-context]");
    if (!root || root.getAttribute("data-qb-bound") === "1") return;
    root.setAttribute("data-qb-bound", "1");
    bindFilters(root);
    bindSelection(root);
    bindRowActions(root);
    bindDeleteAll(root);
    bindQuestionModal(root);
  }

  // jsdom testləri üçün saf funksiyalar (tests/js/teacher_questions_bank.test.js).
  window.QBTypedConfirm = { normalize: normalizePhrase, matches: phraseMatches };

  if (typeof window.EMSReady === "function") window.EMSReady(init);
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
