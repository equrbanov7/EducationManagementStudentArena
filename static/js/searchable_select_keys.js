/**
 * EMSSearchableSelectKeys — `EMSSearchableSelect` üçün KLAVİATURA + ARIA qatı.
 *
 * Niyə ayrı fayl: `searchable_select.js` özü SOFT_CAP=600 sətir büdcəsinə
 * yaxınlaşmışdı, klaviatura idarəsi isə ayrıca, tam bağımsız bir məsuliyyətdir
 * (nə şəbəkə, nə yerləşdirmə, nə çip render-i bilir). Nüvə fayl yalnız bir
 * `attach(ctx)` çağırışı ilə bu qatı qoşur; qat yüklənməyibsə komponent
 * ƏVVƏLKİ kimi (yalnız siçanla) işləməyə davam edir — null-safe degradasiya.
 *
 * Nə əlavə edir (WAI-ARIA combobox, «manual» seçim naxışı):
 *   • ArrowDown / ArrowUp — dövrəvi gəzinti; menyu bağlıdırsa AÇIR.
 *   • Home / End          — ilk / son variant.
 *   • Enter               — vurğulanan variantı seçir.
 *   • Escape              — YALNIZ menyunu bağlayır (modal öz Escape-ini alır).
 *   • Tab                 — menyunu bağlayır, fokus təbii axır (tələ qurmur).
 *   • Backspace (boş input) — sonuncu çipi silir.
 *   • `aria-activedescendant` + `role="option"` — ekran oxuyucusu vurğulanan
 *     variantı oxuyur (fokus input-da qalır).
 *
 * ⚠️ HEÇ BİR variant avtomatik vurğulanmır. Ona görə vurğu boşkən `Enter`
 * toxunulmadan buraxılır və formanın mövcud submit/filtr davranışı POZULMUR —
 * mövcud səthlər üçün geriyə uyğunluq şərti budur.
 *
 * ctx müqaviləsi (nüvə fayl doldurur):
 *   root, input, menu   — DOM düyünləri
 *   optClass            — variant sinfi (prefiksli, məs. "acr-ms__opt")
 *   isOpen()            — menyu açıqdırmı
 *   openMenu()          — ilk səhifəni gətir və aç
 *   closeMenu()         — bağla
 *   select(o)           — variantı seç (siçanla eyni yol)
 *   loadMore()          — növbəti səhifə (lazy paging)
 *   canLoadMore()       — daha səhifə varmı və sorğu getmirmi
 *   removeLastChip()    — sonuncu seçimi sil (Backspace)
 */
(function () {
  "use strict";

  var ACTIVE = "ems-ss__opt--active";
  var DISABLED = "ems-ss__opt--disabled";

  function attach(ctx) {
    var menu = ctx.menu;
    var input = ctx.input;

    /** Menyudakı SEÇİLƏ BİLƏN variantlar (disabled/«more»/skeleton xaric). */
    function optionEls() {
      return Array.prototype.filter.call(menu.querySelectorAll("." + ctx.optClass), function (el) {
        return !el.classList.contains(DISABLED);
      });
    }

    function activeEl() {
      return menu.querySelector("." + ACTIVE);
    }

    function clearActive() {
      var prev = activeEl();
      if (prev) {
        prev.classList.remove(ACTIVE);
        prev.setAttribute("aria-selected", "false");
      }
      input.removeAttribute("aria-activedescendant");
    }

    /** Vurğunu `el`-ə keçir; `scroll !== false` olanda menyu daxilində göstər. */
    function setActive(el, scroll) {
      if (!el) {
        clearActive();
        return;
      }
      if (activeEl() === el) {
        return;
      }
      clearActive();
      el.classList.add(ACTIVE);
      el.setAttribute("aria-selected", "true");
      input.setAttribute("aria-activedescendant", el.id);
      if (scroll === false) {
        return;
      }
      // `scrollIntoView` SƏHİFƏNİ də sürüşdürə bilər (menyu `fixed` olanda
      // dropdown-un özünü ekrandan qaçırardı) — ona görə yalnız menyu daxilində.
      var top = el.offsetTop;
      var bottom = top + el.offsetHeight;
      if (top < menu.scrollTop) {
        menu.scrollTop = top;
      } else if (bottom > menu.scrollTop + menu.clientHeight) {
        menu.scrollTop = bottom - menu.clientHeight;
      }
    }

    /** Vurğunu `delta` qədər sürüşdür (dövrəvi). Sona yaxınlaşanda səhifələ. */
    function moveActive(delta) {
      var list = optionEls();
      if (!list.length) {
        return;
      }
      var index = list.indexOf(activeEl());
      var next = index === -1 ? (delta > 0 ? 0 : list.length - 1) : (index + delta + list.length) % list.length;
      setActive(list[next]);
      // Klaviatura istifadəçisi də lazy səhifələməyə çatsın: siyahının dibinə
      // yaxınlaşanda növbəti səhifəni gətir (siçanda bunu menyu `scroll`-u edir).
      if (next >= list.length - 2 && ctx.canLoadMore()) {
        ctx.loadMore();
      }
    }

    input.addEventListener("keydown", function (ev) {
      if (ev.altKey || ev.ctrlKey || ev.metaKey) {
        return;
      }
      var key = ev.key;
      var isOpen = ctx.isOpen();
      var list;

      if (key === "ArrowDown" || key === "Down") {
        ev.preventDefault(); // kursor mətnin sonuna atılmasın
        if (isOpen) {
          moveActive(1);
        } else {
          ctx.openMenu();
        }
      } else if (key === "ArrowUp" || key === "Up") {
        ev.preventDefault();
        if (isOpen) {
          moveActive(-1);
        } else {
          ctx.openMenu();
        }
      } else if (key === "Home" || key === "End") {
        if (!isOpen) {
          return; // mətn içində Home/End normal işləsin
        }
        list = optionEls();
        if (!list.length) {
          return;
        }
        ev.preventDefault();
        setActive(key === "Home" ? list[0] : list[list.length - 1]);
      } else if (key === "Enter") {
        var current = isOpen ? activeEl() : null;
        if (current && current._emsOpt) {
          ev.preventDefault(); // formu göndərmə — variant seçilir
          ctx.select(current._emsOpt);
        }
        // Vurğu boşdursa hadisə TOXUNULMAZ qalır (mövcud submit davranışı).
      } else if (key === "Escape" || key === "Esc") {
        // Menyu açıqdırsa Escape yalnız menyunu bağlasın; bağlıdırsa hadisə
        // sərbəst qalxsın ki, modal öz Escape-ini ala bilsin.
        if (isOpen) {
          ev.preventDefault();
          ev.stopPropagation();
          ctx.closeMenu();
        }
      } else if (key === "Tab") {
        ctx.closeMenu(); // fokus çıxır — menyu asılı qalmasın
      } else if (key === "Backspace" && !input.value) {
        // Boş input-da Backspace sonuncu çipi silir (çoxseçimin standart
        // davranışı). Input dolu olanda toxunmur — adi mətn silinməsi.
        ctx.removeLastChip();
      }
    });

    return { clearActive: clearActive, setActive: setActive };
  }

  window.EMSSearchableSelectKeys = { attach: attach };
})();
