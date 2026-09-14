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
                resetSelect(el);
            } else {
                el.value = "";
            }
            if (window.EMSBootstrapSelect && el.tagName === "SELECT") {
                window.EMSBootstrapSelect.sync(el);
            }
        }
        markDirty(form);
    }

    /** Select-i DEFOLTA qaytarır: `data-ems-default` varsa ora, yoxsa ilk seçimə. */
    function resetSelect(select) {
        var preferred = select.getAttribute("data-ems-default");
        if (preferred !== null) {
            var found = false;
            for (var i = 0; i < select.options.length; i += 1) {
                if (select.options[i].value === preferred) {
                    found = true;
                    break;
                }
            }
            if (found) {
                select.value = preferred;
                return;
            }
        }
        select.selectedIndex = 0;
    }

    /** Formanın SAHİBİ olduğu parametr adları — yalnız bunlar təmizlənə bilər.
     *
     *  ⚠️ REQRESSİYA QAPISI (sahib, 2026-09-10): «Registrar (kataloq)» →
     *  «Tələbə təyinatları» tabında ada görə axtaranda ekran BİRİNCİ taba
     *  («İxtisaslar») atırdı. Səbəb: bu funksiya əvvəllər prefiksli BÜTÜN
     *  parametrləri «köhnəlmiş» sayıb silirdi, `rc_tab` da prefikslidir —
     *  yəni aktiv tab URL-dən düşürdü və server defolt tabı qaytarırdı.
     *  Eyni tələ `wc_view` / `wc_tab` / `th_tab` / sıralama açarlarında da
     *  vardı. Qayda: forma YALNIZ öz sahələrini idarə edir; panelin vəziyyət
     *  parametrləri (tab, görünüş, sıralama) TOXUNULMAZ qalır. */
    function ownedNames(form) {
        var owned = Object.create(null);
        var nodes = fields(form);
        for (var i = 0; i < nodes.length; i += 1) {
            if (nodes[i].name) {
                owned[nodes[i].name] = true;
            }
        }
        return owned;
    }

    /** Formanın sahibi olduğu (və artıq render olunmayan qardaş) süzgəcləri atır. */
    function dropOwnedParams(current, form) {
        var owned = ownedNames(form);
        var stale = [];
        current.forEach(function (_value, key) {
            if (owned[key]) {
                stale.push(key);
            }
        });
        stale.forEach(function (key) {
            current.delete(key);
        });
        current.delete((form.dataset.paramPrefix || "") + "page");
        current.delete("page");
    }

    /** Applied dəyərlərdən naviqasiya URL-i qurur. */
    function buildUrl(form) {
        var base = form.dataset.baseUrl || window.location.pathname;
        var url = new URL(base, window.location.origin);
        // Mövcud query-ni saxla, yalnız bu panelin ÖZ sahələrini əvəz et.
        var current = new URLSearchParams(window.location.search);
        dropOwnedParams(current, form);
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
        // Filtr dəyişəndə səhifə 1-ə qayıdır (`dropOwnedParams` səhifəni onsuz
        // da atdı; boş dəyər yazılan sahə yuxarıda silinir).
        url.search = current.toString();
        return url.toString();
    }

    /* ---- AVTO rejim (`data-ems-filters-auto`) ---------------------------
       «Tətbiq et» düyməsi yoxdur: select dəyişən kimi, axtarış isə debounce-dan
       sonra tətbiq olunur. Panel SPA ilə yenidən yükləndiyi üçün (a) cədvəl
       yerində skeleton-a çevrilir, (b) axtarış sahəsinin fokusu və kursor
       mövqeyi swap-dan sonra bərpa olunur, (c) yükləmə gedərkən yazılmış
       hərflər itmir — yeni panel gələndə fərq varsa təkrar tətbiq olunur. */
    var AUTO_SEARCH_DEBOUNCE_MS = 350;
    var autoFocus = null; // {section, name, value, caret}
    // Bərpa YALNIZ bizim avto-tətbiqin yaratdığı yükləmədən sonra işləyir —
    // başqa bölmədən sidebar ilə qayıdanda köhnə axtarış dəyəri geri yazılmasın.
    var autoPending = false;

    function isAuto(form) {
        return form.getAttribute("data-ems-filters-auto") === "1";
    }

    function skeletonFor(form) {
        var host = form.closest("[data-tof-root]") || form.parentElement || document;
        // Cədvəlsiz ekranlar (məs. gün-gün kartlar) hədəfi `data-ems-filter-target`
        // ilə göstərir — məzmun shimmer kartlarla əvəzlənir.
        var targets = host.querySelectorAll("[data-ems-filter-target]");
        for (var t = 0; t < targets.length; t += 1) {
            var cards = "";
            for (var k = 0; k < 3; k += 1) {
                cards += '<div class="ems-skelcard" aria-hidden="true">'
                    + '<span class="skeleton skeleton-line skeleton-line--lg"></span>'
                    + '<span class="skeleton skeleton-line"></span>'
                    + '<span class="skeleton skeleton-line skeleton-line--sm"></span>'
                    + "</div>";
            }
            targets[t].setAttribute("aria-busy", "true");
            targets[t].innerHTML = '<div class="ems-filter-skeleton">' + cards + "</div>";
        }
        var wrap = host.querySelector(".ems-tablewrap");
        if (wrap) {
            wrap.setAttribute("aria-busy", "true");
            wrap.classList.add("is-refreshing");
            var table = wrap.querySelector("table");
            var tbody = table ? table.querySelector("tbody") : null;
            if (tbody) {
                var columns = table.querySelectorAll("thead th").length || 4;
                var rows = Math.min(Math.max(tbody.querySelectorAll("tr").length, 4), 8);
                var html = "";
                for (var r = 0; r < rows; r += 1) {
                    html += '<tr class="ems-table__skeleton-row" aria-hidden="true">';
                    for (var c = 0; c < columns; c += 1) {
                        html += '<td><span class="skeleton skeleton-line' + (c === 0 ? " skeleton-line--lg" : " skeleton-line--sm") + '"></span></td>';
                    }
                    html += "</tr>";
                }
                tbody.innerHTML = html;
            }
        }
        var tiles = host.querySelectorAll(".ems-kpi");
        for (var i = 0; i < tiles.length; i += 1) {
            tiles[i].classList.add("ems-kpi--skeleton");
        }
        var count = form.querySelector(".ems-filters__count");
        if (count) {
            count.classList.add("is-refreshing");
        }
    }

    function rememberFocus(form) {
        var active = document.activeElement;
        if (!active || !form.contains(active) || !active.name || !active.hasAttribute("data-ems-filter-search")) {
            autoFocus = null;
            return;
        }
        autoFocus = {
            section: form.dataset.section || "",
            name: active.name,
            value: active.value || "",
            caret: typeof active.selectionStart === "number" ? active.selectionStart : (active.value || "").length,
        };
    }

    function restoreFocus(panel) {
        if (!autoPending || !autoFocus) {
            return;
        }
        autoPending = false;
        var saved = autoFocus;
        autoFocus = null;
        var form = (panel || document).querySelector('[data-ems-filters-auto="1"]');
        if (!form || (saved.section && form.dataset.section !== saved.section)) {
            return;
        }
        var field = form.querySelector('[name="' + saved.name + '"]');
        if (!field) {
            return;
        }
        var rendered = field.value || "";
        try {
            field.focus({ preventScroll: true });
        } catch (err) {
            field.focus();
        }
        if (rendered !== saved.value) {
            // Yükləmə gedərkən istifadəçi yazmağa davam edib — itirmirik.
            field.value = saved.value;
            try {
                field.setSelectionRange(saved.value.length, saved.value.length);
            } catch (err) { /* type=search bəzi brauzerlərdə dəstəkləmir */ }
            scheduleAuto(form, field);
            return;
        }
        var caret = Math.min(saved.caret, rendered.length);
        try {
            field.setSelectionRange(caret, caret);
        } catch (err) { /* ignore */ }
    }

    function scheduleAuto(form, field) {
        var key = "auto:" + (form.dataset.section || form.id || "ems-filters");
        window.clearTimeout(timers[key]);
        timers[key] = window.setTimeout(function () {
            if (!document.contains(form)) {
                return;
            }
            if (!isDirty(form)) {
                return;
            }
            apply(form);
        }, AUTO_SEARCH_DEBOUNCE_MS);
        if (field) {
            autoFocus = {
                section: form.dataset.section || "",
                name: field.name,
                value: field.value || "",
                caret: typeof field.selectionStart === "number" ? field.selectionStart : (field.value || "").length,
            };
        }
    }

    function apply(form) {
        if (isAuto(form)) {
            rememberFocus(form);
            skeletonFor(form);
            autoPending = true;
        }
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

    /** Avto rejimdə «Sıfırla» = SERVER DEFOLTLARI: panelin bütün prefiksli
     *  parametrləri URL-dən atılır (boş dəyər = default qaydası). Draft-ı
     *  index-0 ilə doldurub göndərmək default olmayan seçimi (məs. ən köhnə ili)
     *  URL-ə yazardı — «Sıfırla işləmir» şikayətinin kökü bu idi. */
    function resetToDefaults(form) {
        rememberFocus(form);
        autoFocus = null;
        skeletonFor(form);
        autoPending = true;
        var base = form.dataset.baseUrl || window.location.pathname;
        var url = new URL(base, window.location.origin);
        var current = new URLSearchParams(window.location.search);
        // «Sıfırla» SÜZGƏCLƏRİ sıfırlayır, panelin vəziyyətini yox: aktiv tab /
        // görünüş yerində qalır (yuxarıdakı `ownedNames` şərhinə bax).
        dropOwnedParams(current, form);
        if (form.dataset.section) {
            current.set("section", form.dataset.section);
        }
        url.search = current.toString();
        var target = url.toString();
        if (window.EMSProfileLoadSection && form.dataset.section) {
            window.EMSProfileLoadSection(form.dataset.section, target);
        } else {
            window.location.assign(target);
        }
    }

    window.EMSDelegate.on("click", "[data-ems-filters-reset]", function (event, btn) {
        event.preventDefault();
        var form = btn.closest("[data-ems-filters]");
        if (!form) {
            return;
        }
        if (isAuto(form)) {
            resetToDefaults(form);
            return;
        }
        clear(form);
        apply(form);
    });

    // Tarix sahəsi dəyişəndə bağlı «dövr» select-i «seçilmiş aralıq» olur.
    window.EMSDelegate.on("change", "[data-ems-filters] [data-ems-range-select]", function (event, el) {
        var form = el.closest("[data-ems-filters]");
        var name = el.getAttribute("data-ems-range-select");
        if (!form || !name) {
            return;
        }
        var select = form.querySelector('select[name="' + name + '"]');
        var custom = el.getAttribute("data-ems-range-custom") || "custom";
        if (select && select.value !== custom) {
            select.value = custom;
            if (window.EMSBootstrapSelect) {
                window.EMSBootstrapSelect.sync(select);
            }
        }
    });

    window.EMSDelegate.on("change", "[data-ems-filters] [data-ems-filter]", function (event, el) {
        var form = el.closest("[data-ems-filters]");
        if (!form) {
            return;
        }
        markDirty(form);
        // Avto rejimdə select/checkbox dəyişən kimi tətbiq olunur; axtarış
        // sahəsinin `change`-i (blur/Enter) isə debounce-u gözləmədən göndərir.
        if (isAuto(form) && isDirty(form)) {
            apply(form);
        }
    });

    window.EMSDelegate.on("input", "[data-ems-filters] [data-ems-filter-search]", function (event, el) {
        var form = el.closest("[data-ems-filters]");
        if (!form) {
            return;
        }
        if (isAuto(form)) {
            markDirty(form);
            scheduleAuto(form, el);
            return;
        }
        var key = form.id || "ems-filters";
        window.clearTimeout(timers[key]);
        timers[key] = window.setTimeout(function () {
            markDirty(form);
        }, SEARCH_DEBOUNCE_MS);
    });

    // Avto rejimdə Enter — debounce-u gözləmədən dərhal tətbiq (submit onsuz da apply edir).
    document.addEventListener("profile:section:loaded", function (event) {
        var panel = event && event.detail ? event.detail.panel : null;
        restoreFocus(panel);
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
            resetSelect(field);
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
        ownedNames: ownedNames,
        clear: clear,
        isDirty: isDirty,
        draftValues: draftValues,
        appliedValues: appliedValues,
        buildUrl: buildUrl,
        SEARCH_DEBOUNCE_MS: SEARCH_DEBOUNCE_MS,
        AUTO_SEARCH_DEBOUNCE_MS: AUTO_SEARCH_DEBOUNCE_MS,
    };
})(window, document);
