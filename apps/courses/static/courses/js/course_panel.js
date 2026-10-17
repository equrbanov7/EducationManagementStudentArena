/* ════════════════════════════════════════════════════════════════════════════
   EMSArena — Kurs paneli (course_dashboard.html) davranışı · 2026-09-28

   1) Tablar: server render edir (role=tablist); burada yalnız aktiv panel
      dəyişir, URL hash-i (#sec-<key>) saxlanır, ←/→/Home/End klaviatura
      naviqasiyası (WAI-ARIA tabs), üfüqi daşmada kənar kölgələri.
   2) (2026-10-17) Başqa tətbiqlərin bölmə partial-ları artıq `cd-task` kartlarıdır —
      «əlavə et» düymələri `course_dashboard.html`-də panel başlığındadır, JS ilə köçürmə yoxdur.
   3) Mövzu sətrinin açılıb-bağlanması ([data-cd-topic-toggle]).
   4) Üzv siyahısında dözümlü axtarış (EMSSearchFold varsa).
   5) Qrupu kursdan çıxarma (AJAX, təsdiq dialoqu ilə).

   AJAX-safe: hadisələr document-ə BİR dəfə delegə olunur; init idempotentdir.
   ════════════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  function rootEl() { return document.getElementById("courseDashboardRoot"); }

  /* ───────────────────────── tabs ───────────────────────── */
  function tabs() { return Array.prototype.slice.call(document.querySelectorAll("[data-cd-tab]")); }

  function activate(key, opts) {
    opts = opts || {};
    var list = tabs();
    var target = null;
    list.forEach(function (t) { if (t.getAttribute("data-cd-tab") === key) { target = t; } });
    if (!target) { return false; }
    list.forEach(function (t) {
      var on = t === target;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
      var panel = document.getElementById(t.getAttribute("aria-controls"));
      if (panel) { panel.hidden = !on; }
    });
    if (opts.focus) { target.focus(); }
    if (opts.scroll !== false && target.scrollIntoView) {
      target.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
    if (opts.push) {
      try { history.replaceState(null, "", "#sec-" + key); } catch (e) { /* noop */ }
      try { sessionStorage.setItem(storeKey(), key); } catch (e) { /* noop */ }
    }
    updateFades();
    return true;
  }

  /* Aktiv tab kurs üzrə yadda qalır: başqa tətbiqlərin skriptləri (imtahan
     əlaqələndirmə, forma saxlama) səhifəni hash-siz URL-ə yönləndirir — əvvəl
     istifadəçi hər dəfə «Mövzular»a qayıdırdı. */
  function storeKey() {
    var root = rootEl();
    return "ems-cd-tab-" + (root ? root.getAttribute("data-course-id") : "");
  }

  function updateFades() {
    var wrap = document.querySelector("[data-cd-tabs-wrap]");
    var bar = document.querySelector("[data-cd-tabs]");
    if (!wrap || !bar) { return; }
    var max = bar.scrollWidth - bar.clientWidth;
    wrap.classList.toggle("is-scroll-start", bar.scrollLeft > 4);
    wrap.classList.toggle("is-scroll-end", bar.scrollLeft < max - 4);
  }

  /* ───────────────────────── init (idempotent) ───────────────────────── */
  function init() {
    var root = rootEl();
    if (!root) { return; }

    var bar = document.querySelector("[data-cd-tabs]");
    if (bar && bar.dataset.cdBound !== "1") {
      bar.dataset.cdBound = "1";
      bar.addEventListener("scroll", updateFades, { passive: true });
      window.addEventListener("resize", updateFades);
    }
    var key = (location.hash || "").indexOf("#sec-") === 0 ? location.hash.slice(5) : "";
    if (!key) {
      try { key = sessionStorage.getItem(storeKey()) || ""; } catch (e) { key = ""; }
    }
    if (key === "groups") { key = "members"; }  // köhnə «Qruplar» tabı üzvlər panelinə birləşib
    if (!key || !activate(key, { scroll: true })) { updateFades(); }
    root.classList.add("is-ready");
  }

  /* ───────────────────────── delegated events ───────────────────────── */
  document.addEventListener("click", function (e) {
    var tab = e.target.closest("[data-cd-tab]");
    if (tab) { activate(tab.getAttribute("data-cd-tab"), { push: true }); return; }

    var toggle = e.target.closest("[data-cd-topic-toggle]");
    if (toggle) {
      var body = document.getElementById(toggle.getAttribute("aria-controls"));
      var open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (body) { body.hidden = !open; }
      var li = toggle.closest(".cd-topic");
      if (li) { li.classList.toggle("is-open", open); }
      return;
    }

    var rm = e.target.closest("[data-cd-remove-group]");
    if (rm) { removeGroup(rm); }
  });

  document.addEventListener("keydown", function (e) {
    var tab = e.target.closest && e.target.closest("[data-cd-tab]");
    if (!tab) { return; }
    var list = tabs();
    var i = list.indexOf(tab);
    var next = null;
    if (e.key === "ArrowRight") { next = list[(i + 1) % list.length]; }
    else if (e.key === "ArrowLeft") { next = list[(i - 1 + list.length) % list.length]; }
    else if (e.key === "Home") { next = list[0]; }
    else if (e.key === "End") { next = list[list.length - 1]; }
    if (next) {
      e.preventDefault();
      activate(next.getAttribute("data-cd-tab"), { push: true, focus: true });
    }
  });

  /* Yayımla / qaralamaya qaytar — POST-dan sonra aktiv tab (#sec-…) itməsin. */
  document.addEventListener("submit", function (e) {
    var form = e.target.closest && e.target.closest(".cd-publish");
    if (!form || !location.hash) { return; }
    var next = form.querySelector('input[name="next"]');
    if (next && next.value.indexOf("#") === -1) { next.value += location.hash; }
  });

  /* ───────────────────────── member search ───────────────────────── */
  function matcher(query) {
    if (window.EMSSearch && typeof window.EMSSearch.matcher === "function") {
      return window.EMSSearch.matcher(query);
    }
    var tokens = String(query || "").toLocaleLowerCase().split(/\s+/).filter(Boolean);
    return function (text) {
      var hay = String(text || "").toLocaleLowerCase();
      return tokens.every(function (t) { return hay.indexOf(t) !== -1; });
    };
  }

  document.addEventListener("input", function (e) {
    var input = e.target.closest && e.target.closest("[data-cd-member-search]");
    if (!input) { return; }
    var list = document.querySelector("[data-cd-member-list]");
    if (!list) { return; }
    var test = matcher(input.value.trim());
    var shown = 0;
    list.querySelectorAll(".cd-member").forEach(function (row) {
      var ok = !input.value.trim() || test(row.getAttribute("data-search"));
      row.hidden = !ok;
      if (ok) { shown++; }
    });
    var empty = document.querySelector("[data-cd-member-empty]");
    if (empty) { empty.hidden = shown !== 0; }
  });

  /* ───────────────────────── remove group ───────────────────────── */
  function removeGroup(btn) {
    var root = rootEl();
    if (!root || !root.dataset.deleteGroupUrl) { return; }
    var name = btn.getAttribute("data-cd-remove-group");
    var body = (root.dataset.i18nGroupRemoveBody || "").replace("{group}", name);
    window.EMSConfirm.open({
      title: root.dataset.i18nGroupRemoveTitle,
      body: body,
      confirmLabel: root.dataset.i18nRemove,
      danger: true
    }).then(function (ok) {
      if (!ok) { return; }
      btn.disabled = true;
      var fd = new FormData();
      fd.append("group_name", name);
      window.EMSCore.fetchJSON(root.dataset.deleteGroupUrl, { method: "POST", body: fd })
        .then(function () { window.location.reload(); })
        .catch(function (err) {
          btn.disabled = false;
          var msg = (err && err.payload && err.payload.error) || root.dataset.i18nGenericError;
          if (window.EMSToast && window.EMSToast.show) { window.EMSToast.show(msg, "error"); } else if (window.console) { window.console.error(msg); }
        });
    });
  }

  if (window.EMSReady) { window.EMSReady(init); }
  else if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", init); }
  else { init(); }
})();
