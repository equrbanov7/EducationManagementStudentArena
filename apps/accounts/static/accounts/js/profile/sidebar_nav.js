/* Kabinet sol menyusu — yığcam (ikon-rels) rejimin tooltip-ləri, üfüqi sürüşmə
 * qoruyucusu və düz menyuda aktiv bəndin görünən sahəyə gətirilməsi (2026-09-25).
 *
 * Niyə ayrıca fayl? `ui.js` modul ölçü həddinə (600 sətir) dayanıb; bu fayl
 * sidebar partial-ının ÖZÜNDƏN (`_sidebar.html`) yüklənir ki, həm SPA
 * qabığında, həm embed səhifələrdə (`profile_sidebar` teqi) eyni işləsin.
 *
 * 1. Rels rejimində (`.profile-sidebar.collapsed`, yalnız masaüstü) bəndin
 *    mətni vizual gizlidir (ekran oxuyucu onu yenə oxuyur). Göz üçün ad —
 *    `title` tooltip-i. Server `title` yazmır (geniş rejimdə hər hover-də
 *    təkrar tooltip çıxardı); skript rels rejimində yazır, çıxanda YALNIZ öz
 *    yazdığını (`data-rail-title`) silir.
 * 2. Sidebar üfüqi sürüşməməlidir (`overflow-x: hidden`), amma proqram yolu
 *    (fokus, `scrollIntoView`, keçid anındakı trackpad jesti) `scrollLeft`-i
 *    dəyişə bilir — sol kənar kəsilirdi («rofil», «MUMİ»). Sıfırlanır.
 * 3. Düz menyuda (tələbə/müəllim) aktiv bənd yapışan başlığın/alt blokun
 *    altında qalmasın: ilk yükləmədə və hər AJAX bölmə keçidindən sonra
 *    YALNIZ sidebar sürüşdürülür (səhifə yerində qalır). Akkordeonda bunu
 *    `ui.js` (`scrollActiveSidebarLinkIntoView`) edir — orada toxunulmur.
 *
 * AJAX-safe: quraşdırma `EMSReady.once` ilə BİR dəfə (sidebar swap olunmur),
 * aktiv bəndin göstərilməsi `EMSReady` ilə hər swap-dan sonra (idempotent).
 */
(function () {
    "use strict";

    var RAIL_TITLE_ATTR = "data-rail-title";
    var MOBILE_QUERY = "(max-width: 768px)";

    function railLabel(link) {
        var text = link.querySelector(".sidebar-menu-text");
        return text ? (text.textContent || "").replace(/\s+/g, " ").trim() : "";
    }

    function isRailMode(sidebar) {
        var isMobile = typeof window.matchMedia === "function" && window.matchMedia(MOBILE_QUERY).matches;
        return sidebar.classList.contains("collapsed") && !isMobile;
    }

    function syncRailTitles(sidebar) {
        var railMode = isRailMode(sidebar);
        var links = sidebar.querySelectorAll(".sidebar-menu-link");
        for (var i = 0; i < links.length; i += 1) {
            var link = links[i];
            if (railMode) {
                var label = link.hasAttribute("title") ? "" : railLabel(link);
                if (label) {
                    link.setAttribute("title", label);
                    link.setAttribute(RAIL_TITLE_ATTR, "1");
                }
            } else if (link.getAttribute(RAIL_TITLE_ATTR) === "1") {
                link.removeAttribute("title");
                link.removeAttribute(RAIL_TITLE_ATTR);
            }
        }
    }

    function revealActiveLink() {
        var sidebar = document.getElementById("profileSidebar");
        if (!sidebar || sidebar.getAttribute("data-sidebar-layout") === "full") {
            return;
        }
        if (typeof window.requestAnimationFrame !== "function") {
            return;
        }
        // Aktiv bənd kadr İÇİNDƏ axtarılır: `profile:section:loaded` hadisəsi
        // `updateSidebarActiveState`-dən ƏVVƏL atılır (section_loader.js).
        window.requestAnimationFrame(function () {
            var active = sidebar.querySelector(".sidebar-nav .sidebar-menu-link.active");
            if (!active) {
                return;
            }
            var frame = sidebar.getBoundingClientRect();
            var header = sidebar.querySelector(".sidebar-header");
            var footer = sidebar.querySelector(".sidebar-footer");
            var top = frame.top + (header ? header.offsetHeight : 0);
            var bottom = frame.bottom - (footer ? footer.offsetHeight : 0);
            var box = active.getBoundingClientRect();
            if (box.height === 0 || (box.top >= top && box.bottom <= bottom)) {
                return;
            }
            sidebar.scrollTop += box.top - top - Math.max(0, (bottom - top) / 3);
        });
    }

    function setup() {
        var sidebar = document.getElementById("profileSidebar");
        if (!sidebar || sidebar.getAttribute("data-nav-ready") === "1") {
            return;
        }
        sidebar.setAttribute("data-nav-ready", "1");

        syncRailTitles(sidebar);
        if (typeof window.MutationObserver === "function") {
            new window.MutationObserver(function () {
                syncRailTitles(sidebar);
            }).observe(sidebar, { attributes: true, attributeFilter: ["class"] });
        }

        sidebar.addEventListener(
            "scroll",
            function () {
                if (sidebar.scrollLeft !== 0) {
                    sidebar.scrollLeft = 0;
                }
            },
            { passive: true }
        );
    }

    if (typeof window.EMSReady !== "function") {
        return;
    }
    if (typeof window.EMSReady.once === "function") {
        window.EMSReady.once("profile-sidebar-nav", setup);
    } else {
        window.EMSReady(setup);
    }
    window.EMSReady(revealActiveLink);
})();
