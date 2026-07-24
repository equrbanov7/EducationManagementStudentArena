/*
 * kollokvium_windows.js
 * Source: extracted verbatim from the inline <script> in
 * _kollokvium_windows_content.html (CSP inline-removal, 2026-07).
 * Confirm modal + extra-days (grant) modal for kollokvium score windows.
 * Kept as a plain IIFE (matches the original): it runs once on initial load and
 * once per profile AJAX swap when the section loader re-executes the tag, so the
 * fresh panel elements are each bound exactly once. i18n strings are bridged via
 * data-* on #kwI18n; the faculties/departments JSON stays in json_script blocks.
 */
(function () {
  "use strict";

  var kwI18n = document.getElementById("kwI18n");
  function kwT(key) {
    return kwI18n ? (kwI18n.getAttribute(key) || "") : "";
  }

  // ── bootstrap-select (bu bölmə full-page render olunur; açıq re-init) ──
  try { if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.init(document); } catch (e) {}

  // Alət panelindəki seçimlər dəyişəndə avtomatik submit.
  document.querySelectorAll("[data-autosubmit]").forEach(function (sel) {
    sel.addEventListener("change", function () { if (sel.form) sel.form.submit(); });
  });

  function fmtDate(d) {
    var dd = String(d.getDate()).padStart(2, "0");
    var mm = String(d.getMonth() + 1).padStart(2, "0");
    return dd + "." + mm + "." + d.getFullYear();
  }
  function addDays(iso, days) {
    if (!iso) return null;
    var parts = iso.split("-");
    if (parts.length !== 3) return null;
    var d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    d.setDate(d.getDate() + (Number(days) || 0));
    return d;
  }

  // ── Ümumi təsdiq modalı ──
  var confirmModal = document.getElementById("kw-confirm-modal");
  var confirmTitle = document.getElementById("kw-confirm-title");
  var confirmBody = document.getElementById("kw-confirm-body");
  var confirmOk = document.getElementById("kw-confirm-ok");
  var pendingForm = null;

  function openModal(m) { if (m) { m.classList.add("is-open"); m.setAttribute("aria-hidden", "false"); } }
  function closeModal(m) { if (m) { m.classList.remove("is-open"); m.setAttribute("aria-hidden", "true"); } }
  function closeAll() { document.querySelectorAll(".kw-modal.is-open").forEach(closeModal); pendingForm = null; }

  document.querySelectorAll(".js-kw-close").forEach(function (el) {
    el.addEventListener("click", closeAll);
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeAll(); });

  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      pendingForm = form;
      confirmTitle.textContent = form.getAttribute("data-confirm-title") || kwT("data-confirm-fallback");
      var body = form.getAttribute("data-confirm-body") || "";
      if (form.getAttribute("data-confirm-kind") === "save") {
        var opens = form.querySelector("input[name=opens_on]");
        var closes = form.querySelector("input[name=closes_on]");
        var kl = form.getAttribute("data-confirm-klabel") || "";
        var od = opens && opens.value ? fmtDate(addDays(opens.value, 0)) : "—";
        var cd = closes && closes.value ? fmtDate(addDays(closes.value, 0)) : "—";
        body = kwT("data-confirm-dates") + "<br><br>" +
               "<b>" + kl + "</b>: " + od + " – " + cd +
               "<div class='kw-modal__note' style='margin-top:.7rem'><i class='fas fa-circle-info'></i> <span>" + kwT("data-save-note") + "</span></div>";
      }
      confirmBody.innerHTML = body;
      confirmOk.className = "kw-btn " + (form.getAttribute("data-confirm-variant") === "danger" ? "kw-btn--danger" : "kw-btn--primary");
      openModal(confirmModal);
    });
  });

  confirmOk.addEventListener("click", function () {
    if (pendingForm) {
      var f = pendingForm;
      pendingForm = null;
      closeAll();
      f.submit(); // native submit → data-confirm listener-i işə düşmür (loop yox)
    }
  });

  // ── Əlavə gün modalı ──
  var grantModal = document.getElementById("kw-grant-modal");
  if (grantModal) {
    var grantForm = document.getElementById("kw-grant-form");
    var grantTitle = document.getElementById("kw-grant-title");
    var grantWindowId = document.getElementById("kw-grant-window-id");
    var grantScope = document.getElementById("kw-grant-scope");
    var grantUnitWrap = document.getElementById("kw-grant-unit-wrap");
    var grantUnit = document.getElementById("kw-grant-unit");
    var grantUnitLabel = document.getElementById("kw-grant-unit-label");
    var grantDays = document.getElementById("kw-grant-days");
    var grantPreview = document.getElementById("kw-grant-preview");
    var grantAction = document.getElementById("kw-grant-action");
    var grantGrantId = document.getElementById("kw-grant-grant-id");
    var grantSubmit = document.getElementById("kw-grant-submit");
    var currentCloses = null;
    var ADD_TITLE = kwT("data-add-title");
    var EDIT_TITLE = kwT("data-edit-title");
    var ADD_SUBMIT = '<i class="fas fa-check"></i> ' + kwT("data-add-submit");
    var EDIT_SUBMIT = '<i class="fas fa-check"></i> ' + kwT("data-edit-submit");

    function readJson(id) {
      var node = document.getElementById(id);
      if (!node) return [];
      try { return JSON.parse(node.textContent) || []; } catch (e) { return []; }
    }
    var faculties = readJson("kw-faculties-data");
    var departments = readJson("kw-departments-data");

    function fillUnit(items) {
      grantUnit.innerHTML = "";
      var ph = document.createElement("option");
      ph.value = ""; ph.textContent = "—";
      grantUnit.appendChild(ph);
      items.forEach(function (it) {
        var o = document.createElement("option");
        o.value = it.id; o.textContent = it.name;
        grantUnit.appendChild(o);
      });
      grantUnit.value = "";
      try { if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.refresh(grantUnit); } catch (e) {}
    }

    function syncScope() {
      var v = grantScope.value;
      if (v === "organization") {
        grantUnitWrap.style.display = "none";
      } else {
        grantUnitWrap.style.display = "";
        if (v === "faculty") {
          grantUnitLabel.textContent = kwT("data-faculty");
          fillUnit(faculties);
        } else {
          grantUnitLabel.textContent = kwT("data-department");
          fillUnit(departments);
        }
      }
    }

    function daysValue() {
      // Tam ədədə çevir (1–30). parseInt "2.5"→2, "1.0"→1 — rəqəmləri
      // BİRLƏŞDİRMİR (əvvəlki replace(/[^0-9]/) "2.5"→25 səhvi düzəldilib).
      var n = parseInt(grantDays.value, 10);
      return Math.min(30, Math.max(1, isNaN(n) ? 1 : n));
    }
    function syncPreview() {
      var d = addDays(currentCloses, daysValue());
      grantPreview.textContent = d ? fmtDate(d) : "—";
    }

    grantScope.addEventListener("change", function () { syncScope(); });
    // Mənfi/onluq gün QADAĞANDIR: klaviatura + yapışdırma + blur — hər səviyyədə.
    grantDays.addEventListener("keydown", function (e) {
      if (["-", "+", "e", "E", ".", ","].indexOf(e.key) !== -1) e.preventDefault();
    });
    grantDays.addEventListener("input", function () {
      // Yapışdırma "2.5"/"-3" üçün: tam ədədə kəs (parseInt), rəqəmləri birləşdirmə.
      var n = parseInt(grantDays.value, 10);
      var clean = isNaN(n) ? "" : String(Math.abs(n)); // boş yazmağa icazə (yenidən yığmaq)
      if (clean !== grantDays.value) grantDays.value = clean;
      syncPreview();
    });
    grantDays.addEventListener("change", function () {
      grantDays.value = daysValue(); // blur-da 1–30 aralığına gətir
      syncPreview();
    });

    function openGrantModal(opts) {
      var isEdit = opts.mode === "edit";
      grantAction.value = isEdit ? "edit_extra_days" : "grant_extra_days";
      grantGrantId.value = opts.grantId || "";
      grantWindowId.value = opts.windowId || "";
      currentCloses = opts.closes || null;
      var kl = opts.kLabel || "";
      grantTitle.textContent = (isEdit ? EDIT_TITLE : ADD_TITLE) + (kl ? " — " + kl : "");
      grantSubmit.innerHTML = isEdit ? EDIT_SUBMIT : ADD_SUBMIT;
      // Əhatə seçimi + bölmə options-larını qur (scope-a görə).
      grantScope.value = opts.scope || "organization";
      try { if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.sync(grantScope); } catch (e) {}
      syncScope();
      // Redaktədə mövcud bölməni öncədən seç (fillUnit options-ları qurdu).
      if (isEdit && opts.scope && opts.scope !== "organization" && opts.orgUnitId) {
        // Bölmə deaktiv edilibsə aktiv siyahıda yoxdur — sintetik option əlavə et
        // ki, öncədən dolma boşalmasın (server də bu bölməni qəbul edir).
        if (!grantUnit.querySelector('option[value="' + opts.orgUnitId + '"]')) {
          var synth = document.createElement("option");
          synth.value = opts.orgUnitId;
          synth.textContent = opts.orgUnitName || opts.orgUnitId;
          grantUnit.appendChild(synth);
          try { if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.refresh(grantUnit); } catch (e) {}
        }
        grantUnit.value = opts.orgUnitId;
        try { if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.sync(grantUnit); } catch (e) {}
      }
      grantDays.value = opts.days != null && opts.days !== "" ? String(opts.days) : "2";
      syncPreview();
      openModal(grantModal);
    }

    document.querySelectorAll(".js-kw-grantopen").forEach(function (btn) {
      btn.addEventListener("click", function () {
        openGrantModal({
          mode: "add",
          windowId: btn.getAttribute("data-window-id"),
          closes: btn.getAttribute("data-closes"),
          kLabel: btn.getAttribute("data-k-label"),
        });
      });
    });

    document.querySelectorAll(".js-kw-grantedit").forEach(function (btn) {
      btn.addEventListener("click", function () {
        openGrantModal({
          mode: "edit",
          grantId: btn.getAttribute("data-grant-id"),
          windowId: btn.getAttribute("data-window-id"),
          closes: btn.getAttribute("data-closes"),
          kLabel: btn.getAttribute("data-k-label"),
          scope: btn.getAttribute("data-scope"),
          orgUnitId: btn.getAttribute("data-org-unit-id"),
          orgUnitName: btn.getAttribute("data-org-unit-name"),
          days: btn.getAttribute("data-extra-days"),
        });
      });
    });
  }
})();
