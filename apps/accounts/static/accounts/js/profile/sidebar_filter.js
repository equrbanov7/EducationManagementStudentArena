/* Kabinet sol menyusu — «Menyuda axtar» süzgəci (2026-09-25).
 *
 * Yalnız uzun menyuda (> 20 bənd, `profile_shell.profile_sidebar_filter_enabled`)
 * `_sidebar.html` sahəni və bu skripti render edir. Süzgəc TAMAMİLƏ brauzerdədir:
 * sorğu yoxdur, bənd siyahısı server-render menyudur.
 *
 * Davranış
 * • Yazdıqca bəndlər adına (və qrupun adına) görə süzülür; hər söz ayrıca
 *   axtarılır (bəndin və ya qrupun adında), az/ing hərfləri yumşaq tutuşdurulur
 *   («sagird» → «şagird», «imtahan» → «İmtahan», «shagird» → «şagird») —
 *   kanonik `EMSSearch` (static/js/search_fold.js, 2026-09-26).
 * • Uyğun bəndi olan qrup AÇILIR, olmayan qrup gizlənir; süzgəc təmizlənəndə
 *   qrupların əvvəlki açıq/bağlı vəziyyəti bərpa olunur. İstifadəçinin
 *   yadda saxlanan seçimi (`profileSidebarGroups`, ui.js) DƏYİŞMİR — ui.js
 *   yaddaşa yalnız başlığa klikləri yazır, proqram açılışını yox.
 * • `/` (yazı sahəsində deyilkən) sahəni fokuslayır; Esc əvvəl mətni təmizləyir,
 *   boş sahədə fokusu buraxır; Enter ilk uyğun bəndi açır, ↓ ona keçir.
 * • Heç nə tapılmayanda canlı region (`role="status"`) serverdən gələn mətni
 *   oxuyur — JS-də tərcümə sətri yoxdur.
 *
 * AJAX-safe: sidebar bölmə swap-ında dəyişmir → quraşdırma `EMSReady.once` ilə
 * BİR dəfə; qısayol `document`-ə bir dəfə bağlanır.
 */
(function () {
    "use strict";

    /* Uyğunluq kanonik `EMSSearch`-dədir (static/js/search_fold.js, base.html <head>):
       az/ing hərfləri (ı/i, ə/e/a, ş/s/sh, ç/c/ch, ğ/g/gh, ö/o, ü/u, x/kh) və kod rejimi.
       Kitabxana yoxdursa sadə registrsiz «contains»-ə düşür. */
    function tokensOf(query) {
        if (window.EMSSearch) {
            return window.EMSSearch.tokens(query);
        }
        return String(query || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
    }

    function matcherFor(query) {
        if (window.EMSSearch) {
            return window.EMSSearch.matcher(query);
        }
        var tokens = tokensOf(query);
        return function (text) {
            var hay = String(text || "").toLowerCase();
            return tokens.every(function (token) {
                return hay.indexOf(token) !== -1;
            });
        };
    }

    function textOf(node) {
        return node ? node.textContent || "" : "";
    }

    function isEditable(node) {
        if (!node || !node.tagName) {
            return false;
        }
        return node.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(node.tagName);
    }

    function setup() {
        var sidebar = document.getElementById("profileSidebar");
        var input = sidebar ? sidebar.querySelector("[data-sidebar-filter]") : null;
        var nav = sidebar ? sidebar.querySelector(".sidebar-nav") : null;
        if (!input || !nav || input.getAttribute("data-filter-ready") === "1") {
            return;
        }
        input.setAttribute("data-filter-ready", "1");
        var status = nav.querySelector("[data-sidebar-filter-status]");

        // İndeks bir dəfə qurulur: menyu server-render-dir və swap olunmur.
        var entries = Array.prototype.map.call(nav.querySelectorAll(".sidebar-menu-item"), function (item) {
            var group = item.closest(".sidebar-menu-group, .sidebar-section");
            var groupLabel = group ? group.querySelector(".sidebar-menu-group-text, .sidebar-menu-group-title") : null;
            return {
                item: item,
                link: item.querySelector(".sidebar-menu-link"),
                label: textOf(item.querySelector(".sidebar-menu-text")),
                groupLabel: textOf(groupLabel),
            };
        });
        var containers = Array.prototype.slice.call(nav.querySelectorAll(".sidebar-menu-group, .sidebar-section"));

        function openActiveGroup() {
            var active = nav.querySelector(".sidebar-menu-link.active");
            var details = active ? active.closest("details.sidebar-group") : null;
            if (details) {
                details.open = true;
            }
        }

        function apply() {
            var filtering = tokensOf(input.value).length > 0;
            var hitTest = matcherFor(input.value);
            var matches = 0;
            sidebar.classList.toggle("is-filtering", filtering);

            entries.forEach(function (entry) {
                var hit = !filtering || hitTest(entry.label, entry.groupLabel);
                entry.item.hidden = !hit;
                if (hit && filtering) {
                    matches += 1;
                }
            });

            containers.forEach(function (container) {
                var hasVisible = container.querySelector(".sidebar-menu-item:not([hidden])") !== null;
                container.hidden = filtering && !hasVisible;
                var details = container.querySelector("details.sidebar-group");
                if (!details) {
                    return;
                }
                if (filtering) {
                    if (!details.hasAttribute("data-open-before-filter")) {
                        details.setAttribute("data-open-before-filter", details.open ? "1" : "0");
                    }
                    details.open = hasVisible;
                } else if (details.hasAttribute("data-open-before-filter")) {
                    details.open = details.getAttribute("data-open-before-filter") === "1";
                    details.removeAttribute("data-open-before-filter");
                }
            });

            if (!filtering) {
                // Süzgəc zamanı SPA keçidi olubsa, yeni aktiv bəndin qrupu açıq qalsın.
                openActiveGroup();
            }
            if (status) {
                status.textContent = filtering && matches === 0 ? status.getAttribute("data-empty-text") || "" : "";
            }
        }

        function firstVisibleLink() {
            for (var i = 0; i < entries.length; i += 1) {
                if (!entries[i].item.hidden && entries[i].link && entries[i].item.getClientRects().length) {
                    return entries[i].link;
                }
            }
            return null;
        }

        function clear() {
            if (input.value) {
                input.value = "";
                apply();
            }
        }

        input.addEventListener("input", apply);
        input.addEventListener("search", apply);
        input.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                if (input.value) {
                    // Mətni təmizləyir; mobil şkafın Esc-lə bağlanması (init.js) işə düşməsin.
                    event.preventDefault();
                    event.stopPropagation();
                    clear();
                } else {
                    input.blur();
                }
                return;
            }
            if (event.key === "ArrowDown" || event.key === "Enter") {
                var first = firstVisibleLink();
                if (!first || (event.key === "Enter" && !input.value.trim())) {
                    return;
                }
                event.preventDefault();
                if (event.key === "Enter") {
                    first.click();
                } else {
                    first.focus();
                }
            }
        });

        /* Rels (yığcam) rejimdə sahə gizlidir — gizli süzgəc menyunu «yarımçıq»
           saxlamasın. Amma relsdə BÜTÜN `<details>` açıq qalmalıdır (ui.js onları
           açır və əvvəlki halı `data-open-before-collapse`-a yazır; observer
           `setSidebarCollapsed` bitəndən SONRA işləyir). Ona görə burada qruplar
           bağlanmır: süzgəcdən ƏVVƏLKİ həqiqi hal ui.js-in bərpa açarına ötürülür. */
        function resetForRail() {
            if (!input.value && !sidebar.classList.contains("is-filtering")) {
                return;
            }
            input.value = "";
            containers.forEach(function (container) {
                container.hidden = false;
                var details = container.querySelector("details.sidebar-group");
                if (details && details.hasAttribute("data-open-before-filter")) {
                    if (details.hasAttribute("data-open-before-collapse")) {
                        details.setAttribute("data-open-before-collapse", details.getAttribute("data-open-before-filter"));
                    }
                    details.removeAttribute("data-open-before-filter");
                }
            });
            entries.forEach(function (entry) {
                entry.item.hidden = false;
            });
            sidebar.classList.remove("is-filtering");
            if (status) {
                status.textContent = "";
            }
        }

        if (typeof window.MutationObserver === "function") {
            new window.MutationObserver(function () {
                if (sidebar.classList.contains("collapsed")) {
                    resetForRail();
                }
            }).observe(sidebar, { attributes: true, attributeFilter: ["class"] });
        }

        document.addEventListener("keydown", function (event) {
            if (event.key !== "/" || event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) {
                return;
            }
            if (isEditable(event.target) || document.body.classList.contains("modal-open")) {
                return;
            }
            if (sidebar.classList.contains("collapsed") || !input.getClientRects().length) {
                return;
            }
            event.preventDefault();
            input.focus();
            input.select();
        });
    }

    if (typeof window.EMSReady !== "function") {
        return;
    }
    if (typeof window.EMSReady.once === "function") {
        window.EMSReady.once("profile-sidebar-filter", setup);
    } else {
        window.EMSReady(setup);
    }
})();
