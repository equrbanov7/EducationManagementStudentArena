(function (window, document) {
  "use strict";

  var ns = window.EMSExamLiveMonitor || (window.EMSExamLiveMonitor = {});

  function readJsonScript(id, fallback) {
    var el = document.getElementById(id);
    if (!el) {
      return fallback;
    }
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return fallback;
    }
  }

  function t(ctx, key, fallback) {
    return (ctx.I18N && ctx.I18N[key]) || fallback || key;
  }

  function getCSRF() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }

  function $(id) {
    return document.getElementById(id);
  }

  function initials(name) {
    var parts = (name || "?").trim().split(/\s+/);
    return ((parts[0] || "")[0] || "") + (parts.length > 1 ? (parts[parts.length - 1][0] || "") : "");
  }

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function timeAgo(iso) {
    if (!iso) {
      return "";
    }
    var diff = Math.round((Date.now() - Date.parse(iso)) / 1000);
    if (diff < 60) {
      return diff + gettext(" san əvvəl");
    }
    if (diff < 3600) {
      return Math.floor(diff / 60) + gettext(" dəq əvvəl");
    }
    var d = new Date(iso);
    return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
  }

  function fmtDateTime(iso) {
    if (!iso) {
      return "—";
    }
    var d = new Date(iso);
    var p = function (n) {
      return ("0" + n).slice(-2);
    };
    return p(d.getDate()) + "." + p(d.getMonth() + 1) + "." + d.getFullYear() + " " + p(d.getHours()) + ":" + p(d.getMinutes());
  }

  function scoreText(s) {
    if (s.teacher_score != null && s.checked_by_teacher) {
      return s.teacher_score + gettext(" bal (müəllim)");
    }
    if (s.score_percent != null) {
      return s.score_percent + "%";
    }
    return s.is_finished ? "—" : "Davam edir";
  }

  function eventLabels(ctx) {
    return {
      fullscreen_exited: t(ctx, "event_fullscreen_exited", gettext("Tam ekrandan çıxış")),
      fullscreen_restored: gettext("Tam ekran bərpa edildi"),
      tab_switched: t(ctx, "event_tab_switched", gettext("Tab dəyişdirildi")),
      window_blurred: t(ctx, "event_window_blurred", gettext("Pəncərə fokusu itdi")),
      window_focused: gettext("Pəncərə fokusa qayıtdı"),
      copy_attempt: t(ctx, "event_copy_attempt", gettext("Kopyalama cəhdi")),
      paste_attempt: t(ctx, "event_paste_attempt", gettext("Yapışdırma cəhdi")),
      cut_attempt: gettext("Kəsmə cəhdi"),
      right_click_attempt: t(ctx, "event_right_click", gettext("Sağ klik cəhdi")),
      keyboard_shortcut: t(ctx, "event_keyboard_shortcut", gettext("Klaviatura qısayolu")),
      text_select_attempt: gettext("Mətn seçmə cəhdi"),
      suspicious_repeated: gettext("Şübhəli təkrar"),
      grace_period_expired: gettext("Möhlət bitdi"),
      auto_locked: t(ctx, "event_auto_locked", gettext("Avtomatik kilidləndi")),
      auto_submitted: gettext("Avtomatik təslim"),
      resume_window_expired: gettext("Bərpa müddəti bitdi"),
      teacher_resumed: gettext("Müəllim bərpa etdi"),
      teacher_granted_chance: gettext("Əlavə şans verildi")
    };
  }

  function statusLabels(ctx) {
    return {
      active: t(ctx, "status_active", "aktiv"),
      warned: t(ctx, "status_warned", gettext("xəbərdarlıq")),
      locked: t(ctx, "status_locked", "kilidli"),
      removed: t(ctx, "status_removed", gettext("çıxarılıb")),
      resumed: t(ctx, "status_resumed", gettext("bərpa olunub"))
    };
  }

  function createContext(wrap) {
    var ctx = {
      wrap: wrap,
      POLL_URL: wrap.getAttribute("data-poll-url"),
      SNAPSHOT_BASE: wrap.getAttribute("data-snapshot-base"),
      RESUME_BASE: wrap.getAttribute("data-resume-base"),
      LOCK_BASE: wrap.getAttribute("data-lock-base"),
      STOP_BASE: wrap.getAttribute("data-stop-base"),
      POLL_INTERVAL: 8000,
      I18N: readJsonScript("monitor-i18n", {}),
      state: readJsonScript("monitor-bootstrap", null),
      statusChart: null,
      progressChart: null,
      tip: null,
      modal: $("snapshotModal"),
      currentAttempt: null,
      currentSnapshot: null,
      confirmOverlay: $("confirmOverlay"),
      pendingConfirmAction: null,
      toastTimer: null,
      pollTimer: null,
      polling: true,
      fetchData: null
    };
    ctx.EVENT_LABELS = eventLabels(ctx);
    ctx.STATUS_LABELS = statusLabels(ctx);
    return ctx;
  }

  ns.utils = {
    createContext: createContext,
    esc: esc,
    fmtDateTime: fmtDateTime,
    getCSRF: getCSRF,
    initials: initials,
    scoreText: scoreText,
    t: t,
    timeAgo: timeAgo,
    $: $
  };
})(window, document);
