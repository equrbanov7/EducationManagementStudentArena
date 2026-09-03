/* Read-only düzəliş tarixçəsi — müəllim & tələbə jurnalları.
   Sarı xanadakı ✎ nişanına (data-corr-history="<mark_id>") klik → modal. */
(function () {
  "use strict";

  // json_script-i HƏR dəfə təzə oxu — profil SPA bölməsi AJAX ilə yenilənəndə
  // köhnə data qalmasın (section reload tələsi). data-corr-type ilə düzgün map:
  // bal (grade), sərbəst iş (selfwork), kurs işi (coursework), kollokvium (component).
  var RO_MAPS = {
    grade: "corrHistoryDataRO",
    selfwork: "corrSwHistoryDataRO",
    coursework: "corrCwHistoryDataRO",
    component: "corrCmHistoryDataRO",
  };
  function readData(type) {
    try {
      var raw = document.getElementById(RO_MAPS[type] || RO_MAPS.grade);
      return raw ? JSON.parse(raw.textContent || "{}") : {};
    } catch (e) { return {}; }
  }
  function currentModal() { return document.querySelector("[data-corr-history-modal]"); }

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : s;
    return d.innerHTML;
  }

  function render(entries) {
    var modal = currentModal();
    if (!modal) return;
    var body = modal.querySelector("[data-corr-history-body]");
    body.innerHTML = "";
    (entries || []).forEach(function (c) {
      var item = document.createElement("div");
      // Köhnə sistemdən köçürülmüş üzrlü-qayıb sənədi DƏYİŞİKLİK deyil, SÜBUTdur:
      // "köhnə → yeni" sətri yoxdur, əvəzində tarix aralığı + sənəd adı göstərilir.
      // Fayl hələ köçürülməyibsə link VERİLMİR — sınıq keçid yalan olardı.
      if (c.kind === "legacy_excuse") {
        item.className = "corr-hist-item corr-hist-item--excuse";
        item.innerHTML =
          '<div class="corr-hist-top"><span class="corr-hist-date">' + esc(c.date) + "</span></div>" +
          '<div class="corr-hist-change"><b>' + esc(c.field_display) + ":</b> " + esc(c.period) + "</div>" +
          '<div class="corr-hist-reason">' + esc(c.reason) + "</div>" +
          '<div class="corr-hist-note">' + esc(c.note) + "</div>" +
          '<div class="corr-hist-doc">' +
          (c.document_available && c.document_url
            ? '<a href="' + esc(c.document_url) + '" target="_blank" rel="noopener">' + esc(c.document) + "</a>"
            : "<span>" + esc(c.document) + "</span> <i>" + esc(c.document_note) + "</i>") +
          "</div>" +
          '<div class="corr-hist-by">' + esc(c.by) + "</div>";
        body.appendChild(item);
        return;
      }
      item.className = "corr-hist-item";
      item.innerHTML =
        '<div class="corr-hist-top"><span class="corr-hist-date">' + esc(c.date) + "</span></div>" +
        '<div class="corr-hist-change"><b>' + esc(c.field_display) + ":</b> " + esc(String(c.old)) +
        ' <span class="corr-hist-arrow">→</span> <b>' + esc(String(c.new)) + "</b></div>" +
        '<div class="corr-hist-reason">' + esc(c.reason) + "</div>" +
        '<div class="corr-hist-note">' + esc(c.note) + "</div>" +
        '<div class="corr-hist-by">' + esc(c.by) + "</div>";
      body.appendChild(item);
    });
  }

  document.addEventListener("click", function (ev) {
    var modal = currentModal();
    if (ev.target.closest("[data-corr-close]")) {
      if (modal) modal.hidden = true;
      document.body.style.overflow = "";
      return;
    }
    var badge = ev.target.closest("[data-corr-history]");
    if (!badge || !modal) return;
    var data = readData(badge.getAttribute("data-corr-type") || "grade");
    var key = badge.getAttribute("data-corr-history");
    if (!data[key]) return;
    ev.preventDefault();
    render(data[key]);
    modal.hidden = false;
    document.body.style.overflow = "hidden";
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") {
      var modal = currentModal();
      if (modal) modal.hidden = true;
      document.body.style.overflow = "";
    }
  });
})();
