(function (window, document) {
  "use strict";

  var ns = window.EMSExamLiveMonitor || (window.EMSExamLiveMonitor = {});
  var u = ns.utils;

  function showConfirm(ctx, title, message, btnText, btnClass, onConfirm) {
    u.$("confirmTitle").textContent = title;
    u.$("confirmMessage").textContent = message;
    var okBtn = u.$("confirmOk");
    okBtn.innerHTML = btnText;
    okBtn.className = "btn-act " + btnClass;
    ctx.pendingConfirmAction = onConfirm;
    ctx.confirmOverlay.classList.add("show");
  }

  function hideConfirm(ctx) {
    ctx.confirmOverlay.classList.remove("show");
    ctx.pendingConfirmAction = null;
  }

  function toast(ctx, msg, type) {
    var el = u.$("lvToast");
    el.textContent = msg;
    el.className = "lv-toast show" + (type ? " is-" + type : "");
    clearTimeout(ctx.toastTimer);
    ctx.toastTimer = setTimeout(function () {
      el.className = "lv-toast";
    }, 3000);
  }

  function postAction(ctx, base, attemptId, body, okMsg) {
    return fetch(base + attemptId + "/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": u.getCSRF(), "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(body || {})
    }).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, data: j }; });
    }).then(function (res) {
      if (res.ok && res.data.success) {
        toast(ctx, okMsg, "success");
        ns.snapshot.closeModal(ctx);
        if (typeof ctx.fetchData === "function") {
          ctx.fetchData();
        }
      } else {
        toast(ctx, (res.data && res.data.error) || u.t(ctx, "toast_error", "Əməliyyat alınmadı"), "error");
      }
    }).catch(function () {
      toast(ctx, u.t(ctx, "toast_connection_error", "Bağlantı xətası"), "error");
    });
  }

  function installConfirm(ctx) {
    u.$("confirmClose").addEventListener("click", function () { hideConfirm(ctx); });
    u.$("confirmCancel").addEventListener("click", function () { hideConfirm(ctx); });
    ctx.confirmOverlay.addEventListener("click", function (e) {
      if (e.target === ctx.confirmOverlay) hideConfirm(ctx);
    });
    u.$("confirmOk").addEventListener("click", function () {
      if (ctx.pendingConfirmAction) ctx.pendingConfirmAction();
      hideConfirm(ctx);
    });
  }

  function installModalActions(ctx) {
    u.$("modalStopBtn").addEventListener("click", function () {
      if (!ctx.currentAttempt) return;
      showConfirm(
        ctx,
        u.t(ctx, "confirm_stop_title", "İmtahandan uzaqlaşdır"),
        u.t(ctx, "confirm_stop_msg", "Tələbənin imtahanını birdəfəlik dayandırmaq istəyirsiniz? İmtahan dərhal təslim ediləcək və geri qaytarıla bilməyəcək."),
        '<i class="fas fa-ban"></i> ' + u.t(ctx, "confirm_stop_btn", "Bəli, uzaqlaşdır"),
        "btn-stop2",
        function () { postAction(ctx, ctx.STOP_BASE, ctx.currentAttempt, {}, u.t(ctx, "toast_student_removed", "Tələbə imtahandan uzaqlaşdırıldı")); }
      );
    });
    u.$("modalPauseBtn").addEventListener("click", function () {
      if (!ctx.currentAttempt) return;
      showConfirm(
        ctx,
        u.t(ctx, "confirm_pause_title", "Müvəqqəti blokla"),
        u.t(ctx, "confirm_pause_msg", "Tələbənin ekranı kilidlənəcək. İmtahan dayandırılmayacaq — sonradan bərpa edə bilərsiniz."),
        '<i class="fas fa-lock"></i> ' + u.t(ctx, "confirm_pause_btn", "Bəli, blokla"),
        "btn-pause",
        function () { postAction(ctx, ctx.LOCK_BASE, ctx.currentAttempt, {}, u.t(ctx, "toast_student_blocked", "Tələbə müvəqqəti bloklandı")); }
      );
    });
    u.$("modalResumeBtn").addEventListener("click", function () {
      if (!ctx.currentAttempt) return;
      var isManual = ctx.currentSnapshot && ctx.currentSnapshot.manual_lock;
      var msg = isManual
        ? u.t(ctx, "confirm_resume_manual_msg", "Tələbənin imtahana davam etməsinə icazə verilsin? Pozuntu sayı dəyişməyəcək.")
        : u.t(ctx, "confirm_resume_msg", "Tələbənin imtahana davam etməsinə icazə vermək istəyirsiniz? Əlavə şans da veriləcək.");
      showConfirm(
        ctx,
        u.t(ctx, "confirm_resume_title", "Bərpa et"),
        msg,
        '<i class="fas fa-play"></i> ' + u.t(ctx, "confirm_resume_btn", "Bəli, bərpa et"),
        "btn-resume2",
        function () { postAction(ctx, ctx.RESUME_BASE, ctx.currentAttempt, { grant_extra_chance: !isManual }, u.t(ctx, "toast_student_resumed", "Tələbə bərpa edildi")); }
      );
    });
  }

  function installBlockedActions(ctx) {
    document.addEventListener("click", function (e) {
      var resumeBtn = e.target.closest("[data-blocked-resume]");
      if (resumeBtn) {
        var aid = resumeBtn.getAttribute("data-blocked-resume");
        showConfirm(
          ctx,
          u.t(ctx, "confirm_resume_title", "Bərpa et"),
          u.t(ctx, "confirm_resume_msg", "Bu tələbənin imtahana davam etməsinə icazə vermək istəyirsiniz?"),
          '<i class="fas fa-play"></i> ' + u.t(ctx, "confirm_resume_btn", "Bəli, bərpa et"),
          "btn-resume2",
          function () { postAction(ctx, ctx.RESUME_BASE, aid, { grant_extra_chance: true }, u.t(ctx, "toast_student_resumed", "Tələbə bərpa edildi")); }
        );
        return;
      }
      var stopBtn = e.target.closest("[data-blocked-stop]");
      if (stopBtn) {
        var aid2 = stopBtn.getAttribute("data-blocked-stop");
        showConfirm(
          ctx,
          u.t(ctx, "confirm_stop_title", "İmtahandan uzaqlaşdır"),
          u.t(ctx, "confirm_stop_msg", "Bu tələbəni imtahandan birdəfəlik çıxarmaq istəyirsiniz? Bu əməliyyat geri alına bilməz."),
          '<i class="fas fa-ban"></i> ' + u.t(ctx, "confirm_stop_btn", "Bəli, uzaqlaşdır"),
          "btn-stop2",
          function () { postAction(ctx, ctx.STOP_BASE, aid2, {}, u.t(ctx, "toast_student_removed", "Tələbə imtahandan uzaqlaşdırıldı")); }
        );
      }
    });
  }

  function install(ctx) {
    installConfirm(ctx);
    installModalActions(ctx);
    installBlockedActions(ctx);
  }

  ns.actions = {
    install: install,
    toast: toast
  };
})(window, document);
