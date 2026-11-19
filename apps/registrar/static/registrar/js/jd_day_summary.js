/* Müəllim jurnalı: redaktə vaxtı keçmiş sütun başlığındakı tarixə klik →
   oxu-rejimi GÜN ÖZƏTİ modalı (heç nə dəyişmir; edit deyil). Əməkdaş (sahib 2026-11-17) hər sütunda açır
   və orada dərsin başladıldığı an + saat aralığı görünür. */
(function () {
  "use strict";
  var modal = document.querySelector("[data-jd-day-modal]");
  if (!modal) return;

  function set(sel, val) {
    var el = modal.querySelector(sel);
    if (el) el.textContent = val == null || val === "" ? "—" : val;
  }
  function close() { modal.hidden = true; document.body.style.overflow = ""; }

  document.addEventListener("click", function (ev) {
    if (ev.target.closest("[data-jd-day-close]")) { close(); return; }
    var btn = ev.target.closest("[data-jd-day-summary]");
    if (!btn) return;
    ev.preventDefault();
    modal.querySelector("[data-jd-day-title]").textContent = btn.getAttribute("data-date") || "";
    set("[data-jd-day-kind]", btn.getAttribute("data-kind"));
    set("[data-jd-day-topic]", btn.getAttribute("data-topic"));
    set("[data-jd-day-ie]", btn.getAttribute("data-ie"));
    set("[data-jd-day-qb]", btn.getAttribute("data-qb"));
    set("[data-jd-day-uq]", btn.getAttribute("data-uq"));
    set("[data-jd-day-scored]", btn.getAttribute("data-scored"));
    set("[data-jd-day-marked]", btn.getAttribute("data-marked"));
    set("[data-jd-day-total]", btn.getAttribute("data-total"));
    // Əməkdaş (sahib 2026-11-17): başladılma anı + cədvəl saatı — sahələr yalnız onun HTML-indədir.
    set("[data-jd-day-started]", btn.getAttribute("data-started"));
    set("[data-jd-day-time]", btn.getAttribute("data-time"));
    set("[data-jd-day-hours]", btn.getAttribute("data-hours"));
    // Otaq (sahib 2026-11-19): saatın yanında; otaq məlum deyilsə sətir gizli qalır («—» göstərilmir).
    var room = btn.getAttribute("data-room") || "";
    set("[data-jd-day-room]", room);
    var roomRow = modal.querySelector("[data-jd-day-room-row]");
    if (roomRow) roomRow.hidden = !room;
    // «Redaktə vaxtı keçib» qeydi yalnız kilidli sütunda (əməkdaş açıq dərsin də özətini açır).
    var note = modal.querySelector("[data-jd-day-note]");
    if (note) note.hidden = btn.getAttribute("data-locked") !== "1";
    // «Bu dərsin tarixçəsi» — tarixçə panelini bu dərs tarixi ilə süzülmüş açır (journal_history.js).
    var historyBtn = modal.querySelector("[data-jd-day-history]");
    if (historyBtn) historyBtn.setAttribute("data-jhist-date", btn.getAttribute("data-iso") || "");
    modal.hidden = false;
    document.body.style.overflow = "hidden";
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") close();
  });
})();
