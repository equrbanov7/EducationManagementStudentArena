/* =========================================================================
   Sual bankı (imtahan) — səhifəni yenidən yükləməyən yeniləmə (sahib 2026-11-11: «burada da ləngdir»).

   NİYƏ: süzgəc, keyfiyyət çipi, səhifələmə və hər toplu əməl TAM səhifəni (baza şablonu, bütün CSS/JS,
   KaTeX, modallar) yenidən yükləyirdi. İndi eyni URL `X-QB-Partial: 1` başlığı ilə çağırılır; server
   yalnız `data-qb-live` bölgələrini (kpis · export · quality · list · danger) qaytarır və bu fayl onları
   adına görə əvəz edir. Ünvan `pushState` ilə yenilənir (geri düyməsi işləyir).

   Geri düşmə: fetch / DOMParser yoxdursa, cavab gözlənilməzdirsə və ya bölgə tapılmırsa — adi keçid.

   AJAX-SAFE: idempotent IIFE; kök `[data-qm-context="exam"]`-a BİR dinləyici (delegasiya), document-ə
   yalnız `popstate`. Yenilənmədən sonra kökdə `qb:live:updated` hadisəsi — teacher_questions_bank.js
   seçim vəziyyətini sıfırlayır.
   ========================================================================= */
(function (window, document) {
  "use strict";

  if (window.QBLive) {
    return;
  }

  var PARTIAL_HEADER = "X-QB-Partial";
  var REGIONS = ["kpis", "export", "quality", "list", "danger"];
  var controller = null;
  var seq = 0;

  function root() {
    return document.querySelector('[data-qm-context="exam"]');
  }

  function enabled() {
    return !!(root() && typeof window.fetch === "function" && typeof window.DOMParser === "function");
  }

  function region(name, scope) {
    return (scope || root() || document).querySelector('[data-qb-live="' + name + '"]');
  }

  function swapRegion(doc, name) {
    var target = region(name);
    var fresh = region(name, doc);
    if (!target || !fresh) {
      return false;
    }
    target.textContent = "";
    while (fresh.firstChild) {
      target.appendChild(document.adoptNode(fresh.firstChild));
    }
    return true;
  }

  function setBusy(on) {
    var node = root();
    if (node) {
      node.classList.toggle("eqb-page--busy", !!on);
      node.setAttribute("aria-busy", on ? "true" : "false");
    }
  }

  /* Süzgəc forması bölgələrdən kənardadır — gizli `flag` sahəsi və select-lər URL ilə uyğunlaşdırılır. */
  function syncFilterForm(url) {
    var form = document.getElementById("questionSearchForm");
    if (!form) {
      return;
    }
    var flag = url.searchParams.get("flag") || "";
    var hidden = form.querySelector('input[type="hidden"][name="flag"]');
    if (flag && !hidden) {
      hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = "flag";
      form.insertBefore(hidden, form.firstChild);
    }
    if (hidden) {
      if (flag) {
        hidden.value = flag;
      } else {
        hidden.parentNode.removeChild(hidden);
      }
    }
    ["status", "language", "sort"].forEach(function (name) {
      var select = form.querySelector('select[name="' + name + '"]');
      if (!select) {
        return;
      }
      var wanted = url.searchParams.get(name) || (name === "status" ? "all" : name === "sort" ? "newest" : "");
      if (select.value !== wanted) {
        select.value = wanted;
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.sync === "function") {
          window.EMSBootstrapSelect.sync(select);
        }
      }
    });
    var input = form.querySelector('input[name="q"]');
    var q = url.searchParams.get("q") || "";
    if (input && document.activeElement !== input && input.value !== q) {
      input.value = q;
    }
  }

  function afterSwap() {
    var node = root();
    if (!node) {
      return;
    }
    // Düsturlar (KaTeX) və layihənin select komponenti yeni DOM üçün yenidən işə düşür.
    if (window.EMSMath && typeof window.EMSMath.render === "function") {
      window.EMSMath.render(node);
    }
    if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.init === "function") {
      window.EMSBootstrapSelect.init(node);
    }
    var event;
    try {
      event = new window.CustomEvent("qb:live:updated", { bubbles: true });
    } catch (err) {
      event = document.createEvent("Event");
      event.initEvent("qb:live:updated", true, false);
    }
    node.dispatchEvent(event);
  }

  function hardNavigate(url) {
    window.location.assign(url.toString());
  }

  /* opts.push — yeni tarixçə qeydi; opts.keepUrl — ünvan dəyişmir; opts.scroll — siyahının başına sürüş. */
  function refresh(target, opts) {
    opts = opts || {};
    var url = new URL(String(target || window.location.href), window.location.href);
    if (!enabled()) {
      hardNavigate(url);
      return Promise.resolve(false);
    }
    if (controller) {
      controller.abort(); // köhnə sorğu artıq lazım deyil
    }
    controller = typeof window.AbortController === "function" ? new window.AbortController() : null;
    var mine = ++seq;
    var headers = { Accept: "text/html", "X-Requested-With": "XMLHttpRequest" };
    headers[PARTIAL_HEADER] = "1";
    setBusy(true);
    return window
      .fetch(url.toString(), {
        credentials: "same-origin",
        headers: headers,
        signal: controller ? controller.signal : undefined,
      })
      .then(function (response) {
        if (!response.ok || response.redirected) {
          throw new Error("http_" + response.status);
        }
        return response.text();
      })
      .then(function (html) {
        if (mine !== seq) {
          return false; // daha yeni sorğu var — köhnə cavab atılır
        }
        var doc = new window.DOMParser().parseFromString(html, "text/html");
        if (!swapRegion(doc, "list")) {
          throw new Error("no_region");
        }
        REGIONS.forEach(function (name) {
          if (name !== "list") {
            swapRegion(doc, name);
          }
        });
        setBusy(false);
        if (!opts.keepUrl) {
          try {
            window.history[opts.push ? "pushState" : "replaceState"]({ qbLive: true }, "", url.toString());
          } catch (err) {
            /* tarixçə API-si bağlıdır — ünvan köhnə qalır */
          }
        }
        syncFilterForm(url);
        afterSwap();
        var list = region("list");
        if (opts.scroll && list && list.firstElementChild && list.firstElementChild.getBoundingClientRect().top < 0) {
          list.firstElementChild.scrollIntoView({ block: "start" });
        }
        return true;
      })
      .catch(function (err) {
        if (err && err.name === "AbortError") {
          return false;
        }
        if (mine === seq) {
          hardNavigate(url);
        }
        return false;
      });
  }

  function showMessages(list) {
    if (!window.EMSToast || typeof window.EMSToast.show !== "function") {
      return;
    }
    (list || []).forEach(function (item) {
      if (item && item.text) {
        var level = String(item.level || "info").split(" ")[0];
        window.EMSToast.show(item.text, level === "error" ? "error" : level, level === "error" ? 8000 : undefined);
      }
    });
  }

  /* Süzgəc formasının cari dəyərlərindən URL (boş və default dəyərlər atılır; səhifə 1-ə qayıdır). */
  function urlFromFilterForm(form) {
    var url = new URL(form.getAttribute("action") || window.location.pathname, window.location.href);
    url.search = "";
    new window.FormData(form).forEach(function (value, key) {
      value = String(value == null ? "" : value).trim();
      if (!value || (key === "status" && value === "all") || (key === "sort" && value === "newest")) {
        return;
      }
      url.searchParams.set(key, value);
    });
    return url;
  }

  function onClick(event) {
    if (event.defaultPrevented || event.button > 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    var link = event.target && event.target.closest ? event.target.closest("a[href]") : null;
    if (!link || !link.closest("[data-qb-live]")) {
      return;
    }
    // Yalnız səhifələmə və keyfiyyət çipləri; yükləmə linkləri və sual modalı öz axınındadır.
    var paging = !!link.closest(".pagination-wrapper");
    if (!paging && !link.classList.contains("eqb-chip")) {
      return;
    }
    if (!enabled()) {
      return;
    }
    event.preventDefault();
    refresh(link.href, { push: true, scroll: paging });
  }

  function init() {
    var node = root();
    if (!node || node.getAttribute("data-qb-live-bound") === "1") {
      return;
    }
    node.setAttribute("data-qb-live-bound", "1");
    node.addEventListener("click", onClick);
    if (!window.__qbLivePopstate) {
      window.__qbLivePopstate = true;
      window.addEventListener("popstate", function () {
        if (root()) {
          refresh(window.location.href, { keepUrl: true });
        }
      });
    }
  }

  window.QBLive = {
    enabled: enabled,
    refresh: refresh,
    showMessages: showMessages,
    urlFromFilterForm: urlFromFilterForm,
    PARTIAL_HEADER: PARTIAL_HEADER,
  };

  if (typeof window.EMSReady === "function") window.EMSReady(init);
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})(window, document);
