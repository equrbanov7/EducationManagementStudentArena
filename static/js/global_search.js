/*
 * Global ⌘K search (U8) — command-palette overlay.
 *
 * CSP-safe (no inline handlers), progressive-enhancement: if JS fails the
 * overlay simply never opens and the rest of the app is unaffected.
 *
 * Davranış:
 *   - Aç   : ⌘K / Ctrl+K, yaxud [data-global-search-open] düyməsi.
 *   - Bağla: Esc, fon klikı, «esc» düyməsi və ya nəticə seçmək.
 *   - Sorğu: [data-search-url]?q= ünvanına gecikdirilmiş GET → qruplu JSON.
 *   - Klaviatura: ↑/↓ (dövrələmə ilə), Home/End, ↵ açır, ⌘/Ctrl+↵ yeni tabda.
 *   - Tab fokusu panelin İÇİNDƏ dövr edir (modal tələbi).
 *
 * A11y: role=dialog/listbox/option, input-da aria-activedescendant,
 * nəticə sayı `role="status"` canlı sahəsi ilə elan olunur.
 *
 * Şablon: templates/partials/_global_search.html — üslub: static/css/global_search.css
 */
(function () {
    "use strict";

    var DEBOUNCE_MS = 160;
    // Skelet yalnız sorğu «hiss olunacaq qədər» uzanarsa göstərilir — əks halda
    // hər hərfdə yanıb-sönmə yaranır.
    var LOADING_DELAY_MS = 140;
    var FOCUSABLE = 'a[href], button:not([disabled]), input, [tabindex]:not([tabindex="-1"])';

    function t(text) {
        return window.gettext ? window.gettext(text) : text;
    }

    /* ── Sorğuya uyğun hissənin vurğulanması ────────────────────────────────
       `toLowerCase()` bəzi hərfləri (məs. «İ») İKİ simvola açır və indekslər
       sürüşür. Ona görə simvol-simvol qatlayırıq: uzunluq həmişə eyni qalır. */
    function fold(text) {
        var out = "";
        for (var i = 0; i < text.length; i++) {
            var ch = text.charAt(i);
            var lower = ch.toLowerCase();
            out += lower.charAt(0) || ch;
        }
        return out;
    }

    /** Mətni `<span>`-a yazır; sorğuya uyğun hissəni `<mark>` ilə vurğulayır. */
    function fillHighlighted(el, text, query) {
        var value = text || "";
        var needle = (query || "").trim();
        if (!needle) {
            el.textContent = value;
            return;
        }
        var at = fold(value).indexOf(fold(needle));
        if (at < 0) {
            el.textContent = value;
            return;
        }
        el.textContent = "";
        el.appendChild(document.createTextNode(value.slice(0, at)));
        var hit = document.createElement("mark");
        hit.className = "gsearch__mark";
        hit.textContent = value.slice(at, at + needle.length);
        el.appendChild(hit);
        el.appendChild(document.createTextNode(value.slice(at + needle.length)));
    }

    function safeIcon(icon) {
        return /^fa-[a-z0-9-]+$/.test(icon || "") ? icon : "fa-circle";
    }

    function init() {
        var root = document.querySelector("[data-global-search]");
        // Şablon yalnız daxil olmuş istifadəçi üçün render olunur; həmçinin
        // EMSReady bölmə swap-ından sonra yenidən işləyə bilər — ikiqat
        // bağlanmanın qarşısını alırıq.
        if (!root || root.__emsGlobalSearchBound) {
            return;
        }
        root.__emsGlobalSearchBound = true;

        var panel = root.querySelector(".gsearch__panel");
        var input = root.querySelector("[data-global-search-input]");
        var resultsEl = root.querySelector("[data-global-search-results]");
        var emptyEl = root.querySelector("[data-global-search-empty]");
        var loadingEl = root.querySelector("[data-global-search-loading]");
        var statusEl = root.querySelector("[data-global-search-status]");
        var clearBtn = root.querySelector("[data-global-search-clear]");
        var searchUrl = root.getAttribute("data-search-url");
        if (!input || !resultsEl) {
            return;
        }

        var options = []; // düz siyahı: <a role="option">
        var activeIndex = -1;
        var lastQuery = "";
        var debounceTimer = null;
        var loadingTimer = null;
        var requestToken = 0;
        var lastFocused = null;

        function isOpen() {
            return !root.hasAttribute("hidden");
        }

        function announce(text) {
            if (statusEl) {
                statusEl.textContent = text;
            }
        }

        /**
         * Yüklənmə göstəricisi iki cürdür:
         *  · nəticə hələ yoxdursa — skelet sətirləri (panel boş qalmasın);
         *  · nəticə varsa — köhnə siyahı solur (hər hərfdə sıçrama olmasın).
         */
        function showLoading(on) {
            var skeleton = on && !options.length;
            if (loadingEl) {
                loadingEl.hidden = !skeleton;
            }
            resultsEl.classList.toggle("gsearch__results--busy", on && !skeleton);
            if (on && emptyEl) {
                emptyEl.hidden = true;
            }
        }

        function clearResults() {
            resultsEl.textContent = "";
            options = [];
            activeIndex = -1;
            input.removeAttribute("aria-activedescendant");
        }

        function setActive(index) {
            if (!options.length) {
                return;
            }
            if (index < 0) {
                index = options.length - 1;
            }
            if (index >= options.length) {
                index = 0;
            }
            if (activeIndex >= 0 && options[activeIndex]) {
                options[activeIndex].classList.remove("is-active");
                options[activeIndex].setAttribute("aria-selected", "false");
            }
            activeIndex = index;
            var el = options[activeIndex];
            el.classList.add("is-active");
            el.setAttribute("aria-selected", "true");
            input.setAttribute("aria-activedescendant", el.id);
            el.scrollIntoView({ block: "nearest" });
        }

        function buildItem(item, query, index) {
            var link = document.createElement("a");
            link.className = "gsearch__item";
            link.href = item.url;
            link.setAttribute("role", "option");
            link.setAttribute("aria-selected", "false");
            link.id = "gsearch-opt-" + index;

            var icon = document.createElement("i");
            icon.className = "fas " + safeIcon(item.icon) + " gsearch__item-icon";
            icon.setAttribute("aria-hidden", "true");
            link.appendChild(icon);

            var body = document.createElement("span");
            body.className = "gsearch__item-body";
            var title = document.createElement("span");
            title.className = "gsearch__item-title";
            fillHighlighted(title, item.title, query);
            body.appendChild(title);
            if (item.subtitle) {
                var sub = document.createElement("span");
                sub.className = "gsearch__item-subtitle";
                fillHighlighted(sub, item.subtitle, query);
                body.appendChild(sub);
            }
            link.appendChild(body);

            var enter = document.createElement("span");
            enter.className = "gsearch__item-enter";
            enter.setAttribute("aria-hidden", "true");
            enter.textContent = "↵";
            link.appendChild(enter);

            return link;
        }

        function renderGroups(groups, query) {
            clearResults();
            var frag = document.createDocumentFragment();
            (groups || []).forEach(function (group) {
                var items = group.items || [];
                if (!items.length) {
                    return;
                }
                var section = document.createElement("div");
                section.className = "gsearch__group";

                var label = document.createElement("div");
                label.className = "gsearch__group-label";
                label.textContent = group.label;
                section.appendChild(label);

                items.forEach(function (item) {
                    var link = buildItem(item, query, options.length);
                    section.appendChild(link);
                    options.push(link);
                });
                frag.appendChild(section);
            });
            resultsEl.appendChild(frag);

            var count = options.length;
            if (emptyEl) {
                emptyEl.hidden = count > 0;
            }
            if (count) {
                setActive(0);
                announce(count + " · " + t("Axtarış nəticələri"));
            } else {
                announce(t("Nəticə tapılmadı"));
            }
        }

        function runQuery(query) {
            var token = ++requestToken;
            lastQuery = query;
            if (loadingTimer) {
                window.clearTimeout(loadingTimer);
            }
            loadingTimer = window.setTimeout(function () {
                if (token === requestToken && isOpen()) {
                    showLoading(true);
                }
            }, LOADING_DELAY_MS);

            function finish(groups) {
                if (token !== requestToken || !isOpen()) {
                    return; // köhnəlmiş cavab
                }
                window.clearTimeout(loadingTimer);
                showLoading(false);
                renderGroups(groups, query);
            }

            window
                .fetch(searchUrl + "?q=" + encodeURIComponent(query), {
                    credentials: "same-origin",
                    headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" }
                })
                .then(function (response) {
                    return response.ok ? response.json() : { groups: [] };
                })
                .then(function (data) {
                    finish(data.groups);
                })
                .catch(function () {
                    finish([]);
                });
        }

        function syncClearButton() {
            if (clearBtn) {
                clearBtn.hidden = !input.value;
            }
        }

        function open() {
            if (isOpen()) {
                return;
            }
            // Başlıqda eyni anda yalnız BİR açılan: dil/istifadəçi/«Yarat»
            // menyuları bu hadisəni eşidib bağlanır (bax burgerMenu.js).
            document.dispatchEvent(new CustomEvent("ems:popover:open", { detail: { source: "global-search" } }));
            lastFocused = document.activeElement;
            root.removeAttribute("hidden");
            document.body.classList.add("gsearch-open");
            input.value = "";
            syncClearButton();
            input.focus();
            runQuery(""); // sürətli keçidlər dərhal görünsün
        }

        /**
         * Panel bağlananda fokus itməsin: əvvəlki elementə qayıdırıq, o yoxdursa
         * (⌘K ilə açılıbsa `document.body` olur) başlıqdakı axtarış düyməsinə.
         */
        function restoreFocus() {
            var target = lastFocused;
            if (!target || target === document.body || !document.contains(target)) {
                target = document.querySelector("[data-global-search-open]");
            }
            if (target && typeof target.focus === "function") {
                target.focus();
            } else {
                input.blur();
            }
        }

        function close() {
            if (!isOpen()) {
                return;
            }
            requestToken++; // uçuşdakı cavablar panelə toxunmasın
            window.clearTimeout(loadingTimer);
            window.clearTimeout(debounceTimer);
            root.setAttribute("hidden", "");
            document.body.classList.remove("gsearch-open");
            showLoading(false);
            if (emptyEl) {
                emptyEl.hidden = true;
            }
            clearResults();
            announce("");
            restoreFocus();
        }

        function activate(link, event) {
            if (!link) {
                return;
            }
            if (event && (event.metaKey || event.ctrlKey)) {
                window.open(link.href, "_blank", "noopener");
                return;
            }
            window.location.href = link.href;
        }

        /** Tab modal panelin içində dövr etsin (fokus arxadakı səhifəyə qaçmasın). */
        function trapTab(event) {
            if (!panel) {
                return;
            }
            var focusable = Array.prototype.filter.call(
                panel.querySelectorAll(FOCUSABLE),
                function (el) {
                    return !el.hasAttribute("hidden") && el.offsetParent !== null;
                }
            );
            if (!focusable.length) {
                return;
            }
            var first = focusable[0];
            var last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }

        /* ── Hadisələr ──────────────────────────────────────────────────────
           Delegasiya açarları («hadisə|seçici») QLOBALDIR — bu seçicilər yalnız
           bu faylda qeydiyyatdan keçir (bax apps/accounts/tests/test_static_js_delegate_keys.py). */
        var delegate = window.EMSDelegate;
        if (delegate) {
            delegate.on("click", "[data-global-search-open]", function (event) {
                event.preventDefault();
                open();
            });
            delegate.on("click", "[data-global-search-close]", function () {
                close();
            });
            delegate.on("click", "[data-global-search-clear]", function () {
                input.value = "";
                syncClearButton();
                input.focus();
                runQuery("");
            });
        }

        // Başqa açılan (dil/istifadəçi menyusu) açılanda axtarış bağlanır.
        document.addEventListener("ems:popover:open", function (event) {
            if (!event.detail || event.detail.source !== "global-search") {
                close();
            }
        });

        document.addEventListener("keydown", function (event) {
            var key = event.key ? event.key.toLowerCase() : "";
            if ((event.metaKey || event.ctrlKey) && key === "k") {
                event.preventDefault();
                if (isOpen()) {
                    close();
                } else {
                    open();
                }
            } else if (key === "escape" && isOpen()) {
                event.preventDefault();
                close();
            } else if (key === "tab" && isOpen()) {
                trapTab(event);
            }
        });

        input.addEventListener("input", function () {
            syncClearButton();
            var query = input.value.trim();
            window.clearTimeout(debounceTimer);
            debounceTimer = window.setTimeout(function () {
                if (query !== lastQuery) {
                    runQuery(query);
                }
            }, DEBOUNCE_MS);
        });

        input.addEventListener("keydown", function (event) {
            if (!isOpen()) {
                return;
            }
            var key = event.key ? event.key.toLowerCase() : "";
            if (key === "arrowdown") {
                event.preventDefault();
                setActive(activeIndex + 1);
            } else if (key === "arrowup") {
                event.preventDefault();
                setActive(activeIndex - 1);
            } else if (key === "home" && options.length) {
                event.preventDefault();
                setActive(0);
            } else if (key === "end" && options.length) {
                event.preventDefault();
                setActive(options.length - 1);
            } else if (key === "enter" && activeIndex >= 0 && options[activeIndex]) {
                event.preventDefault();
                activate(options[activeIndex], event);
            }
        });

        // Siçan sətrin üstünə gələndə aktiv seçim onunla sinxronlaşır; sürüşdürmə
        // zamanı yaranan «saxta» mousemove aktiv sətri oğurlamasın deyə kursorun
        // həqiqətən tərpəndiyini yoxlayırıq.
        var lastPointer = { x: -1, y: -1 };
        resultsEl.addEventListener("mousemove", function (event) {
            if (event.clientX === lastPointer.x && event.clientY === lastPointer.y) {
                return;
            }
            lastPointer.x = event.clientX;
            lastPointer.y = event.clientY;
            var item = event.target.closest(".gsearch__item");
            if (!item) {
                return;
            }
            var index = options.indexOf(item);
            if (index >= 0 && index !== activeIndex) {
                setActive(index);
            }
        });

        resultsEl.addEventListener("click", function (event) {
            var item = event.target.closest(".gsearch__item");
            if (item) {
                event.preventDefault();
                activate(item, event);
            }
        });
    }

    if (window.EMSReady) {
        window.EMSReady(init);
    } else {
        document.addEventListener("DOMContentLoaded", init);
    }
})();
