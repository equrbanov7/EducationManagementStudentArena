/* Tələbə elektron jurnalı (FAZA B) — semestr seçici + dərs-tipi filtri + gün modalı.
   Profil SPA bölməsi AJAX ilə yeniləndiyi üçün hamısı delegated (document-səviyyə). */
(function () {
  "use strict";

  // ── Tədris ili + yarım il seçicisi → bölməni ?period=<id> ilə yenilə ──
  function gotoPeriod(periodId) {
    var term = document.querySelector("[data-sjx-term]") || document.querySelector(".sjx-term");
    var base = (term && term.getAttribute("data-base-url")) || "/accounts/profile/";
    var url = base + "?section=my-journal&period=" + encodeURIComponent(periodId);
    var a = document.createElement("a");
    a.href = url;
    a.className = "js-profile-section-link";
    a.setAttribute("data-section", "my-journal");
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { a.remove(); }, 0);
    if (!document.querySelector("[data-profile-sections-host]")) window.location.href = url;
  }

  document.addEventListener("change", function (ev) {
    // Tədris ili dəyişəndə: həmin ilin yarım-illərini göstər + ilkini seç.
    var yearSel = ev.target.closest("[data-sjx-year]");
    if (yearSel) {
      var year = yearSel.value;
      var periodSel = document.querySelector("[data-sjx-period]");
      if (!periodSel) return;
      var first = null;
      Array.prototype.forEach.call(periodSel.options, function (opt) {
        var match = opt.getAttribute("data-year") === year;
        opt.hidden = !match;
        if (match && first === null) first = opt.value;
      });
      // Styled dropdown (bootstrap-single-select) gizli option-lara görə yenilənsin.
      if (typeof periodSel._refreshBootstrapSelect === "function") periodSel._refreshBootstrapSelect();
      if (first) gotoPeriod(first);
      return;
    }
    // Yarım il dəyişəndə: birbaşa həmin dövrə keç.
    var periodSel2 = ev.target.closest("[data-sjx-period]");
    if (periodSel2) gotoPeriod(periodSel2.value);
  });

  // ── Dərs tipi filtri ──
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-sjx-filter] .sjx-filter-btn");
    if (!btn) return;
    var group = btn.closest("[data-sjx-filter]");
    group.querySelectorAll(".sjx-filter-btn").forEach(function (b) { b.classList.remove("is-active"); });
    btn.classList.add("is-active");
    var kind = btn.getAttribute("data-kind");
    document.querySelectorAll("tr.sjx-drow").forEach(function (row) {
      row.style.display = kind === "all" || row.getAttribute("data-kind") === kind ? "" : "none";
    });
  });

  // ── Gün detalı modalı ──
  function modal() { return document.querySelector("[data-sjx-daymodal]"); }
  function closeModal() {
    var m = modal();
    if (m) m.hidden = true;
    document.body.style.overflow = "";
  }

  document.addEventListener("click", function (ev) {
    if (ev.target.closest("[data-sjx-day-close]")) { closeModal(); return; }
    // Düzəliş ✎ nişanı gün modalını YOX, tarixçə modalını açır (correction_history.js).
    if (ev.target.closest("[data-corr-history]")) return;
    var row = ev.target.closest("[data-sjx-day]");
    var m = modal();
    if (!row || !m) return;
    function put(sel, val) {
      var el = m.querySelector(sel);
      if (el) el.textContent = val || "—";
    }
    m.querySelector("[data-sjx-day-date]").textContent = row.getAttribute("data-date") || "";
    put("[data-sjx-day-kind]", row.getAttribute("data-kind-label"));
    put("[data-sjx-day-teacher]", row.getAttribute("data-teacher"));
    put("[data-sjx-day-topic]", row.getAttribute("data-topic"));
    put("[data-sjx-day-room]", row.getAttribute("data-room"));
    put("[data-sjx-day-att]", row.getAttribute("data-att"));
    put("[data-sjx-day-score]", row.getAttribute("data-score"));
    var corr = m.querySelector("[data-sjx-day-corr]");
    if (corr) corr.hidden = row.getAttribute("data-corrected") !== "1";
    // Köhnə sistemdən köçürülmüş üzrlü-qayıb sənədi (sarı sətir, ✎ nişanı).
    var excuse = m.querySelector("[data-sjx-day-excuse]");
    if (excuse) excuse.hidden = row.getAttribute("data-legacy-excuse") !== "1";
    m.hidden = false;
    document.body.style.overflow = "hidden";
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") closeModal();
  });
})();
