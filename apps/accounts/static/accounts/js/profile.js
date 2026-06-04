/**
 * Profile page sidebar and section switching functionality.
 */
document.addEventListener("DOMContentLoaded", function () {
    var toggleBtn = document.getElementById("sidebarToggle");
    var sidebar = document.getElementById("profileSidebar");
    var mobileSidebarTrigger = document.getElementById("profileMobileSidebarTrigger");
    var sidebarBackdrop = document.getElementById("profileSidebarBackdrop");
    var mobileMediaQuery = window.matchMedia("(max-width: 768px)");
    var sidebarExpandTitle = toggleBtn ? toggleBtn.getAttribute("data-title-expand") || "Open sidebar" : "Open sidebar";
    var sidebarCollapseTitle = toggleBtn
        ? toggleBtn.getAttribute("data-title-collapse") || "Close sidebar"
        : "Close sidebar";

    function isMobileViewport() {
        return mobileMediaQuery.matches;
    }

    function setSidebarCollapsed(isCollapsed) {
        if (!sidebar) {
            return;
        }
        sidebar.classList.toggle("collapsed", isCollapsed);
        localStorage.setItem("profileSidebarCollapsed", isCollapsed ? "true" : "false");
        syncSidebarToggleState();
    }

    function syncSidebarToggleState() {
        if (!sidebar) {
            return;
        }

        var icon = toggleBtn ? toggleBtn.querySelector("i") : null;
        var isCollapsed = sidebar.classList.contains("collapsed");

        if (icon && toggleBtn) {
            if (isCollapsed) {
                icon.classList.remove("fa-chevron-left");
                icon.classList.add("fa-chevron-right");
                toggleBtn.title = sidebarExpandTitle;
            } else {
                icon.classList.remove("fa-chevron-right");
                icon.classList.add("fa-chevron-left");
                toggleBtn.title = sidebarCollapseTitle;
            }
        }

        if (mobileSidebarTrigger) {
            mobileSidebarTrigger.classList.toggle("is-hidden", !isCollapsed || !isMobileViewport());
            mobileSidebarTrigger.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
        }

        if (sidebarBackdrop) {
            sidebarBackdrop.classList.toggle("is-visible", isMobileViewport() && !isCollapsed);
        }

        document.body.classList.toggle("profile-sidebar-open-mobile", isMobileViewport() && !isCollapsed);
    }

    if (sidebar) {
        if (toggleBtn) {
            toggleBtn.addEventListener("click", function () {
                setSidebarCollapsed(!sidebar.classList.contains("collapsed"));
            });
        }

        if (localStorage.getItem("profileSidebarCollapsed") === "true") {
            sidebar.classList.add("collapsed");
        }
        syncSidebarToggleState();
    }

    if (mobileSidebarTrigger && sidebar) {
        mobileSidebarTrigger.addEventListener("click", function () {
            setSidebarCollapsed(false);
        });
    }

    if (sidebarBackdrop && sidebar) {
        sidebarBackdrop.addEventListener("click", function () {
            if (isMobileViewport()) {
                setSidebarCollapsed(true);
            }
        });
    }

    if (typeof mobileMediaQuery.addEventListener === "function") {
        mobileMediaQuery.addEventListener("change", syncSidebarToggleState);
    } else if (typeof mobileMediaQuery.addListener === "function") {
        mobileMediaQuery.addListener(syncSidebarToggleState);
    }

    var profilePage = document.querySelector(".profile-page");
    if (!profilePage) {
        return;
    }

    var profileBaseUrl = profilePage.getAttribute("data-profile-base-url") || window.location.pathname;
    var defaultSection = profilePage.getAttribute("data-default-section") || "profile-info";
    var defaultSectionTitle = profilePage.getAttribute("data-default-section-title") || "Profile";
    var sectionLinks = document.querySelectorAll(".js-profile-section-link[data-section]");
    var sidebarSectionLinks = document.querySelectorAll(".profile-sidebar .js-profile-section-link[data-section]");
    var sectionPanels = document.querySelectorAll("[data-profile-section-panel]");

    // P3 — Progressive enhancement: AJAX-safe section adları və endpoint URL şablonu.
    // Atribut boş olarsa AJAX yolu deaktivləşir, brauzer normal naviqasiya edir.
    var ajaxSectionsRaw = profilePage.getAttribute("data-ajax-sections") || "";
    var ajaxSafeSections = ajaxSectionsRaw
        .split(",")
        .map(function (s) { return s.trim(); })
        .filter(function (s) { return !!s; });
    var sectionFragmentUrlTemplate = profilePage.getAttribute("data-section-fragment-url") || "";
    var badgesUrl = profilePage.getAttribute("data-badges-url") || "";
    var sectionsHost = document.getElementById("profileSectionsContainer");
    var ajaxLoadInFlight = null; // AbortController, ya da null
    var badgesRefreshInFlight = null;

    // P3-extra — Sidebar badge-lərini API-dən yenilə. Fail-soft: səhv olarsa
    // mövcud DOM-u dəyişmə, naviqasiyanı pozma. Yalnız mövcud span-ları
    // yenilə (data-badge-key="<key>"). Yeni badge yaratmırıq — count 0-dan
    // böyüyə dəyişərsə, tam reload-da göstəriləcək (kənar hal, qəbul edilən).
    function refreshBadges() {
        if (!badgesUrl || typeof window.fetch !== "function") {
            return;
        }
        if (badgesRefreshInFlight) {
            try { badgesRefreshInFlight.abort(); } catch (e) { /* ignore */ }
        }
        var controller = (typeof AbortController === "function") ? new AbortController() : null;
        badgesRefreshInFlight = controller;
        var opts = {
            credentials: "same-origin",
            headers: { "Accept": "application/json", "X-Requested-With": "XMLHttpRequest" }
        };
        if (controller) { opts.signal = controller.signal; }
        fetch(badgesUrl, opts)
            .then(function (resp) {
                if (!resp.ok) { throw new Error("badges_http_" + resp.status); }
                return resp.json();
            })
            .then(function (payload) {
                if (!payload || payload.ok !== true || !payload.badges) {
                    return;
                }
                var badges = payload.badges;
                Object.keys(badges).forEach(function (key) {
                    var value = badges[key];
                    var nodes = document.querySelectorAll(
                        '.profile-sidebar [data-badge-key="' + key + '"]'
                    );
                    nodes.forEach(function (node) {
                        if (value && value > 0) {
                            node.textContent = String(value);
                            node.style.display = "";
                        } else {
                            // Sıfır olduqda gizlət (DOM-dan silmirik — ölçü stabil qalır).
                            node.textContent = "";
                            node.style.display = "none";
                        }
                    });
                });
            })
            .catch(function () { /* fail-soft */ })
            .then(function () {
                if (badgesRefreshInFlight === controller) {
                    badgesRefreshInFlight = null;
                }
            });
    }
    var sectionTitle = document.getElementById("profileSectionTitle");
    var createExamModal = document.getElementById("createExamModal");
    var createExamModalBody = document.getElementById("createExamModalBody");
    var closeCreateExamModalBtn = document.getElementById("closeCreateExamModal");
    var createExamSubmitInFlight = false;
    var sidebarMenuGroups = [];

    function syncSidebarMenuGroupLayout(group) {
        if (!group) {
            return;
        }

        var items = group.querySelector(".sidebar-menu-group-items");
        if (!items) {
            return;
        }

        group.style.setProperty("--sidebar-group-open-height", String(items.scrollHeight) + "px");
    }

    function syncAllSidebarMenuGroupLayouts() {
        sidebarMenuGroups.forEach(syncSidebarMenuGroupLayout);
    }

    function setSidebarMenuGroupState(group, isOpen) {
        if (!group) {
            return;
        }
        syncSidebarMenuGroupLayout(group);
        group.classList.toggle("is-open", isOpen);
        var toggle = group.querySelector(".sidebar-menu-group-toggle");
        if (toggle) {
            toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
        }
        window.requestAnimationFrame(function () {
            syncSidebarMenuGroupLayout(group);
        });
    }

    function openSidebarMenuGroupForSection(section) {
        if (!section || !sidebarMenuGroups.length) {
            return;
        }
        var sectionLink = sidebar
            ? sidebar.querySelector('.js-profile-section-link[data-section="' + section + '"]')
            : null;
        if (!sectionLink) {
            return;
        }

        var targetGroup = sectionLink.closest(".sidebar-menu-group");
        if (!targetGroup) {
            return;
        }

        setSidebarMenuGroupState(targetGroup, true);
    }

    function initSidebarAccordionMenu() {
        if (!sidebar || sidebar.getAttribute("data-accordion-ready") === "1") {
            return;
        }
        var menu = sidebar.querySelector(".sidebar-menu");
        if (!menu) {
            return;
        }

        var originalChildren = Array.from(menu.children);
        if (!originalChildren.length) {
            return;
        }

        menu.innerHTML = "";
        var currentGroupItems = null;
        var groupIndex = 0;

        originalChildren.forEach(function (node) {
            if (node.classList && node.classList.contains("sidebar-menu-group-label")) {
                var isStaticGroup = node.getAttribute("data-sidebar-static-group") === "1";
                if (isStaticGroup) {
                    currentGroupItems = null;
                    menu.appendChild(node);
                    return;
                }

                groupIndex += 1;
                var group = document.createElement("li");
                group.className = "sidebar-menu-group";
                if (node.classList.contains("sidebar-menu-group-label--bottom")) {
                    group.classList.add("sidebar-menu-group--bottom");
                }

                var toggle = document.createElement("button");
                toggle.type = "button";
                toggle.className = "sidebar-menu-group-toggle";
                toggle.innerHTML =
                    '<span class="sidebar-menu-group-title"></span>' +
                    '<i class="fas fa-chevron-down sidebar-menu-group-caret" aria-hidden="true"></i>';

                var titleNode = toggle.querySelector(".sidebar-menu-group-title");
                if (titleNode) {
                    titleNode.textContent = (node.textContent || "").trim();
                }

                var groupItems = document.createElement("ul");
                groupItems.className = "sidebar-menu-group-items";
                groupItems.id = "profileSidebarGroup" + String(groupIndex);

                toggle.setAttribute("aria-controls", groupItems.id);
                toggle.setAttribute("aria-expanded", "false");

                group.appendChild(toggle);
                group.appendChild(groupItems);
                menu.appendChild(group);

                currentGroupItems = groupItems;
                return;
            }

            if (currentGroupItems) {
                currentGroupItems.appendChild(node);
            } else {
                menu.appendChild(node);
            }
        });

        sidebarMenuGroups = Array.from(menu.querySelectorAll(".sidebar-menu-group"));
        if (!sidebarMenuGroups.length) {
            sidebar.setAttribute("data-accordion-ready", "1");
            return;
        }

        var hasOpenGroup = false;
        sidebarMenuGroups.forEach(function (group) {
            var hasActiveLink = Boolean(group.querySelector(".js-profile-section-link.active"));
            setSidebarMenuGroupState(group, hasActiveLink);
            hasOpenGroup = hasOpenGroup || hasActiveLink;

            var toggle = group.querySelector(".sidebar-menu-group-toggle");
            if (!toggle) {
                return;
            }
            toggle.addEventListener("click", function () {
                setSidebarMenuGroupState(group, !group.classList.contains("is-open"));
            });
        });

        if (!hasOpenGroup) {
            setSidebarMenuGroupState(sidebarMenuGroups[0], true);
        }

        syncAllSidebarMenuGroupLayouts();
        sidebar.setAttribute("data-accordion-ready", "1");
    }

    window.addEventListener("resize", syncAllSidebarMenuGroupLayouts);

    function resolveSectionFromUrl() {
        try {
            var params = new URLSearchParams(window.location.search);
            return params.get("section") || defaultSection;
        } catch (error) {
            return defaultSection;
        }
    }

    // P3 — Lazy load helpers.
    function isAjaxSafeSection(section) {
        return ajaxSafeSections.indexOf(section) !== -1
            && sectionFragmentUrlTemplate
            && sectionsHost
            && typeof window.fetch === "function";
    }

    function buildSectionFragmentUrl(section) {
        // Backend URL şablonunda `__SECTION__` yer-tutucusu var.
        return sectionFragmentUrlTemplate.replace("__SECTION__", encodeURIComponent(section));
    }

    function updateSidebarActiveState(section) {
        sidebarSectionLinks.forEach(function (link) {
            var isMatch = link.getAttribute("data-section") === section;
            link.classList.toggle("active", isMatch);
            if (isMatch && sectionTitle) {
                sectionTitle.textContent = link.getAttribute("data-title") || defaultSectionTitle;
            }
        });
        openSidebarMenuGroupForSection(section);
    }

    function pushSectionUrl(section) {
        if (!window.history || !window.history.pushState) {
            return;
        }
        try {
            var nextUrl = new URL(profileBaseUrl, window.location.origin);
            nextUrl.searchParams.set("section", section);
            window.history.pushState({ section: section, ajax: true }, "", nextUrl.pathname + nextUrl.search);
        } catch (e) { /* ignore */ }
    }

    function extractSectionFromHtml(html, section) {
        try {
            // DOMParser server-render edilmiş tam HTML sənədini parse edir
            // (sections_api.py full profile.html qaytarır, sonra biz panel-i çıxarırıq).
            // Fallback olaraq, parse uğursuz olarsa, div+innerHTML üsulunu istifadə edirik.
            var doc = null;
            if (typeof window.DOMParser === "function") {
                try {
                    doc = new window.DOMParser().parseFromString(html, "text/html");
                } catch (e) { doc = null; }
            }
            var root = doc || (function () {
                var tmp = document.createElement("div");
                tmp.innerHTML = html;
                return tmp;
            })();
            var selector = '[data-profile-section-panel="' + section + '"]';
            return root.querySelector(selector);
        } catch (e) {
            return null;
        }
    }

    /**
     * AJAX swap-dan sonra panel daxilindəki <script> teqlərini yenidən
     * yaradıb DOM-a daxil et — innerHTML/replaceChild script-ləri execute
     * etmir, ona görə bizim həll əl ilə cloneScripts edib hostu run edir.
     * Bu olmadan notifications/posts/statistics və s. section-ların
     * inline JS-i işləmir → content görünmür və ya boş qalır.
     *
     * CSP qeydi: brauzer DOMParser-də parse olunan script-lərdən nonce
     * atributunu təhlükəsizlik səbəbi ilə silir. Bu səbəbdən cari sənədin
     * canlı nonce-unu profile.html root elementindəki `data-csp-nonce`
     * atributundan götürüb yeni script-lərə tətbiq edirik.
     */
    function getDocumentCspNonce() {
        if (profilePage) {
            var n = profilePage.getAttribute("data-csp-nonce");
            if (n) { return n; }
        }
        // Fallback: any script with nonce already in document.
        var anyScript = document.querySelector("script[nonce]");
        if (anyScript) {
            return anyScript.nonce || anyScript.getAttribute("nonce") || "";
        }
        return "";
    }

    function executeInlineScripts(panel) {
        if (!panel) {
            return;
        }
        var cspNonce = getDocumentCspNonce();
        var scripts = panel.querySelectorAll("script");
        scripts.forEach(function (oldScript) {
            var newScript = document.createElement("script");
            // Atributları köçür (type, src, async, defer, vb.) — nonce istisna,
            // çünki DOMParser onu silmiş ola bilər; aşağıda canlı dəyəri qoyuruq.
            for (var i = 0; i < oldScript.attributes.length; i++) {
                var attr = oldScript.attributes[i];
                if (attr.name === "nonce") { continue; }
                try { newScript.setAttribute(attr.name, attr.value); } catch (e) { /* ignore */ }
            }
            // Inline məzmun
            if (oldScript.textContent) {
                newScript.textContent = oldScript.textContent;
            }
            // CSP nonce — cari sənədin canlı dəyərini istifadə et.
            if (cspNonce) {
                try {
                    newScript.setAttribute("nonce", cspNonce);
                    newScript.nonce = cspNonce;
                } catch (e) { /* ignore */ }
            }
            oldScript.parentNode.replaceChild(newScript, oldScript);
        });
    }

    /**
     * AJAX-la dəyişdirilən section-un script-lərini yenidən işə salmaq üçün
     * universal hook. profile.html-də bütün `extraJs`-də olan external
     * script-lər `DOMContentLoaded`-a bağlıdır və AJAX swap zamanı yenidən
     * işə düşmür → form və düymələr "ölü" olur. Həll: AJAX-dan sonra:
     *  1. Custom event göndər ki, ehtiyac duyan script-lər dinləsin.
     *  2. window.EMSProfileReinit() funksiyaları varsa onları çağır.
     *  3. Bootstrap select və debounce search kimi geniş istifadə olunan
     *     bind-ləri panel daxilində yenidən qur.
     */
    function notifySectionLoaded(section, panel) {
        try {
            var ev = new CustomEvent("profile:section:loaded", {
                detail: { section: section, panel: panel },
                bubbles: true,
                cancelable: false
            });
            document.dispatchEvent(ev);
            if (panel) {
                panel.dispatchEvent(ev);
            }
        } catch (e) { /* ignore */ }

        // Geriyə uyğunluq: registered re-init helper-lərini çağır.
        try {
            if (window.EMSProfileReinitHooks && typeof window.EMSProfileReinitHooks === "object") {
                Object.keys(window.EMSProfileReinitHooks).forEach(function (key) {
                    var hook = window.EMSProfileReinitHooks[key];
                    if (typeof hook === "function") {
                        try { hook(panel, section); } catch (err) { /* ignore */ }
                    }
                });
            }
        } catch (e) { /* ignore */ }

        // Generic re-bind-lər — panel daxilində.
        try { rebindCommonControls(panel); } catch (e) { /* ignore */ }
    }

    /**
     * Section panel daxilindəki ümumi UI kontrollarını yenidən qoş.
     * Yalnız mövcud script API-lərini çağırır — heç bir yeni davranış
     * gətirmir.
     */
    function rebindCommonControls(panel) {
        if (!panel) { return; }

        // Bootstrap select wrappers.
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.init === "function") {
            try { window.EMSBootstrapSelect.init(panel); } catch (e) { /* ignore */ }
        }

        // Bizim öz profile-spesifik debounce search.
        try { initDebouncedSearchForms(); } catch (e) { /* ignore */ }

        // Qlobal debounce search forms (base.html-də yüklənir).
        if (window.EMSDebouncedSearchForms && typeof window.EMSDebouncedSearchForms.init === "function") {
            try { window.EMSDebouncedSearchForms.init(panel); } catch (e) { /* ignore */ }
        }

        // Pagination — varsa init et.
        if (window.EMSPagination && typeof window.EMSPagination.init === "function") {
            try { window.EMSPagination.init(panel); } catch (e) { /* ignore */ }
        }
    }

    function showSectionLoading() {
        if (sectionsHost) {
            sectionsHost.setAttribute("aria-busy", "true");
            sectionsHost.classList.add("is-loading");
        }
    }

    function clearSectionLoading() {
        if (sectionsHost) {
            sectionsHost.removeAttribute("aria-busy");
            sectionsHost.classList.remove("is-loading");
        }
    }

    /**
     * AJAX-load the given section. Returns a Promise that resolves to true on
     * success (DOM was swapped) or false on any failure (caller should fall
     * back to a full page navigation).
     */
    function tryAjaxLoadSection(section, options) {
        options = options || {};
        if (!isAjaxSafeSection(section)) {
            return Promise.resolve(false);
        }
        // Cancel any in-flight load.
        if (ajaxLoadInFlight) {
            try { ajaxLoadInFlight.abort(); } catch (e) { /* ignore */ }
        }
        var controller = (typeof AbortController === "function") ? new AbortController() : null;
        ajaxLoadInFlight = controller;
        showSectionLoading();

        var fetchOpts = {
            credentials: "same-origin",
            headers: {
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            }
        };
        if (controller) {
            fetchOpts.signal = controller.signal;
        }

        return fetch(buildSectionFragmentUrl(section), fetchOpts)
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("http_" + response.status);
                }
                return response.json();
            })
            .then(function (payload) {
                if (!payload || payload.ok !== true || !payload.html) {
                    throw new Error("bad_payload");
                }
                var node = extractSectionFromHtml(payload.html, section);
                if (!node) {
                    throw new Error("section_not_in_response");
                }
                node.classList.add("is-active");
                // ƏVVƏLCƏ host-dakı bütün REAL (placeholder olmayan) panel-ləri
                // sil — əks halda əvvəlki bölmə DOM-da qalır və üst-üstə düşür.
                // Eyni zamanda hədəf section-un placeholder-ini də sil ki,
                // dublikat olmasın.
                var oldPanels = sectionsHost.querySelectorAll("[data-profile-section-panel]");
                oldPanels.forEach(function (p) {
                    if (p.parentNode) {
                        p.parentNode.removeChild(p);
                    }
                });
                sectionsHost.appendChild(node);
                // Digər allowed section-lar üçün placeholder-ləri yenidən qur ki,
                // setActiveSection / DOM query-lər doğru işləsin.
                var responseDoc = (function () {
                    try {
                        return new window.DOMParser().parseFromString(payload.html, "text/html");
                    } catch (e) { return null; }
                })();
                if (responseDoc) {
                    var responsePanels = responseDoc.querySelectorAll("[data-profile-section-panel]");
                    responsePanels.forEach(function (p) {
                        var key = p.getAttribute("data-profile-section-panel");
                        if (!key || key === section) { return; }
                        if (sectionsHost.querySelector('[data-profile-section-panel="' + key + '"]')) {
                            return;
                        }
                        // Placeholder klonu (boş, hidden) — script-siz.
                        var ph = document.createElement("section");
                        ph.className = "profile-section-panel profile-section-placeholder";
                        ph.setAttribute("data-profile-section-panel", key);
                        ph.setAttribute("aria-hidden", "true");
                        ph.hidden = true;
                        sectionsHost.appendChild(ph);
                    });
                }
                // Inline script-ləri DOM-a yenidən qoş ki, section-un öz JS-i
                // (notif modal, statistika chart, və s.) işləsin.
                try { executeInlineScripts(node); } catch (e) { /* ignore */ }
                // Universal hook — external script-lərin re-bind etməsi üçün.
                try { notifySectionLoaded(section, node); } catch (e) { /* ignore */ }
                // Sidebar/Title/URL yenilə
                updateSidebarActiveState(section);
                if (options.updateUrl !== false) {
                    pushSectionUrl(section);
                }
                // sectionPanels referansını təzələ ki, gələcək setActiveSection-larda işləsin.
                sectionPanels = document.querySelectorAll("[data-profile-section-panel]");
                // Mobile-də sidebar-ı bağla.
                if (typeof isMobileViewport === "function" && isMobileViewport()) {
                    setSidebarCollapsed(true);
                }
                // P3-extra — badge-ləri arxa planda yenilə. Səhv olarsa naviqasiya
                // pozulmur (fail-soft); badge refresh məcburi deyil.
                try { refreshBadges(); } catch (e) { /* ignore */ }
                return true;
            })
            .catch(function (err) {
                // Fail soft — caller will full-page navigate.
                return false;
            })
            .then(function (result) {
                clearSectionLoading();
                if (ajaxLoadInFlight === controller) {
                    ajaxLoadInFlight = null;
                }
                return result;
            });
    }

    function setActiveSection(section, updateUrl) {
        // P2 cleanup — Hədəf paneli olmadıqda mövcud "is-active"-i ləğv etmə,
        // brauzeri təbii naviqasiyaya burax. Köhnə davranış cari paneldən
        // is-active-i bir an üçün silirdi (kiçik flash).
        //
        // Vacib: server-side profile.html yalnız BİR section-u real content ilə
        // render edir; digər allowed_sections üçün boş `profile-section-placeholder`
        // qoyur. Əgər hədəf panel yalnız placeholder-dirsə (real content yox),
        // setActiveSection FALSE qaytarmalıdır ki, çağıran tam naviqasiyaya
        // keçə bilsin — əks halda boş content göstərilir və content yalnız
        // manual refresh-də gəlir.
        var hasTargetPanel = false;
        var targetIsPlaceholder = false;
        sectionPanels.forEach(function (panel) {
            if (panel.getAttribute("data-profile-section-panel") === section) {
                hasTargetPanel = true;
                if (panel.classList.contains("profile-section-placeholder")) {
                    targetIsPlaceholder = true;
                }
            }
        });

        if (!hasTargetPanel || targetIsPlaceholder) {
            return false;
        }

        sectionPanels.forEach(function (panel) {
            var isMatch = panel.getAttribute("data-profile-section-panel") === section;
            panel.classList.toggle("is-active", isMatch);
        });

        sidebarSectionLinks.forEach(function (link) {
            var isMatch = link.getAttribute("data-section") === section;
            link.classList.toggle("active", isMatch);
            if (isMatch && sectionTitle) {
                sectionTitle.textContent = link.getAttribute("data-title") || defaultSectionTitle;
            }
        });
        openSidebarMenuGroupForSection(section);

        if (updateUrl && window.history && window.history.pushState) {
            var nextUrl = new URL(profileBaseUrl, window.location.origin);
            nextUrl.searchParams.set("section", section);
            window.history.pushState({ section: section }, "", nextUrl.pathname + nextUrl.search);
        }

        return true;
    }

    function openCreatePostModal() {
        if (typeof window.openCreatePostModal === "function") {
            window.openCreatePostModal();
            return;
        }

        // Fallback: if create modal is already in DOM, open it even if bridge function is not ready yet.
        var createModal = document.getElementById("createModal");
        if (createModal) {
            ensureModalRoot(createModal);
            createModal.classList.add("active");
            document.body.style.overflow = "hidden";
            var createTitle = document.getElementById("createTitle");
            if (createTitle) {
                createTitle.focus();
            }
        }
    }

    function ensureModalRoot(modal) {
        if (!modal || !modal.parentElement || modal.parentElement === document.body) {
            return;
        }
        document.body.appendChild(modal);
    }

    function createExamModalLoadingMarkup() {
        return '<div class="create-exam-modal-loading">Form yüklənir...</div>';
    }

    function buildCreateExamModalUrl(createExamUrl) {
        try {
            var url = new URL(createExamUrl, window.location.origin);
            url.searchParams.set("modal", "1");
            return url.pathname + url.search;
        } catch (error) {
            return createExamUrl + (createExamUrl.indexOf("?") === -1 ? "?modal=1" : "&modal=1");
        }
    }

    function initCreateExamSearchableSelect(form, config) {
        if (!form || !config) {
            return null;
        }

        var hiddenSelect = form.querySelector('select[name="' + config.selectName + '"]');
        var listContainer = form.querySelector(config.listSelector);
        var searchInput = form.querySelector(config.searchSelector);
        var counter = form.querySelector(config.counterSelector);
        var optionMap = Object.create(null);
        var checkboxMap = Object.create(null);
        var selectionChangeHandlers = [];
        var itemToggleHandlers = [];

        if (!hiddenSelect || !listContainer) {
            return null;
        }

        function updateCounter() {
            if (counter) {
                counter.textContent = String(hiddenSelect.selectedOptions.length);
            }
        }

        function getSelectedValues() {
            return Array.from(hiddenSelect.selectedOptions || []).map(function (option) {
                return String(option.value);
            });
        }

        function notifySelectionChange(meta) {
            selectionChangeHandlers.forEach(function (handler) {
                handler(meta || {});
            });
        }

        function notifyItemToggle(meta) {
            itemToggleHandlers.forEach(function (handler) {
                handler(meta || {});
            });
        }

        function setValueSelected(value, isSelected, source) {
            var normalizedValue = String(value);
            var option = optionMap[normalizedValue];
            if (!option || option.selected === isSelected) {
                return false;
            }

            option.selected = isSelected;
            var checkbox = checkboxMap[normalizedValue];
            if (checkbox) {
                checkbox.checked = isSelected;
            }

            updateCounter();
            var meta = {
                value: normalizedValue,
                isSelected: isSelected,
                source: source || "programmatic"
            };
            notifyItemToggle(meta);
            notifySelectionChange(meta);
            return true;
        }

        function renderList() {
            var options = Array.from(hiddenSelect.options || []);
            listContainer.innerHTML = "";
            checkboxMap = Object.create(null);
            optionMap = Object.create(null);

            if (!options.length) {
                listContainer.innerHTML = '<div class="create-exam-list-empty">Məlumat tapılmadı.</div>';
                updateCounter();
                return;
            }

            options.forEach(function (option) {
                optionMap[String(option.value)] = option;

                var row = document.createElement("div");
                row.className = "create-exam-list-item";
                row.setAttribute("data-search", (option.textContent || "").toLowerCase());

                var checkboxId = "create_exam_" + config.selectName + "_" + option.value;

                row.innerHTML = '' +
                    '<input type="checkbox" class="create-exam-item-checkbox" id="' + checkboxId + '"' +
                    (option.selected ? " checked" : "") + ">" +
                    '<label class="create-exam-item-label" for="' + checkboxId + '"></label>';

                var checkbox = row.querySelector(".create-exam-item-checkbox");
                var label = row.querySelector(".create-exam-item-label");

                if (label) {
                    label.textContent = option.textContent || "";
                }

                if (checkbox) {
                    checkboxMap[String(option.value)] = checkbox;
                    checkbox.addEventListener("change", function () {
                        setValueSelected(option.value, checkbox.checked, "user");
                    });
                }

                row.addEventListener("click", function (event) {
                    if (!checkbox) {
                        return;
                    }
                    if (event.target === checkbox || event.target === label) {
                        return;
                    }
                    var nextChecked = !checkbox.checked;
                    checkbox.checked = nextChecked;
                    setValueSelected(option.value, nextChecked, "user");
                });

                listContainer.appendChild(row);
            });

            updateCounter();
        }

        function filterList(query) {
            var normalizedQuery = (query || "").toLowerCase();
            var rows = listContainer.querySelectorAll(".create-exam-list-item");
            rows.forEach(function (row) {
                var haystack = row.getAttribute("data-search") || "";
                row.style.display = haystack.indexOf(normalizedQuery) !== -1 ? "flex" : "none";
            });
        }

        if (searchInput) {
            searchInput.addEventListener("input", function () {
                filterList(searchInput.value);
            });
        }

        renderList();
        if (searchInput && searchInput.value) {
            filterList(searchInput.value);
        }

        return {
            getSelectedValues: getSelectedValues,
            setValueSelected: setValueSelected,
            onSelectionChange: function (handler) {
                if (typeof handler === "function") {
                    selectionChangeHandlers.push(handler);
                }
            },
            onItemToggle: function (handler) {
                if (typeof handler === "function") {
                    itemToggleHandlers.push(handler);
                }
            }
        };
    }

    function parseCreateExamGroupStudentMap(form) {
        if (!form) {
            return {};
        }

        var mapScript = form.querySelector("#createExamGroupStudentMap");
        if (!mapScript || !mapScript.textContent) {
            return {};
        }

        try {
            var parsedMap = JSON.parse(mapScript.textContent);
            if (!parsedMap || typeof parsedMap !== "object") {
                return {};
            }
            return parsedMap;
        } catch (error) {
            return {};
        }
    }

    function initCreateExamGroupUserSelectionSync(form, groupSelector, userSelector) {
        if (!form || !groupSelector || !userSelector) {
            return;
        }

        var groupStudentMap = parseCreateExamGroupStudentMap(form);
        if (!Object.keys(groupStudentMap).length) {
            return;
        }

        var manuallyDeselectedUserIds = new Set();
        var previousAutoSelectedUserIds = new Set();

        function getAutoSelectedUserIds() {
            var selectedGroupIds = groupSelector.getSelectedValues();
            var userIds = new Set();

            selectedGroupIds.forEach(function (groupId) {
                var mappedUserIds = groupStudentMap[String(groupId)] || [];
                mappedUserIds.forEach(function (userId) {
                    userIds.add(String(userId));
                });
            });

            return userIds;
        }

        function syncUsersFromSelectedGroups() {
            var autoSelectedUserIds = getAutoSelectedUserIds();
            var staleManualIds = [];

            manuallyDeselectedUserIds.forEach(function (userId) {
                if (!autoSelectedUserIds.has(userId)) {
                    staleManualIds.push(userId);
                }
            });
            staleManualIds.forEach(function (userId) {
                manuallyDeselectedUserIds.delete(userId);
            });

            previousAutoSelectedUserIds.forEach(function (userId) {
                if (!autoSelectedUserIds.has(userId)) {
                    userSelector.setValueSelected(userId, false, "group-sync");
                }
            });

            autoSelectedUserIds.forEach(function (userId) {
                if (!manuallyDeselectedUserIds.has(userId)) {
                    userSelector.setValueSelected(userId, true, "group-sync");
                }
            });

            previousAutoSelectedUserIds = new Set(autoSelectedUserIds);
        }

        groupSelector.onSelectionChange(function () {
            syncUsersFromSelectedGroups();
        });

        userSelector.onItemToggle(function (meta) {
            if (!meta || meta.source !== "user") {
                return;
            }

            var userId = String(meta.value || "");
            if (!userId) {
                return;
            }

            var autoSelectedUserIds = getAutoSelectedUserIds();
            if (!autoSelectedUserIds.has(userId)) {
                return;
            }

            if (meta.isSelected) {
                manuallyDeselectedUserIds.delete(userId);
            } else {
                manuallyDeselectedUserIds.add(userId);
            }
        });

        var initialSelectedUserIds = new Set(userSelector.getSelectedValues());
        var initialAutoSelectedUserIds = getAutoSelectedUserIds();
        initialAutoSelectedUserIds.forEach(function (userId) {
            if (!initialSelectedUserIds.has(userId)) {
                manuallyDeselectedUserIds.add(userId);
            }
        });
        previousAutoSelectedUserIds = new Set(initialAutoSelectedUserIds);

        syncUsersFromSelectedGroups();
    }

    function initCreateExamAccessToggle(form) {
        if (!form) {
            return;
        }

        var isPublicCheckbox = form.querySelector('input[name="is_public"]');
        var accessBlock = form.querySelector("#createExamAccessRestrictions");
        if (!isPublicCheckbox || !accessBlock) {
            return;
        }

        function syncAccessBlock() {
            accessBlock.classList.toggle("is-hidden", isPublicCheckbox.checked);
        }

        syncAccessBlock();
        isPublicCheckbox.addEventListener("change", syncAccessBlock);
    }

    function initCreateExamTypePicker(form) {
        if (!form) {
            return;
        }

        var nativeSelect = form.querySelector('select[name="exam_type"]');
        var picker = form.querySelector("[data-create-exam-type-picker]");
        if (!nativeSelect || !picker) {
            return;
        }

        var typeOptions = picker.querySelectorAll(".js-create-exam-type-option");
        var paintCheckbox = form.querySelector('input[name="enable_paint"]');
        var paintLabel = paintCheckbox ? paintCheckbox.closest(".modal-check-label--paint") : null;
        var randomQuestionGroup = form.querySelector("[data-random-question-group], [data-test-random-question-group]");
        var randomQuestionInput = form.querySelector('input[name="random_question_count"]');

        function syncPaintAvailability(examType) {
            if (randomQuestionGroup) {
                randomQuestionGroup.hidden = false;
            }
            if (randomQuestionInput) {
                randomQuestionInput.disabled = false;
            }
            if (!paintCheckbox) {
                return;
            }

            var isWritten = examType === "written";
            if (!isWritten) {
                paintCheckbox.checked = false;
            }
            paintCheckbox.disabled = !isWritten;

            if (paintLabel) {
                paintLabel.classList.toggle("is-disabled", !isWritten);
            }
        }

        function syncPickerFromSelect() {
            var selectedType = nativeSelect.value || "test";
            typeOptions.forEach(function (option) {
                option.checked = option.value === selectedType;
            });
            syncPaintAvailability(selectedType);
        }

        typeOptions.forEach(function (option) {
            option.addEventListener("change", function () {
                if (!option.checked) {
                    return;
                }

                nativeSelect.value = option.value;
                syncPaintAvailability(option.value);
                nativeSelect.dispatchEvent(new Event("change", { bubbles: true }));
            });
        });

        nativeSelect.addEventListener("change", syncPickerFromSelect);
        syncPickerFromSelect();
    }

    function showCreateExamTemplateInfo(form, templateSelect) {
        var infoPanel = form.querySelector("#modalSupervisionTemplateInfo");
        var infoTitle = form.querySelector("#modalSupervisionTemplateInfoTitle");
        var infoDesc = form.querySelector("#modalSupervisionTemplateInfoDesc");
        var infoFeatures = form.querySelector("#modalSupervisionTemplateInfoFeatures");
        if (!infoPanel || !templateSelect) {
            return;
        }

        var val = templateSelect.value;
        var templates =
            typeof window.MODAL_SUPERVISION_TPL_INFO === "object"
                ? window.MODAL_SUPERVISION_TPL_INFO
                : {};
        var borderColors = {
            custom: "#6c757d",
            light: "#28a745",
            medium: "#ffc107",
            strict: "#dc3545"
        };
        var tpl = templates[val];
        if (!tpl || val === "custom") {
            infoPanel.style.display = "none";
            return;
        }
        infoTitle.textContent = tpl.title || "";
        infoDesc.textContent = tpl.desc || "";
        infoFeatures.innerHTML = "";
        (tpl.features || []).forEach(function (f) {
            var li = document.createElement("li");
            li.textContent = f;
            infoFeatures.appendChild(li);
        });
        infoPanel.style.borderLeftColor = borderColors[val] || "#007bff";
        infoPanel.style.display = "block";
    }

    function initCreateExamSupervisionToggle(form) {
        if (!form) {
            return;
        }

        var enabledCheckbox = form.querySelector('input[name="supervision_enabled"]');
        var settingsBlock = form.querySelector("#modalSupervisionSettings");
        var templateSelect = form.querySelector('select[name="supervision_template"]');
        var customBlock = form.querySelector("#modalSupervisionCustomSettings");

        if (!enabledCheckbox || !settingsBlock) {
            return;
        }

        function syncSupervisionSettings() {
            if (enabledCheckbox.checked) {
                settingsBlock.style.display = "block";
                settingsBlock.removeAttribute("hidden");
            } else {
                settingsBlock.style.display = "none";
            }
        }

        function syncSupervisionCustom() {
            if (!templateSelect || !customBlock) {
                return;
            }
            customBlock.style.display = templateSelect.value === "custom" ? "block" : "none";
        }

        syncSupervisionSettings();
        enabledCheckbox.addEventListener("change", syncSupervisionSettings);
        enabledCheckbox.addEventListener("click", function () {
            setTimeout(syncSupervisionSettings, 0);
        });

        if (templateSelect) {
            syncSupervisionCustom();
            templateSelect.addEventListener("change", syncSupervisionCustom);
            templateSelect.addEventListener("change", function () {
                showCreateExamTemplateInfo(form, templateSelect);
            });
            showCreateExamTemplateInfo(form, templateSelect);
        }

        // Initialize Bootstrap selects inside supervision settings
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.init === "function") {
            window.EMSBootstrapSelect.init(settingsBlock);
        }
    }

    function bindCreateExamModalForm() {
        if (!createExamModalBody) {
            return;
        }

        var closeInlineBtn = createExamModalBody.querySelector(".js-close-create-exam");
        if (closeInlineBtn) {
            closeInlineBtn.addEventListener("click", function () {
                closeCreateExamModal(true);
            });
        }

        var form = createExamModalBody.querySelector("#createExamModalForm");
        if (!form) {
            return;
        }

        initCreateExamTypePicker(form);
        initCreateExamAccessToggle(form);
        initCreateExamSupervisionToggle(form);
        var groupSelector = initCreateExamSearchableSelect(form, {
            selectName: "allowed_groups",
            listSelector: "#createExamGroupsList",
            searchSelector: "#createExamGroupsSearch",
            counterSelector: "#createExamGroupsCount"
        });
        var userSelector = initCreateExamSearchableSelect(form, {
            selectName: "allowed_users",
            listSelector: "#createExamUsersList",
            searchSelector: "#createExamUsersSearch",
            counterSelector: "#createExamUsersCount"
        });
        initCreateExamGroupUserSelectionSync(form, groupSelector, userSelector);

        form.addEventListener("submit", async function (event) {
            event.preventDefault();
            if (createExamSubmitInFlight) {
                return;
            }

            createExamSubmitInFlight = true;
            var submitBtn = form.querySelector('button[type="submit"]');
            var originalSubmitText = submitBtn ? submitBtn.innerHTML : "";
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "Yaradılır...";
            }

            try {
                var response = await fetch(form.getAttribute("action"), {
                    method: "POST",
                    body: new FormData(form),
                    headers: {
                        "X-Requested-With": "XMLHttpRequest"
                    }
                });

                var contentType = response.headers.get("content-type") || "";
                var redirectTarget = response.url || "";
                if (response.ok && contentType.indexOf("application/json") !== -1) {
                    var data = await response.json();
                    if (data.success) {
                        closeCreateExamModal(true);
                        var nextUrl = new URL(profileBaseUrl, window.location.origin);
                        nextUrl.searchParams.set("section", "my-exams");
                        window.setTimeout(function () {
                            window.location.href = nextUrl.pathname + nextUrl.search;
                        }, 60);
                        return;
                    }
                }

                if (response.ok && response.redirected && redirectTarget) {
                    closeCreateExamModal(true);
                    var redirectedUrl = new URL(profileBaseUrl, window.location.origin);
                    redirectedUrl.searchParams.set("section", "my-exams");
                    window.setTimeout(function () {
                        window.location.href = redirectedUrl.pathname + redirectedUrl.search;
                    }, 60);
                    return;
                }

                if (contentType.indexOf("application/json") !== -1) {
                    var jsonError = await response.json();
                    if (jsonError.html) {
                        createExamModalBody.innerHTML = jsonError.html;
                        bindCreateExamModalForm();
                        return;
                    }
                }

                var html = await response.text();
                createExamModalBody.innerHTML = html || '<div class="create-exam-modal-error">Form yenilənmədi. Yenidən cəhd edin.</div>';
                bindCreateExamModalForm();
            } catch (error) {
                if (createExamModalBody) {
                    createExamModalBody.innerHTML = '<div class="create-exam-modal-error">Xəta baş verdi. Yenidən cəhd edin.</div>';
                }
            } finally {
                createExamSubmitInFlight = false;
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalSubmitText;
                }
            }
        });
    }

    async function openCreateExamModal(createExamUrl) {
        if (!createExamUrl || !createExamModal || !createExamModalBody) {
            return;
        }
        if (
            createExamModal.dataset.createExamLoading === "1" &&
            createExamModal.classList.contains("active")
        ) {
            return;
        }

        ensureModalRoot(createExamModal);
        createExamModal.classList.add("active");
        document.body.style.overflow = "hidden";
        createExamModalBody.innerHTML = createExamModalLoadingMarkup();

        var modalUrl = buildCreateExamModalUrl(createExamUrl);
        createExamModal.dataset.createExamUrl = modalUrl;
        var loadToken = String((Number(createExamModal.dataset.createExamToken) || 0) + 1);
        createExamModal.dataset.createExamToken = loadToken;
        createExamModal.dataset.createExamLoading = "1";

        try {
            var response = await fetch(modalUrl, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                }
            });
            var html = await response.text();
            if (!response.ok) {
                throw new Error("create exam modal load failed");
            }
            if (
                createExamModal.dataset.createExamToken !== loadToken ||
                !createExamModal.classList.contains("active")
            ) {
                return;
            }
            createExamModalBody.innerHTML = html;
            bindCreateExamModalForm();
        } catch (error) {
            if (
                createExamModal.dataset.createExamToken !== loadToken ||
                !createExamModal.classList.contains("active")
            ) {
                return;
            }
            createExamModalBody.innerHTML = '<div class="create-exam-modal-error">Form yüklənmədi. Yenidən cəhd edin.</div>';
        } finally {
            if (createExamModal.dataset.createExamToken === loadToken) {
                createExamModal.dataset.createExamLoading = "0";
            }
        }
    }

    function closeCreateExamModal(resetContent) {
        if (!createExamModal) {
            return;
        }
        createExamModal.classList.remove("active");
        document.body.style.overflow = "";
        // Invalidate any in-flight load so a late fetch cannot repaint the
        // body after the modal has been closed, and clear the loading guard
        // so the next open starts fresh.
        createExamModal.dataset.createExamToken =
            String((Number(createExamModal.dataset.createExamToken) || 0) + 1);
        createExamModal.dataset.createExamLoading = "0";
        if (resetContent && createExamModalBody) {
            createExamModalBody.innerHTML = createExamModalLoadingMarkup();
        }
    }

    if (createExamModal) {
        ensureModalRoot(createExamModal);
    }

    if (closeCreateExamModalBtn) {
        closeCreateExamModalBtn.addEventListener("click", function () {
            closeCreateExamModal(true);
        });
    }

    if (createExamModal) {
        createExamModal.addEventListener("click", function (event) {
            if (event.target === createExamModal) {
                closeCreateExamModal(true);
            }
        });
    }

    window.openCreateExamModal = openCreateExamModal;

    if (!sectionLinks.length || !sectionPanels.length) {
        return;
    }

    initSidebarAccordionMenu();

    sectionLinks.forEach(function (link) {
        link.addEventListener("click", function (event) {
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                return;
            }

            var section = link.getAttribute("data-section");
            if (!section) {
                return;
            }

            if (link.getAttribute("data-force-navigation") === "true") {
                return;
            }

            // P3 — AJAX-safe section üçün lazy load cəhd edirik.
            // Uğursuz olarsa fail-soft → təbii naviqasiya.
            if (isAjaxSafeSection(section)) {
                event.preventDefault();
                tryAjaxLoadSection(section, { updateUrl: true }).then(function (ok) {
                    if (!ok) {
                        // Fallback: tam səhifə naviqasiyası.
                        var nextUrl = new URL(profileBaseUrl, window.location.origin);
                        nextUrl.searchParams.set("section", section);
                        window.location.href = nextUrl.pathname + nextUrl.search;
                    }
                });
                return;
            }

            // Non-AJAX section — köhnə davranış: setActiveSection cəhd, alınmazsa təbii naviqasiya.
            if (setActiveSection(section, true)) {
                event.preventDefault();
                if (isMobileViewport()) {
                    setSidebarCollapsed(true);
                }
            }
        });
    });

    // P3 — Browser back/forward dəstəyi (yalnız AJAX ilə naviqasiya etdiyimiz state-lər üçün).
    window.addEventListener("popstate", function (event) {
        var state = event.state || {};
        var section = state.section;
        if (!section) {
            // URL-dən parse et (AJAX rejimi xaricində daxil olunan səhifə)
            try {
                var params = new URLSearchParams(window.location.search);
                section = params.get("section") || defaultSection;
            } catch (e) {
                section = defaultSection;
            }
        }
        if (!isAjaxSafeSection(section)) {
            // Tam reload kömək edir — köhnə davranışı saxla.
            return;
        }
        tryAjaxLoadSection(section, { updateUrl: false }).then(function (ok) {
            if (!ok) {
                window.location.reload();
            }
        });
    });

    // Any "create post" CTA should always open modal in-place.
    document.addEventListener("click", function (event) {
        var trigger = event.target.closest(".js-open-create-post");
        if (!trigger) {
            return;
        }

        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return;
        }

        event.preventDefault();
        setActiveSection("create-post", true);
        openCreatePostModal();
    });

    document.addEventListener("click", function (event) {
        var trigger = event.target.closest(".js-open-create-exam");
        if (!trigger) {
            return;
        }

        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return;
        }

        event.preventDefault();
        setActiveSection("my-exams", true);
        openCreateExamModal(trigger.getAttribute("data-create-exam-url"));
    });

    var assignedExamInfoBackdrop = document.getElementById("assignedExamInfoBackdrop");
    // Qeyd: close/cancel/start düymələri artıq delegasiya ilə idarə olunur
    // (aşağıda), ona görə birbaşa element referensləri saxlanmır.
    var assignedExamInfoStartBtn = document.getElementById("assignedExamInfoStartBtn");
    var assignedExamInfoExamName = document.getElementById("assignedExamInfoExamName");
    var assignedExamInfoType = document.getElementById("assignedExamInfoType");
    var assignedExamInfoDuration = document.getElementById("assignedExamInfoDuration");
    var assignedExamInfoStart = document.getElementById("assignedExamInfoStart");
    var assignedExamInfoEnd = document.getElementById("assignedExamInfoEnd");
    var assignedExamInfoNote = document.getElementById("assignedExamInfoNote");
    var assignedExamCodeForm = document.getElementById("assignedExamCodeForm");
    var assignedExamCodeSlug = document.getElementById("assignedExamCodeSlug");
    var assignedExamAccessCodeInput = document.getElementById("assignedExamAccessCodeInput");
    var assignedExamCodeError = document.getElementById("assignedExamCodeError");
    var assignedExamModalStartUrl = "";
    var assignedExamModalRequiresCode = false;
    var assignedExamCodeSubmitInFlight = false;

    function setAssignedExamCodeError(message) {
        if (assignedExamAccessCodeInput) {
            assignedExamAccessCodeInput.classList.toggle("is-invalid", Boolean(message));
        }
        if (assignedExamCodeError) {
            assignedExamCodeError.textContent = message || "";
            assignedExamCodeError.hidden = !message;
        }
    }

    function openAssignedExamInfoModal(trigger) {
        // AJAX swap-dan sonra modal yeni DOM elementidir — loader yalnız bir dəfə
        // işlədiyi üçün köhnə referenslər stale olur. Açılış anında təzələ.
        assignedExamInfoBackdrop = document.getElementById("assignedExamInfoBackdrop");
        assignedExamInfoExamName = document.getElementById("assignedExamInfoExamName");
        assignedExamInfoType = document.getElementById("assignedExamInfoType");
        assignedExamInfoDuration = document.getElementById("assignedExamInfoDuration");
        assignedExamInfoStart = document.getElementById("assignedExamInfoStart");
        assignedExamInfoEnd = document.getElementById("assignedExamInfoEnd");
        assignedExamInfoNote = document.getElementById("assignedExamInfoNote");
        assignedExamInfoStartBtn = document.getElementById("assignedExamInfoStartBtn");
        assignedExamCodeForm = document.getElementById("assignedExamCodeForm");
        assignedExamCodeSlug = document.getElementById("assignedExamCodeSlug");
        assignedExamAccessCodeInput = document.getElementById("assignedExamAccessCodeInput");
        assignedExamCodeError = document.getElementById("assignedExamCodeError");

        if (!assignedExamInfoBackdrop || !trigger) {
            return;
        }

        assignedExamModalStartUrl = trigger.getAttribute("data-start-url") || "";
        assignedExamModalRequiresCode = trigger.getAttribute("data-requires-code") === "1";

        if (assignedExamInfoExamName) {
            assignedExamInfoExamName.textContent = trigger.getAttribute("data-exam-title") || "";
        }
        if (assignedExamInfoType) {
            assignedExamInfoType.textContent = trigger.getAttribute("data-exam-type") || "-";
        }
        if (assignedExamInfoDuration) {
            assignedExamInfoDuration.textContent = trigger.getAttribute("data-exam-duration") || "-";
        }
        if (assignedExamInfoStart) {
            assignedExamInfoStart.textContent = trigger.getAttribute("data-exam-start") || "-";
        }
        if (assignedExamInfoEnd) {
            assignedExamInfoEnd.textContent = trigger.getAttribute("data-exam-end") || "-";
        }
        if (assignedExamInfoNote) {
            var noteText = trigger.getAttribute("data-exam-note") || "";
            assignedExamInfoNote.textContent = noteText || "Qeyd yoxdur.";
        }

        if (assignedExamCodeSlug) {
            assignedExamCodeSlug.value = trigger.getAttribute("data-exam-slug") || "";
        }
        if (assignedExamCodeForm) {
            assignedExamCodeForm.classList.toggle("is-hidden", !assignedExamModalRequiresCode);
        }
        if (assignedExamAccessCodeInput) {
            assignedExamAccessCodeInput.value = "";
        }
        setAssignedExamCodeError("");
        if (assignedExamInfoStartBtn) {
            assignedExamInfoStartBtn.textContent = assignedExamModalRequiresCode
                ? "Kodu təsdiqlə və başla"
                : "İmtahana başla";
            assignedExamInfoStartBtn.disabled = false;
        }
        assignedExamCodeSubmitInFlight = false;

        assignedExamInfoBackdrop.classList.add("is-open");
        assignedExamInfoBackdrop.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";

        if (assignedExamModalRequiresCode && assignedExamAccessCodeInput) {
            window.setTimeout(function () {
                assignedExamAccessCodeInput.focus();
            }, 40);
        }
    }

    function closeAssignedExamInfoModal() {
        assignedExamInfoBackdrop = document.getElementById("assignedExamInfoBackdrop");
        if (!assignedExamInfoBackdrop) {
            return;
        }
        assignedExamInfoBackdrop.classList.remove("is-open");
        assignedExamInfoBackdrop.setAttribute("aria-hidden", "true");
        if (!createExamModal || !createExamModal.classList.contains("active")) {
            document.body.style.overflow = "";
        }
    }

    document.addEventListener("click", function (event) {
        var trigger = event.target.closest(".js-open-assigned-exam-modal");
        if (!trigger) {
            return;
        }
        event.preventDefault();
        openAssignedExamInfoModal(trigger);
    });

    // Bağlama/ləğv + kod input — DELEGASİYA (document üzərində bir dəfə).
    // AJAX swap-dan sonra modal yeni element olduğu üçün birbaşa bind "ölü"
    // qalardı; delegasiya cari və gələcək modal elementlərini də tutur.
    document.addEventListener("click", function (event) {
        var backdrop = document.getElementById("assignedExamInfoBackdrop");
        if (backdrop && event.target === backdrop) {
            closeAssignedExamInfoModal();
            return;
        }
        if (event.target.closest && event.target.closest("#assignedExamInfoClose, #assignedExamInfoCancelBtn")) {
            closeAssignedExamInfoModal();
        }
    });
    document.addEventListener("input", function (event) {
        if (event.target && event.target.id === "assignedExamAccessCodeInput") {
            event.target.value = event.target.value.replace(/[^0-9]/g, "");
            setAssignedExamCodeError("");
        }
    });

    async function submitAssignedExamCodeForm() {
        if (!assignedExamCodeForm || !assignedExamAccessCodeInput) {
            return;
        }

        var codeValue = (assignedExamAccessCodeInput.value || "").trim();
        if (!codeValue) {
            setAssignedExamCodeError("İmtahan kodu tələb olunur.");
            assignedExamAccessCodeInput.focus();
            return;
        }

        if (assignedExamCodeSubmitInFlight) {
            return;
        }

        assignedExamCodeSubmitInFlight = true;
        if (assignedExamInfoStartBtn) {
            assignedExamInfoStartBtn.disabled = true;
        }

        try {
            var response = await fetch(assignedExamCodeForm.getAttribute("action"), {
                method: "POST",
                body: new FormData(assignedExamCodeForm),
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                }
            });
            var contentType = response.headers.get("content-type") || "";
            if (contentType.indexOf("application/json") !== -1) {
                var payload = await response.json();
                if (response.ok && payload.success) {
                    window.location.href = payload.redirect_url || assignedExamModalStartUrl || window.location.href;
                    return;
                }
                setAssignedExamCodeError(payload.error || "İmtahana başlamaq mümkün olmadı.");
                return;
            }
            if (response.redirected && response.url) {
                window.location.href = response.url;
                return;
            }
            setAssignedExamCodeError("İmtahana başlamaq mümkün olmadı.");
        } catch (error) {
            setAssignedExamCodeError("İmtahana başlamaq mümkün olmadı.");
        } finally {
            assignedExamCodeSubmitInFlight = false;
            if (assignedExamInfoStartBtn) {
                assignedExamInfoStartBtn.disabled = false;
            }
        }
    }

    // Kod formu submit + "Başla" düyməsi — DELEGASİYA (AJAX-safe, bir dəfə bind).
    document.addEventListener("submit", function (event) {
        if (event.target && event.target.id === "assignedExamCodeForm") {
            event.preventDefault();
            submitAssignedExamCodeForm();
        }
    });
    document.addEventListener("click", function (event) {
        if (!event.target.closest || !event.target.closest("#assignedExamInfoStartBtn")) {
            return;
        }
        if (assignedExamModalRequiresCode) {
            submitAssignedExamCodeForm();
            return;
        }
        if (assignedExamModalStartUrl) {
            window.location.href = assignedExamModalStartUrl;
        }
    });

    function initDebouncedSearchForms() {
        var forms = document.querySelectorAll("form.js-profile-debounce-search");
        forms.forEach(function (form) {
            if (form.getAttribute("data-debounce-ready") === "1") {
                return;
            }

            var input = form.querySelector('input[type="search"]');
            if (!input) {
                return;
            }

            var rawDebounceMs = parseInt(form.getAttribute("data-debounce-ms"), 10);
            var debounceMs = Number.isFinite(rawDebounceMs) && rawDebounceMs >= 0 ? rawDebounceMs : 1000;
            var timerId = null;
            var lastSubmittedValue = (input.value || "").trim();

            function submitSearch() {
                var currentValue = (input.value || "").trim();
                if (currentValue === lastSubmittedValue) {
                    return;
                }
                lastSubmittedValue = currentValue;

                if (typeof form.requestSubmit === "function") {
                    form.requestSubmit();
                    return;
                }
                form.submit();
            }

            input.addEventListener("input", function () {
                window.clearTimeout(timerId);
                timerId = window.setTimeout(submitSearch, debounceMs);
            });

            input.addEventListener("keydown", function (event) {
                if (event.key !== "Enter") {
                    return;
                }
                event.preventDefault();
                window.clearTimeout(timerId);
                submitSearch();
            });

            form.addEventListener("submit", function () {
                window.clearTimeout(timerId);
                lastSubmittedValue = (input.value || "").trim();
            });

            form.setAttribute("data-debounce-ready", "1");
        });
    }

    initDebouncedSearchForms();

    var resolvedSection = resolveSectionFromUrl();
    if (!setActiveSection(resolvedSection, false)) {
        setActiveSection(defaultSection, false);
    }

    window.addEventListener("popstate", function () {
        var section = resolveSectionFromUrl();
        // Əgər AJAX-safe-dirsə, yuxarıdakı AJAX popstate handler-i icra olunur.
        // Burada yalnız non-AJAX hallar üçün setActiveSection cəhd edirik.
        if (isAjaxSafeSection(section)) {
            return;
        }
        if (!setActiveSection(section, false)) {
            // Hədəf section yalnız placeholder kimi mövcuddur (real content yox).
            // Tam reload ilə server-side real content çəkək.
            window.location.reload();
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && createExamModal && createExamModal.classList.contains("active")) {
            closeCreateExamModal(true);
            return;
        }

        if (event.key === "Escape" && assignedExamInfoBackdrop && assignedExamInfoBackdrop.classList.contains("is-open")) {
            closeAssignedExamInfoModal();
            return;
        }

        if (event.key === "Escape" && isMobileViewport() && sidebar && !sidebar.classList.contains("collapsed")) {
            setSidebarCollapsed(true);
        }
    });

    var backdrop = document.getElementById("exam-code-backdrop");
    var titleEl = document.getElementById("exam-code-title");
    var textEl = document.getElementById("exam-code-text");
    var slugInput = document.getElementById("exam-code-exam-slug");
    var codeInput = document.getElementById("exam-code-input");

    function openExamCodeModal(button) {
        if (!backdrop || !button || !slugInput || !codeInput) {
            return;
        }

        var slug = button.getAttribute("data-exam-slug");
        var examTitle = button.getAttribute("data-exam-title");

        slugInput.value = slug || "";
        if (titleEl) {
            titleEl.textContent = "Giriş Kodu";
        }
        if (textEl) {
            textEl.innerHTML = '<strong>"' + (examTitle || "") + '"</strong> imtahanına keçid üçün kodu yazın.';
        }
        codeInput.value = "";

        backdrop.style.display = "flex";
        window.setTimeout(function () {
            backdrop.classList.add("show");
            codeInput.focus();
        }, 10);
    }

    function closeExamCodeModal() {
        if (!backdrop) {
            return;
        }

        backdrop.classList.remove("show");
        window.setTimeout(function () {
            backdrop.style.display = "none";
        }, 300);
    }

    if (backdrop) {
        backdrop.addEventListener("click", function (event) {
            if (event.target === backdrop) {
                closeExamCodeModal();
            }
        });
    }

    if (codeInput) {
        codeInput.addEventListener("input", function () {
            this.value = this.value.replace(/[^0-9]/g, "");
        });
    }

    window.openExamCodeModal = openExamCodeModal;
    window.closeExamCodeModal = closeExamCodeModal;
});
