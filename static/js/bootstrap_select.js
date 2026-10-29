/*
 * static/js/bootstrap_select.js — stilli tək seçim (`[data-bootstrap-select]`).
 *
 * TƏNBƏL MENYU (PERF-2 H3, 2026-10-17): init yalnız toggle-u qurur; variant düymələri menyu İLK açılanda
 * (`show.bs.dropdown`, klaviatura ilə açılış da) və ya toggle fokus alanda qurulur, kliklər BİR delegə
 * dinləyici ilə tutulur. `refresh()` bağlı menyunu «köhnəlmiş» işarələyir (növbəti açılışda native
 * `<select>`-dən yenidən qurulur), açıq menyunu sorğu saxlanaraq dərhal yeniləyir. Native `<select>`,
 * `change`, `data-*` və `refresh/sync/init` API-si dəyişməyib; `api.build()` menyunu dərhal qurur.
 *
 * MENYU-DAXİLİ AXTARIŞ (sahib 2026-10-27): DEFAULT açıqdır — görünən variant (boş «Seçilməyib» xaric)
 * `SEARCH_MIN_OPTIONS`-dan azdırsa göstərilmir; `data-live-search="true"` → həmişə, `"false"` → heç vaxt.
 * Qərar hər menyu qurulanda verilir. Süzgəc EMSSearch (ə/e, ı/i, ö/o, ü/u, ş/s, ç/c, ğ/g, registr) ilə;
 * açılanda fokus DƏRHAL axtarışa keçir, bağlananda sorğu təmizlənir; toggle və ya variant üzərində
 * yazılan hərf axtarışa düşür; hər süzgəcdən sonra siyahı başa sürüşür.
 *
 * 2026-10-29 («Yük bölgüsü»: «yazıram gəlmir, scroll edəndə görürəm»): variantlar `refresh()`-siz dəyişsə də
 * native select MutationObserver ilə izlənir; sonradan DOM-a düşən select-lər də belə qoşulur. */
(function () {
    var SEARCH_MIN_OPTIONS = 6;

    function gettext(text) {
        return typeof window.gettext === "function" ? window.gettext(text) : text;
    }

    function normalizeValue(value) {
        return value === null || value === undefined ? "" : String(value);
    }

    // Sorğu və variant eyni qaydada: NFC («g+˘» → «ğ»), görünməz simvollar atılır, kiril «ә/Ә» → «ə/Ə».
    function searchable(text) {
        var value = String(text == null ? "" : text);
        value = value.normalize ? value.normalize("NFC") : value;
        return value.replace(/[\u00AD\u200B-\u200F\u2060\uFEFF]/g, "").replace(/\u04D9/g, "ə").replace(/\u04D8/g, "Ə");
    }

    // Toxunma ekranı: axtarış fokusda ikən virtual klaviatura səhifəni sürüşdürür — menyu bağlanmasın.
    function keepOpenOnViewportChange(input) {
        var coarse = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
        return Boolean(coarse && input && document.activeElement === input);
    }

    function positionMenuFixed(toggle, menu) {
        var rect = toggle.getBoundingClientRect();
        var viewportHeight = window.innerHeight;
        var gap = 6;
        var desiredMax = 320; // CSS max-height (20rem) ilə uyğun
        var spaceBelow = viewportHeight - rect.bottom - gap - 8;
        var spaceAbove = rect.top - gap - 8;
        // Menyunun TAM hündürlüyü aşağıda sığmırsa və yuxarıda daha çox yer
        // varsa — yuxarı aç. Beləcə cədvəlin aşağı sətirlərində bütün seçimlər
        // (məs. 0–10 kollokvium balları) SCROLL-suz görünür.
        var menuH = menu.scrollHeight || 300;
        var needed = Math.min(desiredMax, menuH);
        var openUp = spaceBelow < needed && spaceAbove > spaceBelow;

        // `data-menu-min-width` (ixtiyari, px): dar düymə + geniş menyu (məs. telefon ölkə seçicisi).
        var holder = toggle.closest(".bootstrap-single-select");
        var minWidth = holder ? Number(holder.getAttribute("data-menu-min-width")) || 0 : 0;
        var menuWidth = Math.min(Math.max(rect.width, minWidth), window.innerWidth - 16);
        var menuLeft = Math.max(8, Math.min(rect.left, window.innerWidth - menuWidth - 8));

        menu.classList.add("is-fixed");
        menu.style.position = "fixed";
        menu.style.left = (minWidth ? menuLeft : rect.left) + "px";
        menu.style.width = (minWidth ? menuWidth : rect.width) + "px";
        menu.style.right = "auto";
        menu.style.transform = "none";

        if (openUp) {
            menu.style.top = "auto";
            menu.style.bottom = viewportHeight - rect.top + gap + "px";
            menu.style.maxHeight = Math.max(120, Math.min(desiredMax, spaceAbove)) + "px";
        } else {
            menu.style.top = rect.bottom + gap + "px";
            menu.style.bottom = "auto";
            menu.style.maxHeight = Math.max(120, Math.min(desiredMax, spaceBelow)) + "px";
        }
    }

    function resetMenuPosition(menu) {
        menu.classList.remove("is-fixed");
        menu.style.position = "";
        menu.style.left = "";
        menu.style.right = "";
        menu.style.top = "";
        menu.style.bottom = "";
        menu.style.width = "";
        menu.style.maxHeight = "";
        menu.style.transform = "";
    }

    function enhanceBootstrapSelect(select) {
        if (!select) {
            return null;
        }

        if (select.multiple) {
            return null; // çoxseçim → EMSMultiSelect (yuxarıdakı qeyd)
        }

        if (select.dataset.bootstrapSelectReady === "true") {
            return select._bootstrapSelectApi || null;
        }

        var wrapper = select.closest(".bootstrap-single-select");
        if (!wrapper && select.parentNode) {
            // Django form widget-i (`{{ form.field }}`) sarğısız render olunur — sarğını
            // burada qururuq ki, `data-bootstrap-select` atributu tək başına kifayət etsin.
            wrapper = document.createElement("div");
            wrapper.className = "bootstrap-single-select bootstrap-single-select--ems";
            select.parentNode.insertBefore(wrapper, select);
            wrapper.appendChild(select);
            select.classList.add("bootstrap-single-select__native");
        }
        if (!wrapper) {
            return null;
        }

        select.dataset.bootstrapSelectReady = "true";
        select.classList.add("is-enhanced");

        var dropdown = document.createElement("div");
        dropdown.className = "dropdown bootstrap-single-select__dropdown";

        var toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "btn btn-outline-secondary dropdown-toggle bootstrap-single-select__toggle";
        toggle.setAttribute("data-bs-toggle", "dropdown");
        toggle.setAttribute("data-bs-display", "static");
        toggle.setAttribute("aria-expanded", "false");

        var label = document.createElement("span");
        label.className = "bootstrap-single-select__label-text";
        toggle.appendChild(label);

        var caret = document.createElement("span");
        caret.className = "bootstrap-single-select__caret";
        caret.innerHTML = '<i class="fas fa-chevron-down" aria-hidden="true"></i>';
        toggle.appendChild(caret);

        var menu = document.createElement("div");
        menu.className = "dropdown-menu bootstrap-single-select__menu";

        // Daxili axtarış: menyunun başında yapışqan axtarış sahəsi, variantlar
        // müştəri tərəfində süzülür — seçim yenə native `<select>`-ə yazılır, yəni
        // forma/filtr müqaviləsi dəyişmir. Elementlər TƏNBƏL yaradılır (ilk lazım
        // olanda), göstərilib-göstərilməməsi isə hər `buildMenu()`-da qərarlaşır.
        var searchWrap = null;
        var searchInput = null;
        var searchEmpty = null;

        function wantsSearch() {
            var mode = select.getAttribute("data-live-search");
            if (mode === "true") {
                return true;
            }
            if (mode === "false") {
                return false;
            }
            var count = 0;
            Array.prototype.forEach.call(select.options, function (option, index) {
                if (!option.hidden && !(index === 0 && !option.value)) {
                    count += 1;
                }
            });
            return count >= SEARCH_MIN_OPTIONS;
        }

        function ensureSearch() {
            if (searchWrap) {
                return;
            }
            var placeholder = select.getAttribute("data-live-search-placeholder") || gettext("Axtar…");
            searchWrap = document.createElement("div");
            searchWrap.className = "bootstrap-single-select__search";
            searchInput = document.createElement("input");
            searchInput.type = "search";
            searchInput.className = "form-control form-control-sm bootstrap-single-select__search-input";
            searchInput.autocomplete = "off";
            searchInput.setAttribute("aria-label", placeholder);
            searchInput.placeholder = placeholder;
            searchWrap.appendChild(searchInput);
            searchEmpty = document.createElement("div");
            searchEmpty.className = "bootstrap-single-select__search-empty";
            searchEmpty.setAttribute("role", "status");
            searchEmpty.textContent = select.getAttribute("data-live-search-empty") || gettext("Uyğun nəticə yoxdur");
            searchEmpty.hidden = true;
            searchInput.addEventListener("input", applyLiveSearch);
            searchInput.addEventListener("keydown", onSearchKeydown);
        }

        function searchActive() {
            return Boolean(searchWrap && searchWrap.parentNode === menu);
        }

        dropdown.appendChild(toggle);
        dropdown.appendChild(menu);
        select.insertAdjacentElement("afterend", dropdown);

        function applyLiveSearch() {
            if (!searchActive()) {
                return;
            }
            var needle = searchable(searchInput.value).trim();
            // Kanonik az/ing qatlama + kod rejimi («234king» → «234 K ing», «Aliyev» → «Əliyev»):
            // static/js/search_fold.js (EMSSearch); yoxdursa sadə registrsiz «contains».
            var lowered = needle.toLowerCase();
            var hitTest = window.EMSSearch
                ? window.EMSSearch.matcher(needle)
                : function (text) {
                      return String(text || "").toLowerCase().indexOf(lowered) !== -1;
                  };
            var visible = 0;
            menu.querySelectorAll(".bootstrap-single-select__option").forEach(function (button) {
                // `data-search` (ixtiyari): variantın əlavə axtarış mətni (məs. diakritiksiz / ingiliscə ölkə adı).
                var match = !needle || hitTest(searchable(button.textContent + " " + (button.dataset.search || "")));
                button.hidden = !match;
                if (match) {
                    visible += 1;
                }
            });
            if (searchEmpty) {
                searchEmpty.hidden = visible > 0;
            }
            menu.scrollTop = 0; // uyğunluqlar başdan görünsün (köhnə sürüşmə yerində qalmasın)
        }

        function focusSearch() {
            if (isMenuOpen() && searchActive() && document.activeElement !== searchInput) {
                searchInput.focus({ preventScroll: true });
            }
        }

        function firstVisibleOption() {
            return menu.querySelector(".bootstrap-single-select__option:not([hidden]):not(:disabled)");
        }

        function onSearchKeydown(event) {
            if (event.key === "Enter") {
                // Enter — ilk görünən variantı seç (klaviatura ilə sürətli seçim).
                event.preventDefault();
                var first = firstVisibleOption();
                if (first) {
                    first.click();
                }
            } else if (event.key === "ArrowDown") {
                event.preventDefault();
                var next = firstVisibleOption();
                if (next) {
                    next.focus();
                }
            }
        }

        // Variant üzərində (ArrowDown ilə gəlinib) hərf yazmaq → axtarışa qayıt,
        // hərf ora düşsün; ilk variantda ArrowUp → yenə axtarışa.
        menu.addEventListener("keydown", function (event) {
            if (!searchActive() || event.target === searchInput) {
                return;
            }
            var printable = event.key && event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey;
            var upFromFirst = event.key === "ArrowUp" && event.target === firstVisibleOption();
            if (printable || event.key === "Backspace" || upFromFirst) {
                if (upFromFirst) {
                    event.preventDefault();
                    event.stopPropagation();
                }
                searchInput.focus();
            }
        });

        function syncToggleState() {
            var selectedOption = select.options[select.selectedIndex] || select.options[0];
            var hasValue = Boolean(select.value);

            // `data-toggle-label` (ixtiyari): düymədə qısa etiket (məs. telefon kodu «🇦🇿 +994»), menyuda tam mətn.
            label.textContent = selectedOption
                ? selectedOption.getAttribute("data-toggle-label") || selectedOption.textContent
                : "";
            // Dar sahədə yazı «…» ilə kəsiləndə tam mətn ipucunda görünsün (məs. uzun korpus adı).
            label.title = selectedOption ? selectedOption.textContent : "";
            toggle.classList.toggle("is-placeholder", !hasValue);
            toggle.classList.toggle("is-disabled", select.disabled);
            toggle.disabled = select.disabled;
            toggle.setAttribute("aria-disabled", select.disabled ? "true" : "false");
        }

        function syncSelectedState() {
            menu.querySelectorAll(".bootstrap-single-select__option").forEach(function (button) {
                var isSelected = normalizeValue(button.dataset.value) === normalizeValue(select.value);
                button.classList.toggle("is-selected", isSelected);
                button.setAttribute("aria-pressed", isSelected ? "true" : "false");
            });
        }

        // Menyu ilk açılışa qədər qurulmur (yuxarıdakı qeyd); `menuDirty` — native
        // `<select>` dəyişib, düymələr növbəti açılışda yenidən qurulmalıdır.
        var menuDirty = true;

        function isMenuOpen() {
            return menu.classList.contains("show");
        }

        function buildMenu() {
            menuDirty = false;
            // Açıq menyu yenidən qurulanda (variantlar gəldi) yazılan sorğu və fokus itməsin.
            var keepQuery = isMenuOpen() && searchActive() ? searchInput.value : "";
            var hadFocus = searchActive() && document.activeElement === searchInput;
            menu.innerHTML = "";
            var withSearch = wantsSearch();
            menu.classList.toggle("bootstrap-single-select__menu--searchable", withSearch);
            if (withSearch) {
                ensureSearch();
                searchInput.value = keepQuery;
                searchEmpty.hidden = true;
                menu.appendChild(searchWrap);
                menu.appendChild(searchEmpty);
            }

            Array.prototype.forEach.call(select.options, function (option, index) {
                // Gizli option-ları menyuda göstərmə (native select davranışı) —
                // kaskad/il filtri `option.hidden` ilə süzərsə, styled menyu da
                // yalnız uyğun seçimləri göstərsin (məs. tələbə jurnalı yarım-il).
                if (option.hidden) {
                    return;
                }
                var optionButton = document.createElement("button");
                var isPlaceholder = index === 0 && !option.value;

                optionButton.type = "button";
                optionButton.className = "dropdown-item bootstrap-single-select__option";
                optionButton.dataset.value = option.value;
                if (option.getAttribute("data-search")) {
                    optionButton.dataset.search = option.getAttribute("data-search");
                }
                optionButton.disabled = option.disabled;
                optionButton.classList.toggle("is-placeholder", isPlaceholder);
                // Option-un öz class-larını menyu düyməsinə köçür (məs.
                // "jd-topic-covered" → keçirilmiş mövzular yaşıl rənglənsin).
                if (option.className) {
                    option.classList.forEach(function (c) {
                        optionButton.classList.add(c);
                    });
                }

                var optionLabel = document.createElement("span");
                optionLabel.className = "bootstrap-single-select__option-label";
                optionLabel.textContent = option.textContent;
                // İkinci (sönük) sətir: `<option data-subtext="…">` — məs. jurnal mövzusunun dərs növləri
                // və «✓ keçirilib · tarix» (2026-10-25). Düymənin yazısı (toggle) yalnız əsas mətni göstərir.
                var subtext = option.getAttribute("data-subtext");
                if (subtext) {
                    var optionSub = document.createElement("span");
                    optionSub.className = "bootstrap-single-select__option-sub";
                    optionSub.textContent = subtext;
                    optionLabel.appendChild(optionSub);
                }
                optionButton.appendChild(optionLabel);

                var optionCheck = document.createElement("span");
                optionCheck.className = "bootstrap-single-select__option-check";
                optionCheck.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i>';
                optionButton.appendChild(optionCheck);

                menu.appendChild(optionButton);
            });

            syncSelectedState();
            syncToggleState();
            if (keepQuery) {
                applyLiveSearch();
            }
            if (hadFocus && withSearch) {
                searchInput.focus();
            }
        }

        function ensureMenu() {
            if (menuDirty) {
                buildMenu();
            }
        }

        // Bir delegə dinləyici (əvvəl hər variant düyməsində ayrıca idi).
        menu.addEventListener("click", function (event) {
            var optionButton = event.target && event.target.closest
                ? event.target.closest(".bootstrap-single-select__option")
                : null;
            if (!optionButton || !menu.contains(optionButton) || optionButton.disabled) {
                return;
            }

            select.value = optionButton.dataset.value;
            select.dispatchEvent(new Event("change", { bubbles: true }));
            closeDropdown();
        });

        function refresh() {
            if (isMenuOpen()) {
                buildMenu(); // açıq menyu dərhal yenilənsin (köhnə davranış)
                return;
            }
            menuDirty = true;
            syncToggleState();
        }

        function sync() {
            syncSelectedState();
            syncToggleState();
        }

        select.addEventListener("change", sync);

        // Kəsilmə fix-i: menyu HƏMİŞƏ viewport-a görə (fixed) yerləşir — yer yoxdursa yuxarı açılır, kənardan
        // çıxmır (`data-bs-display="static"` Popper flip-i söndürür; uzun mətnlər/dibdəki select-lər çıxırdı).
        function closeDropdown() {
            if (window.bootstrap && window.bootstrap.Dropdown) {
                window.bootstrap.Dropdown.getOrCreateInstance(toggle).hide();
            }
        }

        function onScrollWhileOpen(event) {
            // Menyu daxili scroll-a icazə ver, kənardakı scroll-da (və ölçü dəyişəndə) bağla.
            if (event && event.target instanceof Node && menu.contains(event.target)) {
                return;
            }
            if (keepOpenOnViewportChange(searchInput)) {
                positionMenuFixed(toggle, menu);
            } else {
                closeDropdown();
            }
        }

        // Toggle-da yazılan hərf itməsin (əvvəl fokus axtarışa yalnız taymerlə keçirdi): menyu açılır, hərf axtarışa.
        toggle.addEventListener("keydown", function (event) {
            var key = event.key || "";
            if (key.length !== 1 || key === " " || event.ctrlKey || event.metaKey || event.altKey || toggle.disabled) {
                return;
            }
            ensureMenu();
            if (searchActive() && !isMenuOpen() && window.bootstrap && window.bootstrap.Dropdown) {
                window.bootstrap.Dropdown.getOrCreateInstance(toggle).show();
            }
            focusSearch();
        });

        // Fokusda əvvəlcədən qur — klaviatura istifadəçisi üçün ilk açılış gecikməsin.
        toggle.addEventListener("focus", ensureMenu);

        toggle.addEventListener("show.bs.dropdown", function () {
            ensureMenu(); // menyu göstərilməzdən və yerləşdirilməzdən ƏVVƏL qurulur
            positionMenuFixed(toggle, menu);
            window.addEventListener("scroll", onScrollWhileOpen, true);
            window.addEventListener("resize", onScrollWhileOpen);
        });

        toggle.addEventListener("shown.bs.dropdown", function () {
            if (searchActive()) {
                searchInput.value = "";
                applyLiveSearch();
                // Fokus DƏRHAL axtarışda (ilk hərf itməsin); taymer — Bootstrap fokusu variantə aparsa.
                focusSearch();
                window.setTimeout(focusSearch, 0);
            }
            var selectedButton = menu.querySelector(".bootstrap-single-select__option.is-selected");
            if (selectedButton && typeof selectedButton.scrollIntoView === "function") {
                selectedButton.scrollIntoView({ block: "nearest" });
            }
        });

        toggle.addEventListener("hidden.bs.dropdown", function () {
            window.removeEventListener("scroll", onScrollWhileOpen, true);
            window.removeEventListener("resize", onScrollWhileOpen);
            resetMenuPosition(menu);
            // Bağlananda sorğu təmizlənir — növbəti açılışda tam siyahı görünsün.
            if (searchActive() && searchInput.value) {
                searchInput.value = "";
                applyLiveSearch();
            }
        });

        select._refreshBootstrapSelect = refresh;
        select._syncBootstrapSelect = sync;

        var api = {
            refresh: refresh,
            sync: sync,
            build: ensureMenu,
        };

        select._bootstrapSelectApi = api;
        refresh();
        // Variantlar `refresh()`-siz dəyişsə də (innerHTML, appendChild, `hidden`) axtarış köhnə siyahıda qalmasın.
        if (typeof window.MutationObserver === "function") {
            var watch = { childList: true, subtree: true, characterData: true, attributes: true };
            watch.attributeFilter = ["hidden", "disabled", "label", "selected", "data-search", "data-subtext"];
            new window.MutationObserver(function () {
                return window.document ? refresh() : null; // bağlanmış pəncərə (jsdom teardown) — yox
            }).observe(select, watch);
        }

        return api;
    }

    // `<select multiple>` bu komponentin işi DEYİL (`select.value = …` bütün seçimləri silərdi) —
    // stilli çoxseçim `static/js/ems_multi_select.js`-dədir (`EMSMultiSelect`). Ümumi
    // `EMSBootstrapSelect.refresh/sync/init` çağırışları ora ötürülür ki, mövcud kod (məs.
    // formadakı bütün select-ləri yeniləyən köməkçilər) çoxseçimi də sinxron saxlasın.
    function multiApi() {
        return window.EMSMultiSelect || null;
    }

    function initBootstrapSelects(root) {
        var scope = root || document;
        scope.querySelectorAll("[data-bootstrap-select]").forEach(function (select) {
            enhanceBootstrapSelect(select);
        });
        if (multiApi()) {
            multiApi().init(scope);
        }
    }

    // Sonradan əlavə olunan select-lər (dialoq/partial `innerHTML`, JS ilə qurulan sətirlər):
    // `profile:section:loaded` göndərməyən swap-larda da avtomatik qoşulur. Yalnız ƏLAVƏ
    // olunan element düyünlərinə baxılır; artıq qoşulmuş select-lər təkrar işlənmir.
    var WATCH = "[data-bootstrap-select], [data-ems-multi-select]";

    function onMutations(records) {
        for (var i = 0; i < records.length; i += 1) {
            var added = records[i].addedNodes;
            for (var j = 0; j < added.length; j += 1) {
                var node = added[j];
                if (node.nodeType !== 1 || node.classList.contains("bootstrap-single-select__option")) {
                    continue;
                }
                if ((node.matches && node.matches(WATCH)) || node.querySelector(WATCH)) {
                    initBootstrapSelects(node.matches && node.matches(WATCH) ? node.parentNode || node : node);
                }
            }
        }
    }

    function watchInsertedSelects() {
        if (typeof window.MutationObserver !== "function" || !document.body || window.__emsSelectObserver) {
            return;
        }
        window.__emsSelectObserver = new window.MutationObserver(onMutations);
        window.__emsSelectObserver.observe(document.body, { childList: true, subtree: true });
    }

    function boot() {
        initBootstrapSelects(document);
        watchInsertedSelects();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }

    // AJAX section swap-dan sonra avtomatik re-init.
    document.addEventListener("profile:section:loaded", function (event) {
        var panel = event.detail && event.detail.panel ? event.detail.panel : document;
        initBootstrapSelects(panel);
    });

    window.EMSBootstrapSelect = {
        enhance: enhanceBootstrapSelect,
        init: initBootstrapSelects,
        refresh: function (select) {
            if (!select) {
                return;
            }
            if (select.multiple) {
                if (multiApi()) {
                    multiApi().refresh(select);
                }
                return;
            }
            if (typeof select._refreshBootstrapSelect === "function") {
                select._refreshBootstrapSelect();
                return;
            }
            enhanceBootstrapSelect(select);
        },
        sync: function (select) {
            if (select && select.multiple) {
                if (multiApi()) {
                    multiApi().sync(select);
                }
                return;
            }
            if (select && typeof select._syncBootstrapSelect === "function") {
                select._syncBootstrapSelect();
            }
        },
    };
})();
