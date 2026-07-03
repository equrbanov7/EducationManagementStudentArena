/*
 * examBankPicker.js
 * --------------------------------------------------------------------------
 * "Suallar bankına bax" picker MODALI.
 *
 *  Struktur: STATİK toolbar (bootstrap-select) + DƏYİŞƏN content + STATİK footer.
 *   - Açılışda bütün gövdə bir dəfə yüklənir, bootstrap-select init olunur.
 *   - Bank/dil/çətinlik/axtarış → yalnız content yenilənir (toolbar qalır).
 *   - Lazy-scroll: IntersectionObserver sentinel-i görəndə növbəti səhifə əlavə olunur.
 *   - "Hamısını seç" cari filtrlərə uyğun BÜTÜN sualları seçir (görünən deyil) —
 *     attach zamanı select_all + excluded ilə serverdə hesablanır.
 *   - Sual üzərinə klik → variantlar akkordeonla açılır.
 *
 * CSP təhlükəsiz: bütün hook-lar data-* atributları ilədir.
 */
(function () {
  "use strict";

  function getCookie(name) {
    // Faza 6.3: mərkəzi EMSCore.getCookie (core/csrf.js); bu fayl "" gözləyir.
    return window.EMSCore.getCookie(name) || "";
  }

  document.addEventListener("DOMContentLoaded", function () {
    var overlay = document.getElementById("bankPickerModal");
    if (!overlay) return;

    var body = overlay.querySelector("[data-bank-picker-body]");
    var pickerUrl = overlay.getAttribute("data-picker-url") || "";

    // Seçim vəziyyəti
    var selectedIds = new Set(); // açıq seçim rejimi
    var excludedIds = new Set(); // "hamısı" rejimində istisna edilənlər
    var selectAllMatching = false;
    var currentTotal = 0;

    var searchTimer = null;
    var modalToken = 0;
    var contentToken = 0;
    var loadingMore = false;
    var observer = null;

    function buildUrl(extra) {
      var usp = new URLSearchParams();
      usp.set("modal", "1");
      Object.keys(extra || {}).forEach(function (key) {
        if (extra[key] !== "" && extra[key] != null) usp.set(key, extra[key]);
      });
      var sep = pickerUrl.indexOf("?") >= 0 ? "&" : "?";
      return pickerUrl + sep + usp.toString();
    }

    function currentControls() {
      var values = {};
      var root = body.querySelector(".bankpicker") || body;
      root.querySelectorAll("[data-picker-control]").forEach(function (el) {
        values[el.getAttribute("data-picker-control")] = el.value;
      });
      return values;
    }

    function setBodyLoading() {
      body.innerHTML =
        gettext('<div class="bankpicker-loading"><span class="bankpicker-spinner" aria-hidden="true"></span> Yüklənir...</div>');
    }

    // ── Açılış: tam modal gövdəsi ──
    function loadFullModal() {
      var token = ++modalToken;
      setBodyLoading();
      fetch(buildUrl({}), { headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin" })
        .then(function (r) { return r.text(); })
        .then(function (html) {
          if (token !== modalToken) return;
          body.innerHTML = html;
          if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.init(body);
          afterContentRendered(true);
        })
        .catch(function () {
          if (token !== modalToken) return;
          body.innerHTML =
            gettext('<div class="bankpicker-empty"><i class="fas fa-triangle-exclamation"></i><p>Yüklənmə xətası. Yenidən cəhd edin.</p></div>');
        });
    }

    // ── Yalnız content (filtr/bank dəyişimi) ──
    function reloadContent() {
      var holder = body.querySelector("[data-picker-content]");
      if (!holder) return;
      // Filtr dəyişdi → seçim sıfırlanır (uyğun çoxluq dəyişir).
      selectAllMatching = false;
      selectedIds.clear();
      excludedIds.clear();

      var token = ++contentToken;
      var params = currentControls();
      params.content = "1";
      params.page = "1";
      holder.innerHTML =
        gettext('<div class="bankpicker-loading"><span class="bankpicker-spinner" aria-hidden="true"></span> Yüklənir...</div>');
      fetch(buildUrl(params), { headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin" })
        .then(function (r) { return r.text(); })
        .then(function (html) {
          if (token !== contentToken) return;
          holder.innerHTML = html;
          afterContentRendered(true);
        })
        .catch(function () {
          if (token !== contentToken) return;
          holder.innerHTML =
            gettext('<div class="bankpicker-empty"><i class="fas fa-triangle-exclamation"></i><p>Yüklənmə xətası.</p></div>');
        });
    }

    // ── Lazy-scroll: növbəti səhifəni əlavə et ──
    function loadMore(sentinel) {
      if (loadingMore) return;
      var nextPage = sentinel.getAttribute("data-next-page");
      if (!nextPage) return;
      loadingMore = true;

      var params = currentControls();
      params.items = "1";
      params.page = nextPage;
      fetch(buildUrl(params), { headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin" })
        .then(function (r) { return r.text(); })
        .then(function (html) {
          // Sentinel-i yeni elementlər + (varsa) yeni sentinel ilə əvəz et.
          var tmp = document.createElement("div");
          tmp.innerHTML = html;
          var frag = document.createDocumentFragment();
          var added = [];
          while (tmp.firstChild) {
            var node = tmp.firstChild;
            if (node.nodeType === 1 && node.classList.contains("bankpicker-item")) added.push(node);
            frag.appendChild(node);
          }
          sentinel.parentNode.insertBefore(frag, sentinel);
          sentinel.parentNode.removeChild(sentinel);
          added.forEach(function (item) {
            var cb = item.querySelector("[data-picker-checkbox]");
            if (cb) syncCheckbox(cb);
          });
          loadingMore = false;
          observeSentinel();
        })
        .catch(function () { loadingMore = false; });
    }

    function observeSentinel() {
      if (observer) observer.disconnect();
      var sentinel = body.querySelector("[data-picker-sentinel]");
      if (!sentinel) return;
      observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) loadMore(entry.target);
          });
        },
        { root: body, rootMargin: "240px" }
      );
      observer.observe(sentinel);
    }

    // ── Seçim sinxronizasiyası ──
    function syncCheckbox(cb) {
      cb.checked = selectAllMatching ? !excludedIds.has(cb.value) : selectedIds.has(cb.value);
    }

    function syncAllVisible() {
      body.querySelectorAll("[data-picker-checkbox]").forEach(syncCheckbox);
    }

    function updateCount() {
      var n = selectAllMatching ? Math.max(0, currentTotal - excludedIds.size) : selectedIds.size;
      var label = body.querySelector("[data-picker-selected-count]");
      if (label) label.textContent = n + gettext(" seçilib");
      var attach = body.querySelector("[data-picker-attach]");
      if (attach) attach.disabled = n === 0;
    }

    function afterContentRendered(resetSelection) {
      if (resetSelection) {
        selectAllMatching = false;
        selectedIds.clear();
        excludedIds.clear();
      }
      var totalEl = body.querySelector("[data-picker-total]");
      currentTotal = totalEl ? parseInt(totalEl.getAttribute("data-picker-total"), 10) || 0 : 0;
      syncAllVisible();
      updateCount();
      observeSentinel();
    }

    // ── Açılış / bağlanış ──
    function open() {
      overlay.hidden = false;
      document.body.classList.add("bankpicker-open");
      selectAllMatching = false;
      selectedIds.clear();
      excludedIds.clear();
      loadFullModal();
    }
    function close() {
      overlay.hidden = true;
      document.body.classList.remove("bankpicker-open");
      if (observer) observer.disconnect();
    }

    document.querySelectorAll("[data-bank-picker-open]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var url = btn.getAttribute("data-picker-url");
        if (url) pickerUrl = url;
        open();
      });
    });

    overlay.addEventListener("click", function (e) {
      if (e.target === overlay || e.target.closest("[data-bank-picker-close]")) close();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !overlay.hidden) close();
    });

    // ── Delegasiya: change ──
    body.addEventListener("change", function (e) {
      if (e.target.closest("[data-picker-control]")) {
        reloadContent();
        return;
      }
      if (e.target.matches("[data-picker-checkbox]")) {
        var id = e.target.value;
        if (selectAllMatching) {
          if (e.target.checked) excludedIds.delete(id);
          else excludedIds.add(id);
        } else {
          if (e.target.checked) selectedIds.add(id);
          else selectedIds.delete(id);
        }
        updateCount();
      }
    });

    // ── Delegasiya: input (axtarış debounce) ──
    body.addEventListener("input", function (e) {
      if (!e.target.closest('[data-picker-control="q"]')) return;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(reloadContent, 300);
    });

    // ── Delegasiya: click ──
    body.addEventListener("click", function (e) {
      var toggle = e.target.closest("[data-picker-toggle]");
      if (toggle) {
        var item = toggle.closest(".bankpicker-item");
        if (item) item.classList.toggle("is-open");
        return;
      }
      var chip = e.target.closest("[data-picker-lang]");
      if (chip) {
        var langSelect = body.querySelector('[data-picker-control="language"]');
        if (langSelect) {
          langSelect.value = chip.getAttribute("data-picker-lang");
          if (window.EMSBootstrapSelect) window.EMSBootstrapSelect.sync(langSelect);
        }
        reloadContent();
        return;
      }
      if (e.target.closest("[data-picker-select-all]")) {
        selectAllMatching = true;
        excludedIds.clear();
        syncAllVisible();
        updateCount();
        return;
      }
      if (e.target.closest("[data-picker-deselect-all]")) {
        selectAllMatching = false;
        selectedIds.clear();
        excludedIds.clear();
        syncAllVisible();
        updateCount();
        return;
      }
      if (e.target.closest("[data-picker-attach]")) {
        doAttach(e.target.closest("[data-picker-attach]"));
      }
    });

    function doAttach(button) {
      var controls = currentControls();
      if (!controls.bank) return;
      var count = selectAllMatching ? Math.max(0, currentTotal - excludedIds.size) : selectedIds.size;
      if (count === 0) return;

      button.disabled = true;
      button.classList.add("is-loading");

      var fd = new FormData();
      fd.set("modal", "1");
      fd.set("action", "attach");
      fd.set("bank", controls.bank);
      if (selectAllMatching) {
        fd.set("select_all", "1");
        fd.set("q", controls.q || "");
        fd.set("language", controls.language || "");
        fd.set("difficulty", controls.difficulty || "");
        excludedIds.forEach(function (id) { fd.append("excluded_ids", id); });
      } else {
        selectedIds.forEach(function (id) { fd.append("question_ids", id); });
      }

      fetch(pickerUrl, {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": getCookie("csrftoken") },
        credentials: "same-origin",
        body: fd,
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data && data.success) {
            window.location.href = data.redirect_url || window.location.href;
          } else {
            button.disabled = false;
            button.classList.remove("is-loading");
            window.alert((data && data.error) || gettext("Xəta baş verdi."));
          }
        })
        .catch(function () {
          button.disabled = false;
          button.classList.remove("is-loading");
          window.alert(gettext("Şəbəkə xətası. Yenidən cəhd edin."));
        });
    }
  });
})();
