/* Read-only düzəliş tarixçəsi — müəllim & tələbə jurnalları.
   Sarı xanadakı ✎ nişanına (data-corr-history="<mark_id>") klik → modal. */
(function () {
  "use strict";

  // json_script-i HƏR dəfə təzə oxu — profil SPA bölməsi AJAX ilə yenilənəndə
  // köhnə data qalmasın (section reload tələsi).
  function readData() {
    try {
      var raw = document.getElementById("corrHistoryDataRO");
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
    var data = readData();
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
