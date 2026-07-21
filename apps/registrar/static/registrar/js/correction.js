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

  function readJson(id) {
    try {
      var raw = document.getElementById(id);
      return raw ? JSON.parse(raw.textContent || "{}") : {};
    } catch (e) { return {}; }
  }
  var histData = readJson("corrHistoryData"); // grade (mark_id)
  var swHist = readJson("corrSwHistoryData"); // selfwork ("topic:enrollment")
  var cwHist = readJson("corrCwHistoryData"); // coursework (enrollment_id)
  var cmHist = readJson("corrCmHistoryData"); // component/kollokvium ("component:enrollment")

  // Hədəf-aware modal sahələri.
  var targetInput = form.querySelector("[data-corr-target]");
  var topicIdInput = form.querySelector("[data-corr-topic-id]");
  var componentIdInput = form.querySelector("[data-corr-component-id]");
  var enrIdInput = form.querySelector("[data-corr-enrollment-id]");
  var fieldWrap = form.querySelector("[data-corr-field-wrap]");
  var swWrap = form.querySelector("[data-corr-sw-wrap]");
  var cwWrap = form.querySelector("[data-corr-cw-wrap]");
  var cmWrap = form.querySelector("[data-corr-cm-wrap]");
  var histCtx = { type: "grade" }; // tarixçə modalında "Düzəlişi sil" üçün kontekst

  function open(el) { el.hidden = false; document.body.style.overflow = "hidden"; }
  function close(el) { el.hidden = true; document.body.style.overflow = ""; }

  function syncFieldMode() {
    var isScore = fieldSel.value === "score";
    scoreWrap.hidden = !isScore;
    attWrap.hidden = isScore;
    scoreWrap.querySelector("select").required = isScore;
    attWrap.querySelector("select").required = !isScore;
  }
  fieldSel.addEventListener("change", syncFieldMode);

  root.addEventListener("click", function (ev) {
    var closer = ev.target.closest("[data-corr-close]");
    if (closer) { close(modal); close(histModal); return; }

    var badge = ev.target.closest(".corr-fixed-badge");
    var cell = ev.target.closest("[data-corr-cell]");
    if (!cell) return;

    var target = cell.dataset.corrTarget || "grade";
    var histMap =
      target === "selfwork" ? swHist : target === "coursework" ? cwHist : target === "component" ? cmHist : histData;

    // Düzəlişli xanada ✎ → tarixçə; başqa yerdə → düzəliş modalı.
    if (badge && cell.dataset.history && histMap[cell.dataset.history]) {
      histCtx = {
        type: target,
        markId: cell.dataset.markId,
        topicId: cell.dataset.topicId,
        componentId: cell.dataset.componentId,
        enrollmentId: cell.dataset.enrollmentId,
      };
      renderHistory(histMap[cell.dataset.history]);
      open(histModal);
      return;
    }

    // Düzəliş modalını doldur (hədəf-aware).
    errBox.hidden = true; errBox.textContent = "";
    form.reset();
    targetInput.value = target === "grade" ? "" : target;
    if (topicIdInput) topicIdInput.value = cell.dataset.topicId || "";
    if (componentIdInput) componentIdInput.value = cell.dataset.componentId || "";
    if (enrIdInput) enrIdInput.value = cell.dataset.enrollmentId || "";
    form.querySelector("[data-corr-mark-id]").value = cell.dataset.markId || "";
    // Boş xana (mark yoxdur) → lesson_id ilə server mark yaradır.
    var lessonIdInput = form.querySelector("[data-corr-lesson-id]");
    if (lessonIdInput) lessonIdInput.value = cell.dataset.lessonId || "";
    form.querySelector("[data-corr-student]").textContent = cell.dataset.student || "";
    form.querySelector("[data-corr-date]").textContent = cell.dataset.date || "";
    form.querySelector("[data-corr-kind]").textContent = cell.dataset.kind || "";

    var isGrade = target === "grade";
    var isSw = target === "selfwork";
    var isCw = target === "coursework";
    var isCm = target === "component";
    if (fieldWrap) fieldWrap.hidden = !isGrade;
    attWrap.hidden = !isGrade;
    scoreWrap.hidden = true;
    if (swWrap) swWrap.hidden = !isSw;
    if (cwWrap) cwWrap.hidden = !isCw;
    if (cmWrap) cmWrap.hidden = !isCm;
    // Gizli grade sahələri HTML5 validasiyanı bloklamasın — required təmizlə.
    attWrap.querySelector("select").required = false;
    scoreWrap.querySelector("select").required = false;

    if (isGrade) {
      var allowsScore = cell.dataset.allowsScore === "1";
      scoreOpt.disabled = !allowsScore;
      fieldSel.value = allowsScore ? "score" : "attendance";
      if (cell.dataset.status) attWrap.querySelector("select").value = cell.dataset.status;
      // Bal: 0–10 seçim (seminar kimi) — cari bal seçili gəlir, boşdursa 0.
      var scoreSel = scoreWrap.querySelector("select");
      scoreSel.value = cell.dataset.score || "0";
      if (window.EMSBootstrapSelect) {
        window.EMSBootstrapSelect.refresh(fieldSel);
        window.EMSBootstrapSelect.sync(attWrap.querySelector("select"));
        window.EMSBootstrapSelect.sync(scoreSel);
      }
      syncFieldMode();
    } else if (isSw) {
      // Sərbəst iş: təhvili əks çevir (0↔1) — korrektor dəyişikliyi görsün.
      var swSel = swWrap.querySelector("select");
      swSel.value = cell.dataset.done === "1" ? "0" : "1";
      if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.sync(swSel);
    } else if (isCw) {
      cwWrap.querySelector("[data-corr-cw-score]").value = cell.dataset.cwScore || "";
      cwWrap.querySelector("[data-corr-cw-topic]").value = cell.dataset.cwTopic || "";
      cwWrap.querySelector("[data-corr-cw-date]").value = cell.dataset.cwDate || "";
    } else if (isCm) {
      cmWrap.querySelector("[data-corr-cm-score]").value = cell.dataset.cmScore || "";
    }
    if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.sync(form.querySelector("[name='reason']"));
    open(modal);
  });

  function renderHistory(entries) {
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
        idx === list.length - 1
          ? '<button type="button" class="corr-hist-del" data-corr-del>Düzəlişi sil</button>'
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
    fd.append("type", histCtx.type || "grade");
    if (histCtx.markId) fd.append("mark_id", histCtx.markId);
    if (histCtx.topicId) fd.append("topic_id", histCtx.topicId);
    if (histCtx.componentId) fd.append("component_id", histCtx.componentId);
    if (histCtx.enrollmentId) fd.append("enrollment_id", histCtx.enrollmentId);
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
