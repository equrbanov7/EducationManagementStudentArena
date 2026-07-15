(function (window, document) {
  "use strict";

  var ns = window.EMSExamLiveMonitor || (window.EMSExamLiveMonitor = {});
  var u = ns.utils;

  function studentByAttempt(ctx, id) {
    return ((ctx.state && ctx.state.students) || []).find(function (s) {
      return String(s.attempt_id) === String(id);
    });
  }

  function installTooltip(ctx) {
    ctx.tip = document.createElement("div");
    ctx.tip.className = "smap-tip";
    document.body.appendChild(ctx.tip);

    u.$("studentMap").addEventListener("mouseover", function (e) {
      var cell = e.target.closest(".smap-cell");
      if (!cell) {
        return;
      }
      var s = studentByAttempt(ctx, cell.getAttribute("data-attempt"));
      if (!s) {
        return;
      }
      ctx.tip.innerHTML = '<div class="tip-name">' + u.esc(s.name) + '</div>' +
        gettext('<div class="tip-row"><span>Cavablanıb</span><b>') + s.answered + " / " + s.total_questions + '</b></div>' +
        gettext('<div class="tip-row"><span>Qalıb</span><b>') + Math.max(0, s.total_questions - s.answered) + '</b></div>' +
        gettext('<div class="tip-row"><span>Tərəqqi</span><b>') + s.progress_pct + '%</b></div>' +
        '<div class="tip-row"><span>Pozuntu</span><b>' + s.violation_count + '</b></div>' +
        '<div class="tip-row"><span>Status</span><b>' + u.esc(ctx.STATUS_LABELS[s.supervision_status] || s.supervision_status) + '</b></div>' +
        (s.is_finished ? gettext('<div class="tip-row"><span>Nəticə</span><b>') + u.esc(u.scoreText(s)) + '</b></div>' : '') +
        gettext('<div class="tip-row"><span>Başlama</span><b>') + u.esc(u.fmtDateTime(s.started_at)) + '</b></div>';
      ctx.tip.classList.add("show");
    });
    u.$("studentMap").addEventListener("mousemove", function (e) {
      var x = e.clientX + 14;
      var y = e.clientY + 14;
      if (x + 250 > window.innerWidth) {
        x = e.clientX - 254;
      }
      ctx.tip.style.left = x + "px";
      ctx.tip.style.top = y + "px";
    });
    u.$("studentMap").addEventListener("mouseout", function () {
      ctx.tip.classList.remove("show");
    });
  }

  function fileIcon(name) {
    var ext = (name || "").split(".").pop().toLowerCase();
    if (ext === "html" || ext === "htm") return "fa-html5";
    if (ext === "css") return "fa-css3-alt";
    if (ext === "js") return "fa-js";
    if (ext === "py") return "fa-python";
    if (ext === "java") return "fa-java";
    return "fa-file-code";
  }

  function renderCodeFiles(ctx, files) {
    if (!files || !files.length) {
      return '<span class="ans-empty">' + u.esc(u.t(ctx, "no_answers_yet", gettext("Hələ cavab yoxdur"))) + '</span>';
    }
    return '<div class="code-files">' + files.map(function (f, i) {
      var empty = !(f.content || "").trim();
      var open = i === 0 && !empty;
      var lines = (f.content || "").split("\n").length;
      return '<div class="code-file' + (open ? " open" : "") + '" data-codefile>' +
        '<button type="button" class="code-file-head" data-codetoggle>' +
        '<i class="fab ' + fileIcon(f.name) + '"></i> <span class="cf-name">' + u.esc(f.name) + '</span>' +
        '<span class="cf-meta">' + (empty ? u.esc(u.t(ctx, "file_empty", gettext("boş"))) : (lines + " " + u.t(ctx, "lines", gettext("sətir")))) + '</span>' +
        '<i class="fas fa-chevron-down cf-caret"></i></button>' +
        '<pre class="code-file-body"><code>' + u.esc(f.content || "") + '</code></pre>' +
        '</div>';
    }).join("") + '</div>';
  }

  function renderQuestionMedia(a) {
    var html = "";
    if (a.image_url) {
      html += '<div class="ans-media"><img src="' + u.esc(a.image_url) + '" alt="" loading="lazy" /></div>';
    }
    if (a.video_url) {
      html += '<div class="ans-media"><video controls preload="metadata" playsinline src="' + u.esc(a.video_url) + '"></video></div>';
    }
    return html;
  }

  function renderTestOptions(ctx, options) {
    return '<div class="ans-options">' + (options || []).map(function (o) {
      var cls = o.is_correct ? "opt-correct" : (o.is_selected ? "opt-wrong" : "opt-neutral");
      var icon = o.is_correct ? '<i class="fas fa-check-circle" style="color:#16a34a"></i>' : (o.is_selected ? '<i class="fas fa-times-circle" style="color:#dc2626"></i>' : '<i class="far fa-circle" style="color:#94a3b8"></i>');
      var lbl = o.label ? '<b>' + u.esc(o.label) + ')</b> ' : '';
      var tags = [];
      if (o.is_selected) tags.push('<span class="opt-tag opt-picked">' + u.esc(u.t(ctx, "picked_option", gettext("Seçilib"))) + '</span>');
      if (o.is_correct) tags.push('<span class="opt-tag opt-key">' + u.esc(u.t(ctx, "correct_option", gettext("Düz"))) + '</span>');
      return '<div class="ans-option-item ' + cls + '">' + icon + '<span class="opt-text">' + lbl + u.esc(o.text) + '</span>' + (tags.length ? '<span class="opt-tags">' + tags.join("") + '</span>' : '') + '</div>';
    }).join("") + '</div>';
  }

  function renderOneAnswer(ctx, a, idx) {
    var kindBadge = {
      test: { label: u.t(ctx, "kind_test", "Test"), cls: "type-test" },
      written: { label: u.t(ctx, "kind_written", gettext("Yazılı")), cls: "type-written" },
      paint: { label: u.t(ctx, "kind_paint", gettext("Çəkim")), cls: "type-paint" },
      coding: { label: u.t(ctx, "kind_coding", "Praktiki"), cls: "type-coding" }
    };
    var badgeDef = kindBadge[a.kind] || kindBadge.written;
    var badge = '<span class="ans-type-badge ' + badgeDef.cls + '">' + u.esc(badgeDef.label) + '</span>';
    var statusChip = a.is_answered ? '<span class="ans-status answered"><i class="fas fa-circle-check"></i> ' + u.esc(u.t(ctx, "answered_chip", gettext("Cavablanıb"))) + '</span>' : '<span class="ans-status pending"><i class="fas fa-circle"></i> ' + u.esc(u.t(ctx, "unanswered_chip", gettext("Boş"))) + '</span>';
    var body = "";
    if (a.kind === "coding") {
      body = renderCodeFiles(ctx, a.files);
      if (a.execution_status) {
        body += '<div class="ans-run-meta"><i class="fas fa-terminal"></i> ' + u.esc(u.t(ctx, "last_run", "Son icra")) + ': ' + u.esc(a.execution_status) + '</div>';
      }
    } else if (a.kind === "test") {
      body = renderTestAnswer(ctx, a);
    } else if (a.kind === "paint") {
      body = renderPaintAnswer(ctx, a);
    } else {
      body = renderWrittenAnswer(ctx, a);
    }
    return '<div class="ans-item ' + (a.is_answered ? "is-answered" : "is-pending") + '">' +
      '<div class="ans-q"><span class="ans-num">' + (idx + 1) + '.</span> ' +
      '<span class="ans-q-text">' + u.esc(a.question_text || u.t(ctx, "question", "Sual")) + '</span>' +
      badge + statusChip + '</div>' + renderQuestionMedia(a) + '<div class="ans-a">' + body + '</div></div>';
  }

  function renderTestAnswer(ctx, a) {
    if (a.options && a.options.length) {
      return renderTestOptions(ctx, a.options);
    }
    if (a.selected_options && a.selected_options.length) {
      var body = '<div class="ans-options">' + a.selected_options.map(function (o) {
        var ok = o.is_correct;
        var icon = ok ? '<i class="fas fa-check-circle" style="color:#16a34a"></i>' : '<i class="fas fa-circle-dot" style="color:#2563eb"></i>';
        var lbl = o.label ? '<b>' + u.esc(o.label) + ')</b> ' : '';
        return '<div class="ans-option-item ' + (ok ? "opt-correct" : "opt-chosen") + '">' + icon + ' ' + lbl + u.esc(o.text) + '</div>';
      }).join("") + '</div>';
      var pickedWrong = a.selected_options.some(function (o) { return !o.is_correct; });
      if (pickedWrong && a.correct_options && a.correct_options.length) {
        body += '<div class="ans-correct-hint"><i class="fas fa-key"></i> ' + u.esc(u.t(ctx, "correct_answer", gettext("Düzgün cavab"))) + ': ' +
          a.correct_options.map(function (o) { return (o.label ? u.esc(o.label) + ") " : "") + u.esc(o.text); }).join(", ") + '</div>';
      }
      return body;
    }
    return '<span class="ans-empty">' + u.esc(u.t(ctx, "no_answers_yet", gettext("Hələ cavab yoxdur"))) + '</span>';
  }

  function renderPaintAnswer(ctx, a) {
    if (a.paint_image_url) {
      return '<div class="ans-media"><a href="' + u.esc(a.paint_image_url) + '" target="_blank" rel="noopener"><img src="' + u.esc(a.paint_image_url) + '" alt="" loading="lazy" /></a></div>';
    }
    if (a.has_paint) {
      return '<span class="pill"><i class="fas fa-paint-brush"></i> ' + u.esc(u.t(ctx, "paint_answer", gettext("Çəkim cavabı verilib"))) + '</span>';
    }
    if (a.text_answer) {
      return '<div class="ans-text-block">' + u.esc(a.text_answer) + '</div>';
    }
    return '<span class="ans-empty">' + u.esc(u.t(ctx, "no_answers_yet", gettext("Hələ cavab yoxdur"))) + '</span>';
  }

  function renderWrittenAnswer(ctx, a) {
    if (a.text_answer) {
      return '<div class="ans-text-block">' + u.esc(a.text_answer) + '</div>';
    }
    if (a.files && a.files.length) {
      return '<div class="ans-files">' + a.files.map(function (fn) {
        return '<span class="pill"><i class="fas fa-paperclip"></i> ' + u.esc(fn) + '</span>';
      }).join(" ") + '</div>';
    }
    return '<span class="ans-empty">' + u.esc(u.t(ctx, "no_answers_yet", gettext("Hələ cavab yoxdur"))) + '</span>';
  }

  function renderAnswers(ctx, d) {
    var answers = d.answers || [];
    if (!answers.length) {
      return '<div class="side-empty">' + u.esc(u.t(ctx, "no_answers_yet", gettext("Hələ heç bir suala cavab verilməyib."))) + '</div>';
    }
    return answers.map(function (a, idx) { return renderOneAnswer(ctx, a, idx); }).join("");
  }

  function renderModal(ctx, d) {
    ctx.currentSnapshot = d;
    u.$("modalStudentName").textContent = d.student_name;
    var metaBits = ["@" + d.student_username, (ctx.STATUS_LABELS[d.supervision_status] || d.supervision_status)];
    if (d.exam_title) metaBits.push(d.exam_title);
    u.$("modalStudentMeta").textContent = metaBits.join(" · ");
    var scoreBlock = "";
    if (d.is_finished) {
      var sVal, sLabel;
      if (d.teacher_score != null && d.checked_by_teacher) {
        sVal = d.teacher_score;
        sLabel = u.t(ctx, "teacher_score_label", gettext("Müəllim balı"));
      } else {
        sVal = d.score_percent != null ? d.score_percent + "%" : "—";
        sLabel = d.checked_by_teacher ? u.t(ctx, "teacher_score_label", gettext("Qiymət")) : u.t(ctx, "auto_score_label", gettext("Avtomatik nəticə"));
      }
      scoreBlock = '<div class="mon-metric"><div class="mm-v" style="color:#16a34a">' + sVal + '</div><div class="mm-l">' + u.esc(sLabel) + '</div></div>';
    } else if (d.live_score_percent != null) {
      // İmtahan davam edərkən cari (müvəqqəti) avtomatik bal — cavablanmamış
      // suallar səhv sayılır, ona görə imtahan indi bitsəydi neçə bal olardısını
      // göstərir. Yaşıldan fərqli (mavi) rəng ilə "hələ yekun deyil" bildirir.
      var liveDetail = (d.live_score != null && d.live_max_score != null)
        ? '<div class="mm-sub">' + u.esc(d.live_score) + '/' + u.esc(d.live_max_score) + '</div>' : '';
      scoreBlock = '<div class="mon-metric mon-metric--live"><div class="mm-v" style="color:#2563eb">' + d.live_score_percent + '%</div>' +
        '<div class="mm-l">' + u.esc(u.t(ctx, "live_score_label", gettext("Cari bal (canlı)"))) + '</div>' + liveDetail + '</div>';
    }
    var incHtml = (d.incidents && d.incidents.length) ? d.incidents.map(function (e) {
      return '<div class="inc-item"><i class="fas fa-circle" style="font-size:0.5rem;color:#dc3545"></i> ' +
        u.esc(e.event_display || ctx.EVENT_LABELS[e.event_type] || e.event_type) +
        '<span class="inc-time">' + u.timeAgo(e.timestamp) + '</span></div>';
    }).join("") : '<div class="side-empty">' + u.esc(u.t(ctx, "no_violations", gettext("Pozuntu qeydə alınmayıb."))) + '</div>';
    var startedRow = '<div class="mon-meta-row"><i class="fas fa-calendar-day"></i> ' + u.esc(u.t(ctx, "exam_date_label", gettext("İmtahan tarixi"))) + ': <b>' + u.esc(u.fmtDateTime(d.started_at)) + '</b>' +
      (d.finished_at ? ' &nbsp;·&nbsp; <i class="fas fa-flag-checkered"></i> ' + u.esc(u.t(ctx, "finished_at_label", gettext("Bitmə"))) + ': <b>' + u.esc(u.fmtDateTime(d.finished_at)) + '</b>' : '') + '</div>';
    u.$("modalBody").innerHTML =
      '<div class="mon-note"><i class="fas fa-eye"></i> ' + u.esc(u.t(ctx, "monitor_note", gettext("Bu, yalnız izləmə rejimidir — tələbə bloklanmır."))) + '</div>' +
      startedRow + '<div class="mon-grid">' +
      '<div class="mon-metric"><div class="mm-v">' + d.answered + '/' + d.total_questions + '</div><div class="mm-l">' + u.esc(u.t(ctx, "answered_label", gettext("Cavablanıb"))) + '</div></div>' +
      '<div class="mon-metric"><div class="mm-v">' + Math.max(0, d.total_questions - d.answered) + '</div><div class="mm-l">' + u.esc(u.t(ctx, "remaining_label", gettext("Qalıb"))) + '</div></div>' +
      '<div class="mon-metric"><div class="mm-v" style="color:#dc3545">' + d.violation_count + '</div><div class="mm-l">' + u.esc(u.t(ctx, "violations_label", "Pozuntu")) + '</div></div>' +
      scoreBlock + '</div><div class="mon-section-title">' + u.esc(u.t(ctx, "current_answers", "Cari cavablar")) + '</div>' + renderAnswers(ctx, d) +
      '<div class="mon-section-title">' + u.esc(u.t(ctx, "violation_log", gettext("Pozuntu jurnalı"))) + '</div>' + incHtml;
    var finished = d.is_finished;
    var canResume = (d.supervision_status === "locked" || d.supervision_status === "removed") && !finished;
    u.$("modalResumeBtn").style.display = canResume ? "inline-flex" : "none";
    u.$("modalPauseBtn").style.display = !finished && d.supervision_status !== "locked" && d.supervision_status !== "removed" ? "inline-flex" : "none";
    u.$("modalStopBtn").style.display = !finished ? "inline-flex" : "none";
    u.$("modalAnswerCount").textContent = (d.answered || 0) + "/" + (d.total_questions || 0) + " " + u.t(ctx, "questions_answered", gettext("sual cavablanıb"));
  }

  function openModal(ctx, attemptId) {
    ctx.currentAttempt = attemptId;
    ctx.modal.classList.add("show");
    u.$("modalBody").innerHTML = gettext('<div class="modal-loading"><i class="fas fa-circle-notch fa-spin"></i><p>Yüklənir…</p></div>');
    ["modalResumeBtn", "modalPauseBtn", "modalStopBtn"].forEach(function (b) { u.$(b).style.display = "none"; });
    fetch(ctx.SNAPSHOT_BASE + attemptId + "/", { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json(); })
      .then(function (d) { renderModal(ctx, d); })
      .catch(function () {
        u.$("modalBody").innerHTML = gettext('<div class="modal-loading">Məlumat yüklənmədi.</div>');
      });
  }

  function closeModal(ctx) {
    ctx.modal.classList.remove("show");
    ctx.currentAttempt = null;
    ctx.currentSnapshot = null;
  }

  function install(ctx) {
    installTooltip(ctx);
    u.$("studentMap").addEventListener("click", function (e) {
      var cell = e.target.closest(".smap-cell");
      if (cell) openModal(ctx, cell.getAttribute("data-attempt"));
    });
    u.$("modalClose").addEventListener("click", function () { closeModal(ctx); });
    // "Yenilə" — modal açıq qalarkən performans üçün avtomatik poll YOXDUR;
    // nəzarətçi bu düymə ilə cari cavabları və canlı balı yenidən çəkir.
    var refreshBtn = u.$("modalRefreshBtn");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", function () {
        if (ctx.currentAttempt) openModal(ctx, ctx.currentAttempt);
      });
    }
    u.$("modalBody").addEventListener("click", function (e) {
      var toggle = e.target.closest("[data-codetoggle]");
      if (!toggle) return;
      var file = toggle.closest("[data-codefile]");
      if (file) file.classList.toggle("open");
    });
    ctx.modal.addEventListener("click", function (e) {
      if (e.target === ctx.modal) closeModal(ctx);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeModal(ctx);
    });
  }

  ns.snapshot = {
    closeModal: closeModal,
    install: install
  };
})(window, document);
