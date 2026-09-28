/* ════════════════════════════════════════════════════════════════════════════
   EMSArena — Kurs paneli · «AI ilə kurs qur» çekməcəsi (2026-09-28, REAL)

   Əvvəlki versiya vitrin idi: istənilən prompt-a eyni hazır planı göstərir,
   «Təsdiqlə» heç nə yaratmırdı. İndi:
     prompt → POST courses:ai_plan (Gemini, heç nə yazılmır) → müəllim mövzu və
     resursları seçir → POST courses:ai_apply (atomik yaradılır) → səhifə yenilənir.

   Konfiqurasiya və BÜTÜN mətnlər #courseAIConfig data-* atributlarındadır
   (partials/_ai_drawer_config.html) — JS-də sərt kodlanmış dil yoxdur.
   Açıcı: istənilən [data-ems-ai] elementi (EMSDelegate). A11y: role=dialog,
   aria-modal, fokus tələsi, Escape, fokusun açıcıya qayıtması.
   ════════════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  var ICON = {
    spark: '<path d="M12 3l1.8 4.9L19 9.7l-5.2 1.8L12 16l-1.8-4.5L5 9.7l5.2-1.8L12 3Z"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    back: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    retry: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5"/>'
  };
  function ic(name, size) {
    return '<svg width="' + (size || 16) + '" height="' + (size || 16) + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + ICON[name] + '</svg>';
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  var cfgEl = null, T = {}, root = null, state = null, opener = null;

  function readConfig() {
    cfgEl = document.getElementById("courseAIConfig");
    if (!cfgEl) { return false; }
    T = {};
    Object.keys(cfgEl.dataset).forEach(function (k) {
      if (k.indexOf("t") === 0 && k.length > 1) {
        var key = k.charAt(1).toLowerCase() + k.slice(2);
        T[key] = cfgEl.dataset[k];
      }
    });
    return true;
  }
  function fmt(str, vars) {
    return String(str || "").replace(/\{(\w+)\}/g, function (_, k) { return vars[k] != null ? vars[k] : ""; });
  }

  /* ───────────────────────── open / close ───────────────────────── */
  function open(trigger) {
    if (root || !readConfig()) { return; }
    opener = trigger || document.activeElement;
    state = { phase: "prompt", prompt: "", plan: null, sel: {}, error: "", remaining: null, created: null };
    root = document.createElement("div");
    root.className = "ems-ai-root";
    root.innerHTML =
      '<div class="ai-scrim" data-act="close"></div>' +
      '<aside class="ai-drawer" role="dialog" aria-modal="true" aria-labelledby="aiDrawerTitle"></aside>';
    document.body.appendChild(root);
    document.body.classList.add("ems-ai-open");
    requestAnimationFrame(function () { if (root) { root.classList.add("open"); } });
    render();
    focusFirst();
  }

  function close() {
    if (!root) { return; }
    if (state && state.phase === "applying") { return; }
    var el = root;
    root = null;
    el.classList.remove("open");
    document.body.classList.remove("ems-ai-open");
    setTimeout(function () { el.remove(); }, 220);
    if (state && state.phase === "done") { window.location.reload(); return; }
    if (opener && opener.focus) { try { opener.focus(); } catch (e) { /* noop */ } }
  }

  function focusFirst() {
    if (!root) { return; }
    var t = root.querySelector('[data-el="prompt"]') || root.querySelector(".aid-x");
    if (t) { t.focus(); }
  }

  /* ───────────────────────── render ───────────────────────── */
  function render() {
    if (!root) { return; }
    var d = root.querySelector(".ai-drawer");
    d.setAttribute("aria-busy", state.phase === "generating" || state.phase === "applying" ? "true" : "false");
    d.innerHTML =
      '<div class="aid-head"><div class="aid-head-top">' +
        '<span class="aid-spark">' + ic("spark", 20) + "</span>" +
        '<div><h2 class="aid-title" id="aiDrawerTitle">' + esc(T.title) + '</h2><p class="aid-sub">' + esc(T.sub) + "</p></div>" +
        '<button type="button" class="aid-x" data-act="close" aria-label="' + esc(T.close) + '">' + ic("x", 19) + "</button>" +
      "</div></div>" +
      '<div class="aid-body">' + body() + "</div>" + foot();
    var ta = d.querySelector('[data-el="prompt"]');
    if (ta) {
      ta.addEventListener("input", function () {
        state.prompt = ta.value;
        var g = d.querySelector('[data-act="generate"]');
        if (g) { g.disabled = !ta.value.trim(); }
      });
    }
  }

  function errorBox() {
    if (!state.error) { return ""; }
    return '<div class="aid-error" role="alert">' + ic("alert", 16) + "<span>" + esc(state.error) + "</span></div>";
  }

  function body() {
    if (state.phase === "prompt") {
      var chips = [T.ex1, T.ex2, T.ex3].filter(Boolean).map(function (ex) {
        return '<button type="button" class="aid-chip" data-act="ex" data-v="' + esc(ex) + '">' + esc(ex) + "</button>";
      }).join("");
      return errorBox() +
        '<label class="aid-prompt-lbl" for="aiPromptInput">' + esc(T.promptLabel) + "</label>" +
        '<textarea class="aid-ta" id="aiPromptInput" data-el="prompt" maxlength="1500" placeholder="' + esc(T.promptPlaceholder) + '">' + esc(state.prompt) + "</textarea>" +
        (chips ? '<div class="aid-ex"><div class="aid-ex-h">' + esc(T.examples) + '</div><div class="aid-ex-chips">' + chips + "</div></div>" : "") +
        '<div class="aid-note">' + ic("info", 15) + "<span>" + esc(T.note) + "</span></div>";
    }
    if (state.phase === "generating") {
      var rows = "";
      for (var i = 0; i < 5; i++) {
        rows += '<div class="aid-skel-card"><span class="aid-skel-n"></span><div class="aid-skel-lines">' +
          '<span class="aid-shimmer aid-shimmer--lg"></span><span class="aid-shimmer"></span></div></div>';
      }
      return '<div class="aid-gen" role="status"><div class="aid-gen-orb">' + ic("spark", 24) + "</div>" +
        '<div><div class="aid-gen-t">' + esc(T.generating) + '</div><div class="aid-gen-s">' + esc(T.generatingSub) + "</div></div></div>" +
        '<div class="aid-skel" aria-hidden="true">' + rows + "</div>";
    }
    if (state.phase === "review" || state.phase === "applying") { return review(); }
    if (state.phase === "done") {
      return '<div class="aid-done" role="status"><div class="ck">' + ic("check", 30) + "</div>" +
        "<h3>" + esc(T.doneTitle) + "</h3><p>" + esc(state.created || "") + "</p></div>";
    }
    return "";
  }

  function selectedCount() {
    var n = 0;
    (state.plan ? state.plan.topics : []).forEach(function (_, i) { if (state.sel["t" + i]) { n++; } });
    return n;
  }

  function review() {
    var topics = state.plan ? state.plan.topics : [];
    var all = topics.length && selectedCount() === topics.length;
    var html = errorBox() +
      '<div class="aid-plan-summary"><span class="ic">' + ic("spark", 18) + "</span><div>" +
      '<div class="t">' + esc(T.reviewTitle) + '</div><div class="s">' + esc(fmt(T.reviewSub, { count: topics.length })) + "</div></div>" +
      '<label class="aid-check aid-check--all"><input type="checkbox" data-act="all"' + (all ? " checked" : "") + "><span>" + esc(T.selectAll) + "</span></label></div>" +
      '<ol class="aid-topics">';
    topics.forEach(function (t, i) {
      var on = !!state.sel["t" + i];
      html += '<li class="aid-topic' + (on ? " is-on" : "") + '">' +
        '<label class="aid-topic__head"><input type="checkbox" data-act="topic" data-v="' + i + '"' + (on ? " checked" : "") + ">" +
        '<span class="aid-topic__n">' + (i + 1) + "</span>" +
        '<span class="aid-topic__tx"><span class="aid-topic__t">' + esc(t.title) + "</span>" +
        (t.description ? '<span class="aid-topic__d">' + esc(t.description) + "</span>" : "") + "</span></label>";
      if (t.resources && t.resources.length) {
        html += '<ul class="aid-res" aria-label="' + esc(T.resources) + '">';
        t.resources.forEach(function (r, j) {
          var k = "r" + i + "_" + j, ron = on && !!state.sel[k];
          html += '<li><label class="aid-check"><input type="checkbox" data-act="res" data-v="' + k + '"' + (ron ? " checked" : "") + (on ? "" : " disabled") + ">" +
            ic("link", 14) + '<span class="aid-res__t">' + esc(r.title) + "</span></label>" +
            '<a class="aid-res__url" href="' + esc(r.url) + '" target="_blank" rel="noopener noreferrer">' + esc(r.url.replace(/^https?:\/\//, "")) + "</a></li>";
        });
        html += "</ul>";
      }
      html += "</li>";
    });
    return html + "</ol>";
  }

  function foot() {
    if (state.phase === "prompt") {
      var quota = state.remaining != null ? '<span class="aid-quota">' + esc(fmt(T.quota, { count: state.remaining })) + "</span>" : "";
      return '<div class="aid-foot">' + quota + '<button type="button" class="aid-btn ai" data-act="generate"' + (state.prompt.trim() ? "" : " disabled") + ">" +
        ic("spark", 16) + " " + esc(T.generate) + "</button></div>";
    }
    if (state.phase === "review" || state.phase === "applying") {
      var busy = state.phase === "applying";
      var n = selectedCount();
      return '<div class="aid-foot">' +
        '<button type="button" class="aid-btn subtle" data-act="back"' + (busy ? " disabled" : "") + ' aria-label="' + esc(T.back) + '" title="' + esc(T.back) + '">' + ic("back", 16) + "</button>" +
        '<button type="button" class="aid-btn subtle" data-act="generate"' + (busy ? " disabled" : "") + ' title="' + esc(T.regenerate) + '">' + ic("retry", 16) + "<span class=\"aid-hide-sm\">" + esc(T.regenerate) + "</span></button>" +
        '<button type="button" class="aid-btn ai" data-act="apply"' + (n && !busy ? "" : " disabled") + ">" +
        (busy ? '<span class="aid-spin" aria-hidden="true"></span> ' + esc(T.applying) : ic("check", 15) + " " + esc(fmt(T.apply, { count: n }))) + "</button></div>";
    }
    if (state.phase === "done") {
      return '<div class="aid-foot"><button type="button" class="aid-btn ai" data-act="close">' + esc(T.doneAction) + "</button></div>";
    }
    return "";
  }

  /* ───────────────────────── actions ───────────────────────── */
  function generate() {
    if (!state.prompt.trim()) { return; }
    state.phase = "generating";
    state.error = "";
    render();
    window.EMSCore.fetchJSON(cfgEl.dataset.planUrl, { method: "POST", data: { prompt: state.prompt } })
      .then(function (res) {
        if (!root) { return; }
        state.plan = res.plan;
        state.sel = {};
        (res.plan.topics || []).forEach(function (t, i) {
          state.sel["t" + i] = true;
          (t.resources || []).forEach(function (_, j) { state.sel["r" + i + "_" + j] = true; });
        });
        if (res.remaining != null) { state.remaining = res.remaining; }
        state.phase = "review";
        render();
        var list = root.querySelector(".aid-body");
        if (list) { list.scrollTop = 0; }
      })
      .catch(function (err) {
        if (!root) { return; }
        state.error = (err && err.payload && err.payload.error) || T.error;
        state.phase = state.plan ? "review" : "prompt";
        render();
      });
  }

  function apply() {
    var topics = [];
    state.plan.topics.forEach(function (t, i) {
      if (!state.sel["t" + i]) { return; }
      topics.push({
        title: t.title,
        description: t.description,
        resources: (t.resources || []).filter(function (_, j) { return state.sel["r" + i + "_" + j]; })
      });
    });
    if (!topics.length) { return; }
    state.phase = "applying";
    state.error = "";
    render();
    window.EMSCore.fetchJSON(cfgEl.dataset.applyUrl, { method: "POST", data: { plan: { topics: topics } } })
      .then(function (res) {
        if (!root) { return; }
        state.created = res.message || "";
        state.phase = "done";
        render();
        var btn = root.querySelector('[data-act="close"].aid-btn');
        if (btn) { btn.focus(); }
      })
      .catch(function (err) {
        if (!root) { return; }
        state.error = (err && err.payload && err.payload.error) || T.error;
        state.phase = "review";
        render();
      });
  }

  function onClick(e) {
    var el = e.target.closest("[data-act]");
    if (!el || !root || !root.contains(el)) { return; }
    var act = el.getAttribute("data-act"), v = el.getAttribute("data-v");
    if (act === "close") { e.preventDefault(); close(); return; }
    if (act === "ex") { state.prompt = v; render(); focusFirst(); return; }
    if (act === "generate") { generate(); return; }
    if (act === "apply") { apply(); return; }
    if (act === "back") { state.phase = "prompt"; state.error = ""; render(); focusFirst(); return; }
  }

  function onChange(e) {
    var el = e.target;
    if (!root || !root.contains(el) || !el.matches("input[type=checkbox][data-act]")) { return; }
    var act = el.getAttribute("data-act"), v = el.getAttribute("data-v");
    if (act === "topic") {
      state.sel["t" + v] = el.checked;
      (state.plan.topics[+v].resources || []).forEach(function (_, j) { state.sel["r" + v + "_" + j] = el.checked; });
    } else if (act === "res") {
      state.sel[v] = el.checked;
    } else if (act === "all") {
      state.plan.topics.forEach(function (t, i) {
        state.sel["t" + i] = el.checked;
        (t.resources || []).forEach(function (_, j) { state.sel["r" + i + "_" + j] = el.checked; });
      });
    }
    var scroll = root.querySelector(".aid-body").scrollTop;
    render();
    root.querySelector(".aid-body").scrollTop = scroll;
    var again = root.querySelector('input[data-act="' + act + '"]' + (v ? '[data-v="' + v + '"]' : ""));
    if (again) { again.focus(); }
  }

  function onKey(e) {
    if (!root) { return; }
    if (e.key === "Escape") { e.preventDefault(); close(); return; }
    if (e.key !== "Tab") { return; }
    var f = root.querySelectorAll('button:not([disabled]), textarea, input:not([disabled]), a[href]');
    if (!f.length) { return; }
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  /* ───────────────────────── wiring (bir dəfə) ───────────────────────── */
  document.addEventListener("click", function (e) {
    var trigger = e.target.closest ? e.target.closest("[data-ems-ai]") : null;
    if (trigger) { e.preventDefault(); open(trigger); return; }
    onClick(e);
  });
  document.addEventListener("change", onChange);
  document.addEventListener("keydown", onKey);

  window.EMSCourseAI = { open: open, close: close };
})();
