/* =========================================================================
   ems_ui/filter_bar.js — Filtr panelinin DRAFT ↔ APPLIED məntiqi
   (handoff §4 komponent 2 · §8 qayda 14)

   QAYDA
   -----
   Sahələrin dəyişməsi SORĞU GÖNDƏRMİR. Yalnız «Tətbiq et» applied vəziyyəti
   yeniləyir, URL-i `history.pushState` ilə sinxronlaşdırır və bölməni yenidən
   yükləyir. Sıralama və səhifələmə server tərəfdədir.

   NİYƏ URL?
   ---------
   Kabinet bölmələri `?section=…` üzərində işləyir; filtr dəyərləri həmin
   query string-ə əlavə olunur. Bu, (a) səhifə yenilənəndə filtrin qalmasını,
   (b) linkin paylaşıla bilməsini, (c) `section_loader.js`-in mövcud
   parametr-daşıma məntiqinə uyğunluğu təmin edir.

   MARKUP MÜQAVİLƏSİ
   -----------------
   <form class="ems-filters" data-ems-filters
         data-section="workload-center"           ← ?section= dəyəri
         data-param-prefix="wl_">                  ← parametr ad fəzası
     <div class="ems-field"><select name="wl_year" data-ems-filter>…</select></div>
     <input name="wl_q" data-ems-filter data-ems-filter-search>   ← 240ms debounce
     <button type="submit" class="ems-filters__apply">Tətbiq et</button>
     <button type="button" data-ems-filters-reset>Sıfırla</button>
   </form>

   Axtarış sahəsi debounce-dan sonra da YALNIZ `is-dirty` işarəsini qoyur —
   avtomatik sorğu göndərmir (handoff qaydası). Debounce yalnız çipləri və
   «dəyişiklik var» bildirişini yeniləmək üçündür.
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSFilterBar) {
        return;
    }

    var SEARCH_DEBOUNCE_MS = 240; // handoff: axtarış 240ms debounce
    var timers = Object.create(null);

    function fields(form) {
        return form.querySelectorAll("[data-ems-filter]");
    }

    /** Draft (canlı DOM) dəyərləri. */
    function draftValues(form) {
        var out = {};
        var nodes = fields(form);
        for (var i = 0; i < nodes.length; i += 1) {
            var el = nodes[i];
            if (!el.name) {
                continue;
            }
            var value = el.type === "checkbox" ? (el.checked ? "1" : "") : el.value;
            out[el.name] = (value || "").trim();
        }
        return out;
    }

    /** Applied (sonuncu tətbiq olunmuş) dəyərlər — sahənin `data-applied`-i. */
    function appliedValues(form) {
        var out = {};
        var nodes = fields(form);
        for (var i = 0; i < nodes.length; i += 1) {
            var el = nodes[i];
            if (el.name) {
                out[el.name] = (el.dataset.applied || "").trim();
            }
        }
        return out;
    }

    function isDirty(form) {
        var draft = draftValues(form);
        var applied = appliedValues(form);
        for (var key in draft) {
            if (Object.prototype.hasOwnProperty.call(draft, key) && draft[key] !== applied[key]) {
                return true;
            }
        }
        return false;
    }

    function markDirty(form) {
        form.classList.toggle("is-dirty", isDirty(form));
    }

    /** Applied vəziyyəti draft-dan yazır (tətbiqdən sonra). */
    function commit(form) {
        var nodes = fields(form);
        for (var i = 0; i < nodes.length; i += 1) {
            var el = nodes[i];
            if (el.name) {
                el.dataset.applied = el.type === "checkbox" ? (el.checked ? "1" : "") : el.value || "";
            }
        }
        form.classList.remove("is-dirty");
    }

    /** Draft-ı applied-ə qaytarır (Sıfırla → «tətbiq olunmuşa qayıt» DEYİL,
     *  bütün dəyərləri boşaldır — handoff «Sıfırla» semantikası). */
    function clear(form) {
        var nodes = fields(form);
        for (var i = 0; i < nodes.length; i += 1) {
            var el = nodes[i];
            if (el.type === "checkbox") {
                el.checked = false;
            } else if (el.tagName === "SELECT") {
                el.selectedIndex = 0;
            } else {
                el.value = "";
            }
            if (window.EMSBootstrapSelect && el.tagName === "SELECT") {
                window.EMSBootstrapSelect.sync(el);
            }
        }
        markDirty(form);
    }

    /** Applied dəyərlərdən naviqasiya URL-i qurur. */
    function buildUrl(form) {
        var base = form.dataset.baseUrl || window.location.pathname;
        var url = new URL(base, window.location.origin);
        // Mövcud query-ni saxla, yalnız bu panelin parametrlərini əvəz et.
        var current = new URLSearchParams(window.location.search);
        var prefix = form.dataset.paramPrefix || "";
        if (prefix) {
            var stale = [];
            current.forEach(function (_value, key) {
                if (key.indexOf(prefix) === 0) {
                    stale.push(key);
                }
            });
            stale.forEach(function (key) {
                current.delete(key);
            });
        }
        if (form.dataset.section) {
            current.set("section", form.dataset.section);
        }
        var values = draftValues(form);
        for (var key in values) {
            if (Object.prototype.hasOwnProperty.call(values, key)) {
                if (values[key]) {
                    current.set(key, values[key]);
                } else {
                    current.delete(key);
                }
            }
        }
        // Filtr dəyişəndə səhifə 1-ə qayıdır.
        current.delete((form.dataset.paramPrefix || "") + "page");
        current.delete("page");
        url.search = current.toString();
        return url.toString();
    }

    function apply(form) {
        commit(form);
        var url = buildUrl(form);
        if (window.EMSProfileLoadSection && form.dataset.section) {
            // Kabinet SPA yolu — sidebar yerində qalır, yalnız panel yenilənir.
            // İMZA: (section, sourceUrl, options) — ikinci arqument SƏTİRDİR.
            // Obyekt ötürülsəydi loader onu `options.sourceUrl` kimi saxlayır və
            // URL «[object Object]» olurdu (Mərhələ 1-də tapılıb düzəldilib).
            window.EMSProfileLoadSection(form.dataset.section, url);
        } else {
            window.location.assign(url);
        }
    }

    /* ---- Hadisələr ------------------------------------------------------- */

    window.EMSDelegate.on("submit", "form[data-ems-filters]", function (event, form) {
        event.preventDefault();
        apply(form);
    });

    window.EMSDelegate.on("click", "[data-ems-filters-reset]", function (event, btn) {
        event.preventDefault();
        var form = btn.closest("[data-ems-filters]");
        if (form) {
            clear(form);
            apply(form);
        }
    });

    window.EMSDelegate.on("change", "[data-ems-filters] [data-ems-filter]", function (event, el) {
        var form = el.closest("[data-ems-filters]");
        if (form) {
            markDirty(form);
        }
    });

    window.EMSDelegate.on("input", "[data-ems-filters] [data-ems-filter-search]", function (event, el) {
        var form = el.closest("[data-ems-filters]");
        if (!form) {
            return;
        }
        var key = form.id || "ems-filters";
        window.clearTimeout(timers[key]);
        timers[key] = window.setTimeout(function () {
            markDirty(form);
        }, SEARCH_DEBOUNCE_MS);
    });

    // Tətbiq olunmuş filtr çipinin «×»-i — həmin sahəni boşaldıb dərhal tətbiq edir.
    window.EMSDelegate.on("click", "[data-ems-filter-remove]", function (event, btn) {
        event.preventDefault();
        var name = btn.getAttribute("data-ems-filter-remove");
        var form = document.querySelector("[data-ems-filters]");
        if (!form || !name) {
            return;
        }
        var field = form.querySelector('[name="' + name + '"]');
        if (!field) {
            return;
        }
        if (field.type === "checkbox") {
            field.checked = false;
        } else if (field.tagName === "SELECT") {
            field.selectedIndex = 0;
            if (window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(field);
            }
        } else {
            field.value = "";
        }
        apply(form);
    });

    /* İlk render + hər AJAX swap: applied baseline-i sahələrdən oxu. */
    window.EMSReady(function () {
        var forms = document.querySelectorAll("[data-ems-filters]");
        for (var i = 0; i < forms.length; i += 1) {
            var form = forms[i];
            var nodes = fields(form);
            for (var j = 0; j < nodes.length; j += 1) {
                var el = nodes[j];
                if (el.name && el.dataset.applied === undefined) {
                    el.dataset.applied = el.type === "checkbox" ? (el.checked ? "1" : "") : el.value || "";
                }
            }
            markDirty(form);
        }
    });

    window.EMSFilterBar = {
        apply: apply,
        clear: clear,
        isDirty: isDirty,
        draftValues: draftValues,
        appliedValues: appliedValues,
        buildUrl: buildUrl,
        SEARCH_DEBOUNCE_MS: SEARCH_DEBOUNCE_MS,
    };
})(window, document);
