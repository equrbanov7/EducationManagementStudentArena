/*
 * examBankPicker.js — «Suallar bankından seç» MODALI (redizayn 2026-10-19).
 * --------------------------------------------------------------------------
 * Sahib: «bu modalı da yenidən redesign et, daha yaxşı formada olsun və problemsiz işləsin».
 *
 *  Struktur: STATİK filtr sırası (bootstrap-select) + DƏYİŞƏN content (öz scroll-u) + STATİK alt sıra.
 *   - İlk açılışda bütün gövdə yüklənir; sonrakı açılışlarda bank/filtr/seçim SAXLANIR.
 *     Uğurlu əlavədən sonra növbəti açılışda content yenilənir («artıq əlavə olunub» görünsün).
 *   - Bank/dil/çətinlik → yalnız content yenilənir; axtarış EMSSearchInput-dan (1500 ms, ≥ 2 simvol, Enter).
 *   - Lazy-scroll: IntersectionObserver (root = content) + «Daha çox göstər» düyməsi (klaviatura ehtiyatı).
 *   - «Görünənlərin hamısını seç» (yüklənmiş, söndürülməmiş kartlar) və «Bütün N sualı seç» (cari
 *     filtrə uyğun HAMISI — serverdə select_all + excluded_ids ilə hesablanır).
 *   - Esc bağlayır (açıq seçici menyusu / dolu axtarış sahəsi əvvəl özünü bağlayır), fokus tələsi,
 *     bağlananda fokus açan düyməyə qayıdır.
 *   - Server xətaları (yükləmə, əlavə, 403/404) modalın içində göstərilir — əvvəl xəta səhifəsinin
 *     HTML-i modalın içinə yazılırdı, əlavə xətası isə `window.alert` idi.
 *   - Əlavədən sonra: data-picker-after="reload" → səhifə yenilənir (mesaj serverdən toast kimi gəlir),
 *     əks halda toast + modal bağlanır + `ems:bank-picker:attached` hadisəsi.
 *
 * AJAX-safe: dinləyicilər document səviyyəsindədir və BİR dəfə bağlanır; overlay hər əməldə
 * yenidən tapılır. CSP: inline style/HTML sətri yoxdur — skeleton <template>-dən klonlanır.
 * Köhnə köməkçilər (seçim anbarı, xəta kartı, fokus siyahısı): examBankPicker_parts.js — ƏVVƏL yüklənir.
 */
(function () {
  "use strict";

  if (window.__emsBankPickerBound || !window.EMSBankPickerParts) return;
  window.__emsBankPickerBound = true;

  var P = window.EMSBankPickerParts;
  var sel = P.selection(body);
  var state = {
    pickerUrl: "",
    returnFocus: null,
    modalToken: 0,
    contentToken: 0,
    loadingMore: false,
    observer: null,
    loaded: false,
    stale: false,
    mouseDownOnScrim: false,
  };

  function overlay() {
    return document.getElementById("bankPickerModal");
  }

  function body() {
    var el = overlay();
    return el ? el.querySelector("[data-bank-picker-body]") : null;
  }

  function isOpen() {
    var el = overlay();
    return Boolean(el && !el.hidden);
  }

  function tr(key, fallback) {
    var el = overlay();
    return (el && el.getAttribute("data-t-" + key)) || fallback;
  }

  function csrf() {
    if (window.EMSCore && typeof window.EMSCore.getCookie === "function") {
      return window.EMSCore.getCookie("csrftoken") || "";
    }
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function toast(message, level) {
    if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
      window.EMSToast.show(message, level || "info");
    }
  }

  function buildUrl(extra) {
    var usp = new URLSearchParams();
    usp.set("modal", "1");
    Object.keys(extra || {}).forEach(function (key) {
      if (extra[key] !== "" && extra[key] != null) usp.set(key, extra[key]);
    });
    var base = state.pickerUrl || (overlay() && overlay().getAttribute("data-picker-url")) || "";
    return base + (base.indexOf("?") >= 0 ? "&" : "?") + usp.toString();
  }

  function getHTML(url) {
    return fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin" }).then(
      function (response) {
        if (!response.ok) {
          var err = new Error("HTTP " + response.status);
          err.status = response.status;
          throw err;
        }
        return response.text();
      }
    );
  }

  function controls() {
    var values = {};
    var root = body();
    if (!root) return values;
    root.querySelectorAll("[data-picker-control]").forEach(function (el) {
      values[el.getAttribute("data-picker-control")] = el.value;
    });
    return values;
  }

  function control(name) {
    var root = body();
    return root ? root.querySelector('[data-picker-control="' + name + '"]') : null;
  }

  function setBusy(el, busy) {
    if (el) el.setAttribute("aria-busy", busy ? "true" : "false");
  }

  // ── Yükləmə ───────────────────────────────────────────────────────────
  function loadFull(extra) {
    var root = body();
    if (!root) return;
    var token = ++state.modalToken;
    root.textContent = "";
    root.appendChild(P.cloneTemplate("bankPickerSkeletonFull"));
    setBusy(root, true);
    getHTML(buildUrl(extra || {}))
      .then(function (html) {
        if (token !== state.modalToken) return;
        root.innerHTML = html;
        setBusy(root, false);
        if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.init(root);
        state.loaded = true;
        afterContent(true);
        focusFirstControl();
      })
      .catch(function (err) {
        if (token !== state.modalToken) return;
        setBusy(root, false);
        root.textContent = "";
        root.appendChild(P.errorState(tr, err && err.status));
      });
  }

  function reloadContent(searchInput) {
    var holder = body() && body().querySelector("[data-picker-content]");
    if (!holder) {
      loadFull();
      return;
    }
    sel.reset();
    hideError();
    var token = ++state.contentToken;
    var params = controls();
    params.content = "1";
    params.page = "1";
    var SI = window.EMSSearchInput;
    // Yazdıqca axtarış: köhnə siyahı sakitcə solur, skeletə çevrilmir (fokus/kursor qalır).
    var quiet = Boolean(searchInput && holder.children.length);
    if (quiet) {
      holder.classList.add("ems-search-pending");
      if (SI) SI.busy(searchInput, true);
    } else {
      holder.textContent = "";
      holder.appendChild(P.cloneTemplate("bankPickerSkeletonItems"));
    }
    setBusy(holder, true);
    getHTML(buildUrl(params))
      .then(function (html) {
        if (token !== state.contentToken) return;
        holder.classList.remove("ems-search-pending");
        if (quiet && SI) SI.busy(searchInput, false);
        holder.innerHTML = html;
        holder.scrollTop = 0;
        setBusy(holder, false);
        afterContent(true);
      })
      .catch(function (err) {
        if (token !== state.contentToken) return;
        holder.classList.remove("ems-search-pending");
        if (quiet && SI) SI.busy(searchInput, false);
        setBusy(holder, false);
        holder.textContent = "";
        holder.appendChild(P.errorState(tr, err && err.status));
      });
  }

  function loadMore(sentinel) {
    if (state.loadingMore || !sentinel || !sentinel.isConnected) return;
    var nextPage = sentinel.getAttribute("data-next-page");
    if (!nextPage) return;
    state.loadingMore = true;
    sentinel.classList.add("is-loading");
    var oldError = sentinel.querySelector(".bankpicker-sentinel__error");
    if (oldError) oldError.remove();

    var params = controls();
    params.items = "1";
    params.page = nextPage;
    var token = state.contentToken;
    getHTML(buildUrl(params))
      .then(function (html) {
        if (token !== state.contentToken || !sentinel.isConnected) return;
        var tmp = document.createElement("ul");
        tmp.innerHTML = html;
        var frag = document.createDocumentFragment();
        while (tmp.firstChild) frag.appendChild(tmp.firstChild);
        sentinel.parentNode.insertBefore(frag, sentinel);
        sentinel.parentNode.removeChild(sentinel);
        sel.sync();
        observeSentinel();
      })
      .catch(function () {
        sentinel.classList.remove("is-loading");
        var msg = document.createElement("p");
        msg.className = "bankpicker-sentinel__error";
        msg.setAttribute("role", "alert");
        msg.textContent = tr("more-error", "Növbəti suallar yüklənmədi.");
        sentinel.insertBefore(msg, sentinel.firstChild);
      })
      .then(function () {
        state.loadingMore = false;
      });
  }

  function observeSentinel() {
    if (state.observer) state.observer.disconnect();
    state.observer = null;
    var root = body();
    var sentinel = root && root.querySelector("[data-picker-sentinel]");
    if (!sentinel || typeof window.IntersectionObserver !== "function") return;
    state.observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) loadMore(entry.target);
        });
      },
      { root: root.querySelector("[data-picker-content]"), rootMargin: "240px" }
    );
    state.observer.observe(sentinel);
  }

  function afterContent(resetSel) {
    if (resetSel) sel.reset();
    sel.readTotal();
    sel.sync();
    observeSentinel();
  }

  // ── Xəta (alt sıra) ───────────────────────────────────────────────────
  function showError(message) {
    var root = body();
    var el = root && root.querySelector("[data-picker-error]");
    if (!el) {
      toast(message, "error");
      return;
    }
    el.textContent = message;
    el.hidden = false;
  }

  function hideError() {
    var root = body();
    var el = root && root.querySelector("[data-picker-error]");
    if (el) {
      el.hidden = true;
      el.textContent = "";
    }
  }

  // ── Açılış / bağlanış / fokus ─────────────────────────────────────────
  function dialog() {
    var el = overlay();
    return el ? el.querySelector(".bankpicker-dialog") : null;
  }

  function focusFirstControl() {
    var root = body();
    if (!root || !isOpen()) return;
    var bank = control("bank");
    var target = null;
    if (bank && !bank.value) {
      var wrap = bank.closest(".bootstrap-single-select");
      target = (wrap && wrap.querySelector(".bootstrap-single-select__toggle")) || bank;
    } else {
      target = control("q");
    }
    if (target && typeof target.focus === "function") {
      target.focus({ preventScroll: true });
    }
  }

  function open(trigger) {
    var el = overlay();
    if (!el) return;
    var url = trigger && trigger.getAttribute("data-picker-url");
    if (url && url !== state.pickerUrl) {
      if (state.pickerUrl) state.loaded = false; // başqa imtahan/naviqasiya sorğusu
      state.pickerUrl = url;
    } else if (!state.pickerUrl) {
      state.pickerUrl = el.getAttribute("data-picker-url") || "";
    }
    state.returnFocus = trigger || document.activeElement;
    el.hidden = false;
    document.body.classList.add("bankpicker-open");
    document.documentElement.classList.add("bankpicker-lock");
    var dlg = dialog();
    if (dlg) dlg.focus({ preventScroll: true });

    if (!state.loaded) {
      sel.reset();
      loadFull();
    } else if (state.stale) {
      state.stale = false;
      reloadContent();
      focusFirstControl();
    } else {
      observeSentinel();
      focusFirstControl();
    }
  }

  function close() {
    var el = overlay();
    if (!el || el.hidden) return;
    el.hidden = true;
    document.body.classList.remove("bankpicker-open");
    document.documentElement.classList.remove("bankpicker-lock");
    if (state.observer) state.observer.disconnect();
    hideError();
    var back = state.returnFocus;
    state.returnFocus = null;
    if (back && document.contains(back) && typeof back.focus === "function") {
      try {
        back.focus({ preventScroll: true });
      } catch (err) {
        /* fokus verilə bilməyən element */
      }
    }
  }

  // ── Əlavə et ──────────────────────────────────────────────────────────
  function setAttaching(button, on) {
    sel.busy = on;
    if (!button) return;
    var label = button.querySelector("[data-picker-attach-label]");
    if (label && !label.dataset.defaultText) label.dataset.defaultText = label.textContent;
    button.classList.toggle("is-loading", on);
    button.setAttribute("aria-busy", on ? "true" : "false");
    if (label) label.textContent = on ? tr("adding", "Əlavə olunur…") : label.dataset.defaultText;
    button.disabled = on || sel.count() === 0;
  }

  function attachErrorMessage(status, data) {
    if (data && data.error) return data.error;
    if (status === 403) return tr("forbidden", "Bu imtahana sual əlavə etmək icazəniz yoxdur.");
    if (status === 404) return tr("not-found", "Bank tapılmadı və ya artıq sizə açıq deyil.");
    return tr("attach-error", "Suallar əlavə olunmadı. Yenidən cəhd edin.");
  }

  function doAttach(button) {
    if (sel.busy) return;
    var values = controls();
    if (!values.bank || sel.count() === 0) return;
    hideError();
    setAttaching(button, true);

    var after = (overlay() && overlay().getAttribute("data-picker-after")) || "stay";
    var fd = new FormData();
    fd.set("modal", "1");
    fd.set("action", "attach");
    fd.set("bank", values.bank);
    fd.set("after", after);
    if (sel.selectAll) {
      fd.set("select_all", "1");
      fd.set("q", values.q || "");
      fd.set("language", values.language || "");
      fd.set("difficulty", values.difficulty || "");
      sel.excluded.forEach(function (id) { fd.append("excluded_ids", id); });
    } else {
      sel.selected.forEach(function (id) { fd.append("question_ids", id); });
    }

    var reloading = false;
    fetch(state.pickerUrl, {
      method: "POST",
      headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrf() },
      credentials: "same-origin",
      body: fd,
    })
      .then(function (response) {
        return response
          .json()
          .catch(function () { return {}; })
          .then(function (data) { return { ok: response.ok, status: response.status, data: data || {} }; });
      })
      .then(function (res) {
        if (!(res.ok && res.data.success)) {
          showError(attachErrorMessage(res.status, res.data));
          return;
        }
        if (after === "reload") {
          reloading = true;
          var target = res.data.redirect_url || "";
          var samePage = !target || new URL(target, window.location.href).pathname === window.location.pathname;
          if (samePage) window.location.reload();
          else window.location.href = target;
          return;
        }
        toast(res.data.message, res.data.count ? "success" : "warning");
        state.stale = true;
        sel.reset();
        document.dispatchEvent(new CustomEvent("ems:bank-picker:attached", { detail: res.data }));
        close();
      })
      .catch(function () {
        showError(tr("network-error", "Şəbəkə xətası — bağlantını yoxlayıb yenidən cəhd edin."));
      })
      .then(function () {
        if (!reloading) setAttaching(button, false);
        sel.render();
      });
  }

  // ── Hadisələr (document səviyyəsində, bir dəfə) ────────────────────────
  document.addEventListener("click", function (event) {
    var opener = event.target.closest && event.target.closest("[data-bank-picker-open]");
    if (opener) {
      event.preventDefault();
      open(opener);
      return;
    }
    var el = overlay();
    if (!el || el.hidden || !el.contains(event.target)) return;

    if (event.target === el) {
      if (state.mouseDownOnScrim) close();
      return;
    }
    if (event.target.closest("[data-bank-picker-close]")) {
      close();
      return;
    }
    if (event.target.closest("[data-picker-retry]")) {
      if (body() && body().querySelector("[data-picker-content]")) reloadContent();
      else loadFull();
      return;
    }
    var toggle = event.target.closest("[data-picker-toggle]");
    if (toggle) {
      var panel = document.getElementById(toggle.getAttribute("aria-controls"));
      var expanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", expanded ? "false" : "true");
      if (panel) panel.hidden = expanded;
      return;
    }
    var more = event.target.closest("[data-picker-more]");
    if (more) {
      loadMore(more.closest("[data-picker-sentinel]"));
      return;
    }
    var chip = event.target.closest("[data-picker-lang]");
    if (chip) {
      var lang = control("language");
      if (lang) {
        lang.value = chip.getAttribute("data-picker-lang");
        if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.sync(lang);
      }
      reloadContent();
      return;
    }
    if (event.target.closest("[data-picker-reset]")) {
      var q = control("q");
      if (q) {
        q.value = "";
        if (window.EMSSearchInput && window.EMSSearchInput.sync) window.EMSSearchInput.sync(q, "");
      }
      ["language", "difficulty"].forEach(function (name) {
        var sel = control(name);
        if (sel) {
          sel.value = "";
          if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.sync(sel);
        }
      });
      reloadContent();
      return;
    }
    if (event.target.closest("[data-picker-select-all]")) {
      sel.chooseAllMatching();
      return;
    }
    if (event.target.closest("[data-picker-deselect-all]")) {
      sel.reset();
      sel.sync();
      return;
    }
    var attach = event.target.closest("[data-picker-attach]");
    if (attach) doAttach(attach);
  });

  document.addEventListener("mousedown", function (event) {
    var el = overlay();
    state.mouseDownOnScrim = Boolean(el && event.target === el);
  });

  document.addEventListener("change", function (event) {
    var el = overlay();
    if (!el || !el.contains(event.target)) return;
    var target = event.target;
    if (target.matches('[data-picker-control="q"]')) return; // axtarışı EMSSearchInput idarə edir
    if (target.matches("[data-picker-control]")) {
      reloadContent();
      return;
    }
    if (target.matches("[data-picker-page-toggle]")) {
      sel.togglePage(target.checked);
      return;
    }
    if (target.matches("[data-picker-checkbox]")) {
      sel.set(target.value, target.checked);
      sel.render();
    }
  });

  // Esc / fokus tələsi — capture: Bootstrap dropdown-un öz Esc-i menyunu bağlamazdan ƏVVƏL baxırıq.
  document.addEventListener(
    "keydown",
    function (event) {
      if (!isOpen()) return;
      var el = overlay();
      if (event.key === "Escape") {
        if (el.querySelector(".dropdown-menu.show")) return; // əvvəl açıq seçici bağlansın
        var t = event.target;
        if (t && t.matches && t.matches('input[type="search"]') && t.value) return; // əvvəl sahə təmizlənsin
        event.preventDefault();
        event.stopPropagation();
        close();
        return;
      }
      if (event.key !== "Tab") return;
      var dlg = dialog();
      if (!dlg) return;
      var items = P.visibleFocusable(dlg);
      if (!items.length) {
        event.preventDefault();
        dlg.focus();
        return;
      }
      var first = items[0];
      var last = items[items.length - 1];
      var active = document.activeElement;
      if (event.shiftKey && (active === first || active === dlg || !dlg.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !dlg.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    },
    true
  );

  // Axtarış: vahid EMSSearchInput (1500 ms, ≥ 2 simvol, Enter dərhal, boşaldanda dərhal).
  if (window.EMSSearchInput && typeof window.EMSSearchInput.delegate === "function") {
    window.EMSSearchInput.delegate('[data-picker-control="q"]', {
      onSearch: function (value, meta) {
        var el = overlay();
        if (el && meta && meta.input && el.contains(meta.input)) reloadContent(meta.input);
      },
    });
  }

  // Test qarmağı (jsdom) — daxili vəziyyətə toxunmadan açıb-bağlamaq üçün.
  window.EMSBankPicker = { open: open, close: close, reload: reloadContent };
})();
