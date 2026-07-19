/* Müəllim jurnalı: redaktə vaxtı keçmiş sütun başlığındakı tarixə klik →
   oxu-rejimi GÜN ÖZƏTİ modalı (heç nə dəyişmir; edit deyil). */
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
    modal.hidden = false;
    document.body.style.overflow = "hidden";
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") close();
  });
})();
