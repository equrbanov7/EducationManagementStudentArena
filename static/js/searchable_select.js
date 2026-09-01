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
 *   • OPT-IN UX əlavələri (bunları göndərməyən mövcud səthlərdə davranış EYNİDİR):
 *       – server nəticəsində `disabled: true` (+ `hint`) → variant GÖRÜNÜR, amma
 *         seçilmir və səbəbi yanında yazılır («onsuz da bu jurnaldadır»);
 *       – `opts.emptyText` → nəticə yoxdursa mənalı boş vəziyyət mətni;
 *       – `opts.skeleton: true` → ilk səhifə gələnə qədər skeleton sətirlər.
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
  var uid = 0; // `aria-activedescendant` üçün instansiya-unikal id kökü

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
    // Vahid komponent üslubu (static/css/searchable_select.css) tək-seçim və
    // çox-seçimi FƏRQLİ göstərir: tək-seçimdə çip «dəyər» kimi (bordersiz,
    // sətir sınmadan), çox-seçimdə isə həb-token kimi. Rejimi yalnız JS bilir,
    // ona görə sinfi burada qoyuruq.
    rootEl.classList.add("ems-ss", multi ? "ems-ss--multi" : "ems-ss--single");
    var pageSize = opts.pageSize || 10;
    var basePlaceholder = opts.placeholder || search.getAttribute("placeholder") || "";
    var listeners = { change: [] };

    // KLAVİATURA: `aria-activedescendant` real id tələb edir, ona görə hər
    // instansiyaya unikal kök, hər varianta artan nömrə verilir. Bu bəyan
    // A11Y blokundan ƏVVƏL olmalıdır: `var` qaldırılsa da TƏYİNAT qaldırılmır,
    // ona görə aşağıda qalsaydı `menu.id` hərfi «undefined-menu» olardı və eyni
    // səhifədəki İKİ komponent eyni DOM id-sini paylaşardı.
    var instanceId = "ems-ss-" + ++uid;

    // ── A11Y karkası (combobox + listbox) ────────────────────────────────────
    // Bunlar YALNIZ atribut əlavə edir; heç bir CSS/JS seçicisi role/aria-ya
    // görə işləmir, ona görə mövcud səthlərin davranışı dəyişmir.
    if (!menu.id) {
      menu.id = instanceId + "-menu";
    }
    menu.setAttribute("role", "listbox");
    if (multi) {
      menu.setAttribute("aria-multiselectable", "true");
    }
    search.setAttribute("role", "combobox");
    search.setAttribute("aria-autocomplete", "list");
    search.setAttribute("aria-haspopup", "listbox");
    search.setAttribute("aria-expanded", "false");
    search.setAttribute("aria-controls", menu.id);

    var selected = {}; // id -> text
    var optSeq = 0;
    var offset = 0;
    var lastTerm = null;
    var hasMore = false;
    var loading = false;
    var pending = null; // sorğu gedərkən yazılan son axtarış (trailing re-fetch)
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
      var hasValue = !!Object.keys(selected).length;
      search.setAttribute("placeholder", hasValue && !multi ? "" : basePlaceholder);
      // Seçim varkən input yer tələb etməsin — yoxsa çip + input çərçivəyə
      // sığmayıb sətri sındırır (bax searchable_select.css: `.has-value`).
      rootEl.classList.toggle("has-value", hasValue);
    }

    function renderChips() {
      chips.querySelectorAll("." + CHIP).forEach(function (c) {
        c.remove();
      });
      Object.keys(selected).forEach(function (id) {
        var chip = document.createElement("span");
        chip.className = "ems-ss__chip " + CHIP;
        chip.innerHTML = '<span></span><button type="button" class="ems-ss__chip-x ' + CHIP_X + '">×</button>';
        chip.querySelector("span").textContent = selected[id];
        chip.setAttribute("title", selected[id]);
        // «×» simvolu ekran oxuyucusuna heç nə demir. Etiket mətni çağırandan
        // gəlir (tərcümə şablonda olur); verilməyibsə seçimin öz adı işlənir.
        var removeLabel = opts.removeLabel ? opts.removeLabel.replace("%s", selected[id]) : selected[id];
        chip.querySelector("." + CHIP_X).setAttribute("aria-label", removeLabel);
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
      div.className = "ems-ss__opt " + OPT;
      div.setAttribute("role", "option");
      div.setAttribute("aria-selected", "false");
      div.id = instanceId + "-opt-" + ++optSeq;
      // Seçilə bilməyən variant: server `disabled: true` göndərəndə element
      // GÖRÜNÜR, amma seçilmir və SƏBƏBİ (`hint`) yanında yazılır — istifadəçi
      // «axtardığım niyə yoxdur?» sualı ilə qalmasın. Bayraq opsionaldır:
      // göndərməyən mövcud səthlər üçün davranış dəyişmir.
      if (o.disabled) {
        div.className += " ems-ss__opt--disabled";
        div.setAttribute("aria-disabled", "true");
        var label = document.createElement("span");
        label.className = "ems-ss__opt-label";
        label.textContent = o.text;
        div.appendChild(label);
        if (o.hint) {
          var hint = document.createElement("span");
          hint.className = "ems-ss__opt-hint";
          hint.textContent = o.hint;
          div.appendChild(hint);
        }
        div.addEventListener("mousedown", function (ev) {
          ev.preventDefault(); // fokus getməsin, seçim də olmasın
        });
        insertOption(div);
        return;
      }
      div.textContent = o.text;
      // Klaviatura `Enter`-i eyni yoldan getsin deyə variant öz datasını
      // elementdə saxlayır — siçan və klaviatura ARASINDA davranış fərqi olmur.
      div._emsOpt = o;
      div.addEventListener("mousedown", function (ev) {
        ev.preventDefault();
        selectOption(o);
      });
      div.addEventListener("mousemove", function () {
        // Siçan gəzdirəndə klaviatura vurğusu ora keçsin — yoxsa iki ayrı
        // «aktiv» görünüş (hover + klaviatura vurğusu) eyni anda görünərdi.
        if (keys) {
          keys.setActive(div, false);
        }
      });
      insertOption(div);
    }

    /** Seçim — siçan mousedown-u və klaviatura Enter-i üçün TƏK yol. */
    function selectOption(o) {
      if (!multi) {
        selected = {};
      }
      selected[o.id] = o.text;
      renderChips();
      search.value = "";
      close();
      emit();
    }

    // ------- klaviatura + ARIA (ayrı modul) -------
    // Qat `static/js/searchable_select_keys.js`-dədir. Yüklənməyibsə komponent
    // ƏVVƏLKİ kimi (yalnız siçanla) işləyir — heç nə sınmır.
    var keys = null;

    /** Menyu bağlıdırsa aç (fokusdakı kimi ilk səhifəni gətir). */
    function openFromKeyboard() {
      lastTerm = search.value.trim();
      fetchOpts(lastTerm, false);
    }

    /** Boş input-da Backspace: sonuncu seçimi sil. */
    function removeLastChip() {
      var chosen = Object.keys(selected);
      if (!chosen.length) {
        return;
      }
      delete selected[chosen[chosen.length - 1]];
      renderChips();
      emit();
    }

    /** Vurğunu təmizlə — qat yoxdursa no-op. */
    function clearActive() {
      if (keys) {
        keys.clearActive();
      }
    }

    /** Variantı "more" göstəricisindən ƏVVƏL yerləşdir. */
    function insertOption(div) {
      var moreEl = menu.querySelector("." + OPT_MORE);
      if (moreEl) {
        menu.insertBefore(div, moreEl);
      } else {
        menu.appendChild(div);
      }
    }

    /** Yüklənmə hissi: skeleton sətirlər (yalnız İLK səhifə üçün). */
    function setSkeleton(on) {
      if (!opts.skeleton) {
        return;
      }
      var existing = menu.querySelector(".ems-ss__skeleton");
      if (!on) {
        if (existing) {
          existing.remove();
        }
        return;
      }
      if (existing) {
        return;
      }
      var box = document.createElement("div");
      box.className = "ems-ss__skeleton";
      box.setAttribute("aria-hidden", "true");
      for (var i = 0; i < 3; i++) {
        var line = document.createElement("div");
        line.className = "skeleton skeleton-line ems-ss__skeleton-line";
        box.appendChild(line);
      }
      menu.appendChild(box);
      open();
    }

    /** Nəticə yoxdursa mənalı boş vəziyyət (opt-in: `opts.emptyText`). */
    function setEmpty(on) {
      var existing = menu.querySelector(".ems-ss__empty");
      if (!on || !opts.emptyText) {
        if (existing) {
          existing.remove();
        }
        return;
      }
      if (existing) {
        return;
      }
      var box = document.createElement("div");
      box.className = "ems-ss__empty";
      box.textContent = opts.emptyText;
      menu.appendChild(box);
    }

    function setMore(state) {
      var moreEl = menu.querySelector("." + OPT_MORE);
      if (state) {
        if (!moreEl) {
          moreEl = document.createElement("div");
          moreEl.className = "ems-ss__more " + OPT_MORE;
          moreEl.textContent = "…";
          menu.appendChild(moreEl);
        }
      } else if (moreEl) {
        moreEl.remove();
      }
    }

    function fetchOpts(term, append) {
      if (loading) {
        // Sorğu getdiyi an yazılan axtarışı ATMA — növbəyə al və cari sorğu
        // bitəndə işə sal. Əvvəllər belə keystroke səssizcə itirdi: istifadəçi
        // ad yazırdı, siyahı isə KÖHNƏ nəticədə donub qalırdı (yalnız ikinci
        // dəfə yazanda düzəlirdi).
        pending = { term: term, append: append };
        return;
      }
      loading = true;
      var seq = ++reqSeq;
      var off = append ? offset : 0;
      if (!append) {
        setEmpty(false);
        setSkeleton(true);
      }
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
            // Vurğulanan element indi silindi — `aria-activedescendant` ölü
            // id-yə işarə etməsin (ekran oxuyucusu susardı).
            clearActive();
            offset = 0;
          }
          setSkeleton(false);
          var list = d.results || [];
          list.forEach(renderOption);
          offset += list.length;
          hasMore = !!d.has_more;
          setMore(hasMore);
          if (!menu.querySelector("." + OPT)) {
            // Nəticə yoxdur: `emptyText` verilibsə mənalı boş vəziyyət göstər,
            // verilməyibsə köhnə davranış (menyunu bağla) saxlanılır.
            setEmpty(true);
            if (menu.querySelector(".ems-ss__empty")) {
              open();
            } else {
              close();
            }
          } else {
            open();
          }
        })
        .catch(function () {
          setSkeleton(false);
        })
        .finally(function () {
          loading = false;
          if (pending) {
            var queued = pending;
            pending = null; // rekursiya döngəyə düşməsin
            fetchOpts(queued.term, queued.append);
          }
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
    // Kənara klik → BAĞLA. Əvvəlki `blur` + setTimeout(160) yanaşması klaviatura
    // qatı gələndə itmişdi və menyu açıq qalırdı (iki picker eyni anda açılıb
    // üst-üstə düşürdü). `pointerdown` daha düzgündür: fokusun hara keçdiyindən
    // asılı deyil, capture fazasında işləyir və Tab/Escape məntiqinə toxunmur.
    function onDocPointerDown(ev) {
      if (ev.target instanceof Node && rootEl.contains(ev.target)) {
        return; // öz içimiz (input, çip «×», variant) — bağlamırıq
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
      search.setAttribute("aria-expanded", "true");
      document.addEventListener("pointerdown", onDocPointerDown, true);
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
      search.setAttribute("aria-expanded", "false");
      document.removeEventListener("pointerdown", onDocPointerDown, true);
      clearActive();
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
    // Klaviatura qatını qoş: ArrowUp/Down/Home/End/Enter/Escape/Tab/Backspace.
    if (window.EMSSearchableSelectKeys) {
      keys = window.EMSSearchableSelectKeys.attach({
        root: rootEl,
        input: search,
        menu: menu,
        optClass: OPT,
        isOpen: function () {
          return rootEl.classList.contains(OPEN);
        },
        openMenu: openFromKeyboard,
        closeMenu: close,
        select: selectOption,
        loadMore: function () {
          fetchOpts(lastTerm || "", true);
        },
        canLoadMore: function () {
          return hasMore && !loading;
        },
        removeLastChip: removeLastChip,
      });
    }
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
      // Kaskadda mərhələ dəyişəndə mətn yenilənsin: valideyn seçilməmişkən
      // «Əvvəlcə qrup seçin…», seçildikdən sonra «Tələbə axtarın…». Placeholder
      // statik qalsaydı, qrup seçiləndən sonra da köhnə (yanlış) göstəriş qalırdı.
      setPlaceholder: function (text) {
        basePlaceholder = text || "";
        updatePlaceholder();
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
