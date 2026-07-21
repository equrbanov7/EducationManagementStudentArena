/* Admin jurnal-düzəlişi: xana kliki → modal (davamiyyət/bal + səbəb + qeyd + PDF),
   düzəlişli xana → tarixçə modalı. AJAX multipart göndərmə + inline xəta. */
(function () {
  "use strict";
  var root = document.querySelector("[data-correction-root]");
  if (!root) return;

  var modal = root.querySelector("[data-corr-modal]");
  var histModal = root.querySelector("[data-corr-history-modal]");
  var form = root.querySelector("[data-corr-form]");
  var errBox = root.querySelector("[data-corr-error]");
  var fieldSel = form.querySelector("[data-corr-field]");
  var attWrap = form.querySelector("[data-corr-att-wrap]");
  var scoreWrap = form.querySelector("[data-corr-score-wrap]");
  var scoreOpt = form.querySelector("[data-corr-score-opt]");

  var histData = {};
  try {
    var raw = document.getElementById("corrHistoryData");
    if (raw) histData = JSON.parse(raw.textContent || "{}");
  } catch (e) { histData = {}; }

  function open(el) { el.hidden = false; document.body.style.overflow = "hidden"; }
  function close(el) { el.hidden = true; document.body.style.overflow = ""; }

  function syncFieldMode() {
    var isScore = fieldSel.value === "score";
    scoreWrap.hidden = !isScore;
    attWrap.hidden = isScore;
    scoreWrap.querySelector("input").required = isScore;
    attWrap.querySelector("select").required = !isScore;
  }
  fieldSel.addEventListener("change", syncFieldMode);

  root.addEventListener("click", function (ev) {
    var closer = ev.target.closest("[data-corr-close]");
    if (closer) { close(modal); close(histModal); return; }

    var badge = ev.target.closest(".corr-fixed-badge");
    var cell = ev.target.closest("[data-corr-cell]");
    if (!cell) return;

    // Düzəlişli xanada ✎ → tarixçə; başqa yerdə → düzəliş modalı.
    if (badge && cell.dataset.history && histData[cell.dataset.history]) {
      renderHistory(histData[cell.dataset.history], cell.dataset.history);
      open(histModal);
      return;
    }

    // Düzəliş modalını doldur.
    errBox.hidden = true; errBox.textContent = "";
    form.reset();
    form.querySelector("[data-corr-mark-id]").value = cell.dataset.markId;
    form.querySelector("[data-corr-student]").textContent = cell.dataset.student || "";
    form.querySelector("[data-corr-date]").textContent = cell.dataset.date || "";
    form.querySelector("[data-corr-kind]").textContent = cell.dataset.kind || "";
    // Bal yalnız seminar/lab xanasında seçilə bilər.
    var allowsScore = cell.dataset.allowsScore === "1";
    scoreOpt.disabled = !allowsScore;
    // Seminar/lab (bal olan) xana → default "Bal" düzəlişi (normal jurnal kimi);
    // mühazirə (yalnız davamiyyət) → "Davamiyyət".
    fieldSel.value = allowsScore ? "score" : "attendance";
    if (cell.dataset.status) attWrap.querySelector("select").value = cell.dataset.status;
    if (cell.dataset.score) scoreWrap.querySelector("input").value = cell.dataset.score;
    // Bootstrap-select toggle-ları proqramla dəyişən value/disabled-i əks etdirsin
    // (native select .value ilə "change" event atılmır).
    if (window.EMSBootstrapSelect) {
      window.EMSBootstrapSelect.refresh(fieldSel);
      window.EMSBootstrapSelect.sync(attWrap.querySelector("select"));
      window.EMSBootstrapSelect.sync(form.querySelector("[name='reason']"));
    }
    syncFieldMode();
    open(modal);
  });

  function renderHistory(entries, markId) {
    var body = root.querySelector("[data-corr-history-body]");
    body.innerHTML = "";
    var list = entries || [];
    list.forEach(function (c, idx) {
      var item = document.createElement("div");
      item.className = "corr-hist-item";
      var doc = c.document_url
        ? '<a class="corr-hist-doc" href="' + c.document_url + '" target="_blank" rel="noopener">PDF</a>'
        : "";
      // Yalnız ƏN SON düzəliş geri alına bilər (zəncir pozulmasın) — sonuncu element.
      var delBtn =
        idx === list.length - 1 && markId
          ? '<button type="button" class="corr-hist-del" data-corr-del="' + esc(markId) + '">' +
            "Düzəlişi sil" +
            "</button>"
          : "";
      item.innerHTML =
        '<div class="corr-hist-top"><span class="corr-hist-date">' + esc(c.date) + "</span>" + doc + "</div>" +
        '<div class="corr-hist-change"><b>' + esc(c.field_display) + ":</b> " + esc(String(c.old)) +
        ' <span class="corr-hist-arrow">→</span> <b>' + esc(String(c.new)) + "</b></div>" +
        '<div class="corr-hist-reason">' + esc(c.reason) + "</div>" +
        '<div class="corr-hist-note">' + esc(c.note) + "</div>" +
        '<div class="corr-hist-by">' + esc(c.by) + "</div>" +
        delBtn;
      body.appendChild(item);
    });
  }

  // "Düzəlişi sil" → son düzəlişi geri al (dəyər köhnəyə qayıdır, sarı itir).
  root.addEventListener("click", function (ev) {
    var del = ev.target.closest("[data-corr-del]");
    if (!del || !root.dataset.deleteUrl) return;
    if (!window.confirm("Bu düzəlişi geri almaq istəyirsiniz? Xana əvvəlki dəyərinə qayıdacaq.")) return;
    del.disabled = true;
    var fd = new FormData();
    fd.append("type", "grade");
    fd.append("mark_id", del.getAttribute("data-corr-del"));
    var token = form.querySelector("[name=csrfmiddlewaretoken]");
    if (token) fd.append("csrfmiddlewaretoken", token.value);
    fetch(root.dataset.deleteUrl, {
      method: "POST",
      body: fd,
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin",
    })
      .then(function (r) { return r.json(); })
      .then(function (j) { if (j.ok) { window.location.reload(); } else { del.disabled = false; } })
      .catch(function () { del.disabled = false; });
  });

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : s;
    return d.innerHTML;
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var submitBtn = form.querySelector("[data-corr-submit]");
    submitBtn.disabled = true;
    errBox.hidden = true;
    var fd = new FormData(form);
    fetch(root.dataset.applyUrl, {
      method: "POST",
      body: fd,
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin",
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (res.ok && res.j.ok) {
          window.location.reload();
        } else {
          errBox.textContent = (res.j && res.j.error) || "Xəta baş verdi.";
          errBox.hidden = false;
          submitBtn.disabled = false;
        }
      })
      .catch(function () {
        errBox.textContent = "Şəbəkə xətası.";
        errBox.hidden = false;
        submitBtn.disabled = false;
      });
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") { close(modal); close(histModal); }
  });
})();
