/**
 * EMSSearchableSelect — təkrar-istifadəli axtarışlı seçici (server-backed).
 *
 * `_searchable_picker.html` DOM strukturunu (chips + input + menu) idarə edir:
 *   <div class="{prefix}-ms js-{hook}">
 *     <div class="{prefix}-ms__chips"><input class="{prefix}-ms__search"></div>
 *     <div class="{prefix}-ms__menu"></div>
 *   </div>
 *
 * Xüsusiyyətlər (best-practice UX):
 *   • Server-side axtarış — DEBOUNCE (250ms), heç vaxt bütün datanı yükləmir.
 *   • LAZY / infinite-scroll səhifələmə (offset/limit + has_more) — menyu aşağı
 *     sürüşəndə növbəti səhifə gətirilir.
 *   • single / multi seçim (chip-lərlə). single-də seçim əvəzlənir.
 *   • KASKAD (dependency): kafedra fakültədən asılıdır — valideyn dəyişəndə
 *     `?<dependParam>=<parentValue>` sorğuya əlavə olunur, uşaq seçim təmizlənir.
 *   • Kəsilmə-önləyən (collision-aware) FIXED yerləşdirmə — dropdown heç vaxt
 *     ekrandan/overflow konteynerdən kənara çıxmır (aşağıda yer yoxsa yuxarı açır).
 *
 * Prefiks-agnostikdir: chips/opt/chip class-larını mövcud `input`-un class
 * adından (`{prefix}-ms__search`) çıxarır, beləcə hər səhifə öz CSS-i ilə işləyir.
 *
 * İstifadə:
 *   var pick = EMSSearchableSelect.create(root.querySelector(".js-ecs-faculty"), {
 *     url: "/exams/lookups/faculties/", multi: false, placeholder: "…",
 *     onChange: reload
 *   });
 *   var dept = EMSSearchableSelect.create(el2, {
 *     url: "…/departments/", dependParam: "faculty",
 *     getDependValue: function(){ return pick.value(); }, onChange: reload
 *   });
 *   pick.on("change", function(){ dept.reset(); });   // valideyn → uşağı sıfırla
 */
(function () {
  "use strict";

  var GAP = 6;
  var DESIRED_MAX = 300; // px — CSS max-height ilə uyğun

  function hasClippingAncestor(element) {
    var node = element.parentElement;
    while (node && node !== document.body) {
      var s = window.getComputedStyle(node);
      if (/(auto|scroll|hidden|clip)/.test(s.overflow + s.overflowY + s.overflowX)) {
        return true;
      }
      node = node.parentElement;
    }
    return false;
  }

  function create(rootEl, opts) {
    if (!rootEl) {
      return null;
    }
    if (rootEl._emsSearchable) {
      return rootEl._emsSearchable; // ikiqat init qarşısı
    }
    opts = opts || {};

    var search = rootEl.querySelector("input");
    if (!search) {
      return null;
    }
    var chips = search.parentElement;
    var menu = null;
    Array.prototype.forEach.call(rootEl.children, function (c) {
      if (c !== chips) {
        menu = c;
      }
    });
    if (!menu) {
      return null;
    }

    // Prefiks: "ecs-ms__search" → "ecs".
    var m = (search.className || "").match(/([a-z0-9]+)-ms__search/i);
    var prefix = m ? m[1] : "ms";
    var CHIP = prefix + "-chip";
    var CHIP_X = prefix + "-chip__x";
    var OPT = prefix + "-ms__opt";
    var OPT_MORE = prefix + "-ms__more";
    var OPEN = "is-open";

    var multi = !!opts.multi;
    var pageSize = opts.pageSize || 10;
    var basePlaceholder = opts.placeholder || search.getAttribute("placeholder") || "";
    var listeners = { change: [] };

    var selected = {}; // id -> text
    var offset = 0;
    var lastTerm = null;
    var hasMore = false;
    var loading = false;
    var reqSeq = 0;
    var debounceTimer = null;

    function emit() {
      listeners.change.forEach(function (cb) {
        try {
          cb();
        } catch (e) {
          /* noop */
        }
      });
      if (typeof opts.onChange === "function") {
        opts.onChange();
      }
    }

    function ids() {
      return Object.keys(selected);
    }
    function value() {
      var k = Object.keys(selected);
      return k.length ? k[0] : "";
    }

    function updatePlaceholder() {
      search.setAttribute("placeholder", Object.keys(selected).length && !multi ? "" : basePlaceholder);
    }

    function renderChips() {
      chips.querySelectorAll("." + CHIP).forEach(function (c) {
        c.remove();
      });
      Object.keys(selected).forEach(function (id) {
        var chip = document.createElement("span");
        chip.className = CHIP;
        chip.innerHTML = '<span></span><button type="button" class="' + CHIP_X + '">×</button>';
        chip.querySelector("span").textContent = selected[id];
        chip.querySelector("." + CHIP_X).addEventListener("click", function (ev) {
          ev.preventDefault();
          delete selected[id];
          renderChips();
          updatePlaceholder();
          emit();
        });
        chips.insertBefore(chip, search);
      });
      updatePlaceholder();
    }

    function buildUrl(term, off) {
      var url = opts.url + (opts.url.indexOf("?") === -1 ? "?" : "&");
      url += "q=" + encodeURIComponent(term) + "&limit=" + pageSize + "&offset=" + off;
      if (opts.dependParam && typeof opts.getDependValue === "function") {
        var dv = opts.getDependValue();
        if (dv) {
          url += "&" + encodeURIComponent(opts.dependParam) + "=" + encodeURIComponent(dv);
        }
      }
      return url;
    }

    function renderOption(o) {
      if (selected[o.id] && multi) {
        return;
      }
      var div = document.createElement("div");
      div.className = OPT;
      div.textContent = o.text;
      div.addEventListener("mousedown", function (ev) {
        ev.preventDefault();
        if (!multi) {
          selected = {};
        }
        selected[o.id] = o.text;
        renderChips();
        search.value = "";
        close();
        emit();
      });
      // "more" göstəricisindən əvvəl əlavə et.
      var moreEl = menu.querySelector("." + OPT_MORE);
      if (moreEl) {
        menu.insertBefore(div, moreEl);
      } else {
        menu.appendChild(div);
      }
    }

    function setMore(state) {
      var moreEl = menu.querySelector("." + OPT_MORE);
      if (state) {
        if (!moreEl) {
          moreEl = document.createElement("div");
          moreEl.className = OPT_MORE;
          moreEl.textContent = "…";
          menu.appendChild(moreEl);
        }
      } else if (moreEl) {
        moreEl.remove();
      }
    }

    function fetchOpts(term, append) {
      if (loading) {
        return;
      }
      loading = true;
      var seq = ++reqSeq;
      var off = append ? offset : 0;
      fetch(buildUrl(term, off), { headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then(function (r) {
          return r.ok ? r.json() : { results: [], has_more: false };
        })
        .then(function (d) {
          if (seq !== reqSeq) {
            return; // köhnəlmiş cavab
          }
          if (!append) {
            menu.innerHTML = "";
            offset = 0;
          }
          var list = d.results || [];
          list.forEach(renderOption);
          offset += list.length;
          hasMore = !!d.has_more;
          setMore(hasMore);
          if (!menu.querySelector("." + OPT)) {
            close();
          } else {
            open();
          }
        })
        .catch(function () {
          /* noop */
        })
        .finally(function () {
          loading = false;
        });
    }

    // ------- yerləşdirmə (kəsilmə-önləyən) -------
    var useFixed = null;
    function positionFixed() {
      var rect = rootEl.getBoundingClientRect();
      var vh = window.innerHeight;
      var below = vh - rect.bottom - GAP - 8;
      var above = rect.top - GAP - 8;
      var needed = Math.min(DESIRED_MAX, menu.scrollHeight || DESIRED_MAX);
      var up = below < needed && above > below;
      menu.style.position = "fixed";
      menu.style.left = rect.left + "px";
      menu.style.width = rect.width + "px";
      menu.style.right = "auto";
      if (up) {
        menu.style.top = "auto";
        menu.style.bottom = vh - rect.top + GAP + "px";
        menu.style.maxHeight = Math.max(120, Math.min(DESIRED_MAX, above)) + "px";
      } else {
        menu.style.top = rect.bottom + GAP + "px";
        menu.style.bottom = "auto";
        menu.style.maxHeight = Math.max(120, Math.min(DESIRED_MAX, below)) + "px";
      }
    }
    function clearFixed() {
      menu.style.position = "";
      menu.style.left = menu.style.right = menu.style.top = menu.style.bottom = "";
      menu.style.width = menu.style.maxHeight = "";
    }
    function onDocScroll(ev) {
      if (ev.target instanceof Node && menu.contains(ev.target)) {
        return; // menyu daxili scroll
      }
      close();
    }
    function open() {
      if (rootEl.classList.contains(OPEN)) {
        if (useFixed) {
          positionFixed();
        }
        return;
      }
      rootEl.classList.add(OPEN);
      if (useFixed === null) {
        useFixed = hasClippingAncestor(rootEl);
      }
      if (useFixed) {
        positionFixed();
        window.addEventListener("scroll", onDocScroll, true);
        window.addEventListener("resize", close);
      }
    }
    function close() {
      if (!rootEl.classList.contains(OPEN)) {
        return;
      }
      rootEl.classList.remove(OPEN);
      if (useFixed) {
        clearFixed();
        window.removeEventListener("scroll", onDocScroll, true);
        window.removeEventListener("resize", close);
      }
    }

    // ------- hadisələr -------
    search.addEventListener("input", function () {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      debounceTimer = setTimeout(function () {
        lastTerm = search.value.trim();
        fetchOpts(lastTerm, false);
      }, 250);
    });
    search.addEventListener("focus", function () {
      lastTerm = search.value.trim();
      fetchOpts(lastTerm, false);
    });
    search.addEventListener("blur", function () {
      setTimeout(close, 160);
    });
    // infinite scroll — menyu dibinə çatanda növbəti səhifə.
    menu.addEventListener("scroll", function () {
      if (hasMore && !loading && menu.scrollTop + menu.clientHeight >= menu.scrollHeight - 24) {
        fetchOpts(lastTerm || "", true);
      }
    });

    var api = {
      el: rootEl,
      ids: ids,
      value: value,
      values: ids,
      text: function () {
        var k = Object.keys(selected);
        return k.length ? selected[k[0]] : "";
      },
      clear: function () {
        selected = {};
        renderChips();
        emit();
      },
      // valideyn dəyişəndə uşağı sıfırla (event yaymadan — reload valideyndə olur)
      reset: function () {
        selected = {};
        search.value = "";
        renderChips();
        menu.innerHTML = "";
        offset = 0;
      },
      setValue: function (id, text) {
        if (!multi) {
          selected = {};
        }
        selected[id] = text;
        renderChips();
        emit();
      },
      on: function (evt, cb) {
        if (listeners[evt]) {
          listeners[evt].push(cb);
        }
      },
    };
    rootEl._emsSearchable = api;
    updatePlaceholder();
    return api;
  }

  window.EMSSearchableSelect = { create: create };
})();
