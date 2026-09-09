/* Sidebar, generic profile UI helpers, and legacy exam-code modal. */
(function (ns) {
    "use strict";

    ns.register(function installProfileUi(ctx) {
        function isMobileViewport() {
            return ctx.mobileMediaQuery.matches;
        }

        function syncSidebarToggleState() {
            if (!ctx.sidebar) {
                return;
            }

            var icon = ctx.toggleBtn ? ctx.toggleBtn.querySelector("i") : null;
            var isCollapsed = ctx.sidebar.classList.contains("collapsed");

            if (icon && ctx.toggleBtn) {
                if (isCollapsed) {
                    icon.classList.remove("fa-chevron-left");
                    icon.classList.add("fa-chevron-right");
                    ctx.toggleBtn.title = ctx.sidebarExpandTitle;
                } else {
                    icon.classList.remove("fa-chevron-right");
                    icon.classList.add("fa-chevron-left");
                    ctx.toggleBtn.title = ctx.sidebarCollapseTitle;
                }
            }

            if (ctx.mobileSidebarTrigger) {
                var showMobileTrigger = isCollapsed && isMobileViewport();
                ctx.mobileSidebarTrigger.classList.toggle("is-hidden", !showMobileTrigger);
                ctx.mobileSidebarTrigger.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
                ctx.mobileSidebarTrigger.setAttribute("aria-hidden", showMobileTrigger ? "false" : "true");
            }

            if (ctx.sidebarBackdrop) {
                ctx.sidebarBackdrop.classList.toggle("is-visible", isMobileViewport() && !isCollapsed);
            }

            document.body.classList.toggle("profile-sidebar-open-mobile", isMobileViewport() && !isCollapsed);
        }

        function setSidebarCollapsed(isCollapsed) {
            if (!ctx.sidebar) {
                return;
            }
            ctx.sidebar.classList.toggle("collapsed", isCollapsed);
            localStorage.setItem("profileSidebarCollapsed", isCollapsed ? "true" : "false");
            applySidebarCollapsedGroups(isCollapsed);
            syncSidebarToggleState();
        }

        /* ── Sidebar qrupları (nativ <details>) ──────────────────────────────
           2026-09-10: qruplar artıq SERVER tərəfdə render olunur. Əvvəllər bu
           funksiyalar düz siyahını yükləndikdən sonra akkordeona çevirirdi —
           yüklənmə sıçrayışı, JS-siz düz siyahı və qrupa aid olmayan bəndlərin
           yanlış qrupa düşməsi problemləri yaranırdı. İndi JS yalnız:
             • qrup başlığındakı sayğac/xəbərdarlıq nöqtəsini doldurur,
             • istifadəçinin açıb-bağladığını yadda saxlayır,
             • SPA keçidində aktiv bölmənin qrupunu açır,
             • yığcam rejimə keçəndə hamısını açır (bağlı `<details>`-in
               məzmununu CSS ilə göstərmək mümkün deyil), qayıdanda bərpa edir.
        */

        var SIDEBAR_GROUP_STATE_KEY = "profileSidebarGroups";

        function readSidebarGroupState() {
            try {
                var raw = localStorage.getItem(SIDEBAR_GROUP_STATE_KEY);
                var parsed = raw ? JSON.parse(raw) : null;
                return parsed && typeof parsed === "object" ? parsed : {};
            } catch (e) {
                return {};
            }
        }

        function writeSidebarGroupState(key, isOpen) {
            if (!key) {
                return;
            }
            try {
                var state = readSidebarGroupState();
                state[key] = isOpen;
                localStorage.setItem(SIDEBAR_GROUP_STATE_KEY, JSON.stringify(state));
            } catch (e) {
                /* fail-soft: private mode / dolu kvota */
            }
        }

        function sidebarGroupDetails(group) {
            return group ? group.querySelector("details.sidebar-group") : null;
        }

        /* Başlıqdakı meta: bənd sayı + (bağlı ikən) gözləyən nişan nöqtəsi. */
        function syncSidebarMenuGroupLayout(group) {
            if (!group) {
                return;
            }

            var meta = group.querySelector(".sidebar-menu-group-meta");
            if (!meta) {
                return;
            }

            var links = group.querySelectorAll(".sidebar-menu-group-items .sidebar-menu-link");
            var details = sidebarGroupDetails(group);
            var isOpen = Boolean(details && details.open);
            var hasAlert = false;

            group.querySelectorAll(".sidebar-menu-badge").forEach(function (badge) {
                if ((badge.textContent || "").trim() !== "") {
                    hasAlert = true;
                }
            });

            meta.textContent = isOpen ? "" : String(links.length);
            meta.classList.toggle("sidebar-menu-group-meta--alert", !isOpen && hasAlert);
        }

        function syncAllSidebarMenuGroupLayouts() {
            ctx.sidebarMenuGroups.forEach(syncSidebarMenuGroupLayout);
        }

        function setSidebarMenuGroupState(group, isOpen) {
            var details = sidebarGroupDetails(group);
            if (!details) {
                return;
            }
            details.open = Boolean(isOpen);
            syncSidebarMenuGroupLayout(group);
        }

        function openSidebarMenuGroupForSection(section) {
            if (!ctx.sidebarMenuGroups.length) {
                return;
            }

            var sectionLink = section && ctx.sidebar
                ? ctx.sidebar.querySelector('.sidebar-menu-link[data-section="' + section + '"]')
                : null;
            var targetGroup = sectionLink ? sectionLink.closest(".sidebar-menu-group") : null;

            ctx.sidebarMenuGroups.forEach(function (group) {
                group.classList.toggle("has-active", group === targetGroup);
            });

            if (targetGroup) {
                setSidebarMenuGroupState(targetGroup, true);
            }
        }

        /* Uzun menyuda (RİM/rektor: 59 bənd, yığcam rejimdə 59 nişan) aktiv bənd
           görünən sahədən kənarda qala bilir. Sidebar öz sürüşmə sahəsi olduğuna
           görə YALNIZ onu sürüşdürürük — səhifə yerində qalır. */
        function scrollActiveSidebarLinkIntoView() {
            if (!ctx.sidebar) {
                return;
            }
            var activeLink = ctx.sidebar.querySelector(".sidebar-menu-link.active");
            if (!activeLink) {
                return;
            }
            window.requestAnimationFrame(function () {
                var box = activeLink.getBoundingClientRect();
                var frame = ctx.sidebar.getBoundingClientRect();
                if (box.top >= frame.top && box.bottom <= frame.bottom) {
                    return;
                }
                ctx.sidebar.scrollTop += box.top - frame.top - frame.height / 3;
            });
        }

        /* Yığcam rejim: bağlı `<details>` nişanlarını da gizlədir, ona görə
           keçiddə hamısı açılır və geri qayıdanda əvvəlki vəziyyət bərpa olunur. */
        function applySidebarCollapsedGroups(isCollapsed) {
            if (!ctx.sidebarMenuGroups.length) {
                return;
            }

            ctx.sidebarMenuGroups.forEach(function (group) {
                var details = sidebarGroupDetails(group);
                if (!details) {
                    return;
                }
                if (isCollapsed) {
                    if (details.getAttribute("data-open-before-collapse") === null) {
                        details.setAttribute("data-open-before-collapse", details.open ? "1" : "0");
                    }
                    details.open = true;
                    return;
                }
                var previous = details.getAttribute("data-open-before-collapse");
                if (previous !== null) {
                    details.open = previous === "1";
                    details.removeAttribute("data-open-before-collapse");
                }
            });
            syncAllSidebarMenuGroupLayouts();
            scrollActiveSidebarLinkIntoView();
        }

        function initSidebarAccordionMenu() {
            if (!ctx.sidebar || ctx.sidebar.getAttribute("data-accordion-ready") === "1") {
                return;
            }

            ctx.sidebarMenuGroups = Array.from(ctx.sidebar.querySelectorAll(".sidebar-menu-group"));
            if (!ctx.sidebarMenuGroups.length) {
                ctx.sidebar.setAttribute("data-accordion-ready", "1");
                return;
            }

            var storedState = readSidebarGroupState();

            ctx.sidebarMenuGroups.forEach(function (group) {
                var details = sidebarGroupDetails(group);
                if (!details) {
                    return;
                }

                // Server DEFAULT-u yalnız istifadəçi həmin qrupu ƏVVƏLLƏR özü
                // açıb-bağlayıbsa əzilir (`storedState`-də açar var).
                var key = group.getAttribute("data-sidebar-group");
                if (key && Object.prototype.hasOwnProperty.call(storedState, key)) {
                    details.open = storedState[key] === true;
                }

                // Yaddaşa YALNIZ istifadəçinin öz kliki yazılır. `toggle` hadisəsi
                // proqram dəyişikliyində də atəşlənir (yığcam rejim bütün qrupları
                // məcburi açır) — ona qulaq assaq, istifadəçinin seçimi silinərdi.
                // `click` anında `details.open` HƏLƏ köhnə dəyərdir → tərsini yazırıq.
                var summary = details.querySelector(".sidebar-menu-group-toggle");
                if (summary) {
                    summary.addEventListener("click", function () {
                        writeSidebarGroupState(key, !details.open);
                    });
                }
                details.addEventListener("toggle", function () {
                    syncSidebarMenuGroupLayout(group);
                });
            });

            // «Harada olduğun» yaddaşdan asılı olmamalıdır: aktiv bölmənin
            // qrupu ilk yükləmədə də açılır (server `active` sinfini verir).
            var activeLink = ctx.sidebar.querySelector(".sidebar-menu-link.active[data-section]");
            openSidebarMenuGroupForSection(activeLink ? activeLink.getAttribute("data-section") : null);
            syncAllSidebarMenuGroupLayouts();

            if (ctx.sidebar.classList.contains("collapsed")) {
                applySidebarCollapsedGroups(true);
            }

            scrollActiveSidebarLinkIntoView();

            ctx.sidebar.setAttribute("data-accordion-ready", "1");
        }

        function updateSidebarActiveState(section) {
            /* ⚠️ 2026-09-09 (sahib: «2 hissə eyni anda aktiv göstərir»).
               `ctx.sidebarSectionLinks` YALNIZ `.js-profile-section-link`-ləri
               toplayır. Sidebar-da SPA olmayan bölmə linkləri də var (məs.
               «Jurnal bağlama») — onların `active` sinfini server render edir və
               SPA keçidi onu SİLƏ BİLMİRDİ, nəticədə iki bölmə eyni anda mavi
               qalırdı. Ona görə əvvəlcə sidebar-dakı BÜTÜN bölmə linklərindən
               `active` götürülür, sonra uyğun olan yenidən qoyulur. */
            if (ctx.sidebar) {
                ctx.sidebar.querySelectorAll(".sidebar-menu-link[data-section]").forEach(function (link) {
                    if (link.getAttribute("data-section") !== section) {
                        link.classList.remove("active");
                        link.removeAttribute("aria-current");
                    }
                });
            }
            ctx.sidebarSectionLinks.forEach(function (link) {
                var isMatch = link.getAttribute("data-section") === section;
                link.classList.toggle("active", isMatch);
                // A11y (U18): aktiv bölmə screen-reader-ə "cari səhifə" kimi bildirilir.
                if (isMatch) {
                    link.setAttribute("aria-current", "page");
                } else {
                    link.removeAttribute("aria-current");
                }
                if (isMatch && ctx.sectionTitle) {
                    ctx.sectionTitle.textContent = link.getAttribute("data-title") || ctx.defaultSectionTitle;
                    // Brauzer tab-ı / tarixçə / ekran oxuyucu üçün sənəd başlığı da
                    // bölmə ilə dəyişir (QA 2026-09-05 P3-4).
                    var titleSuffix = ctx.profilePage ? ctx.profilePage.getAttribute("data-title-suffix") : "";
                    if (titleSuffix) {
                        document.title = ctx.sectionTitle.textContent + " - " + titleSuffix;
                    }
                }
            });
            openSidebarMenuGroupForSection(section);
        }

        function ensureModalRoot(modal) {
            if (!modal || !modal.parentElement || modal.parentElement === document.body) {
                return;
            }
            document.body.appendChild(modal);
        }

        function openCreatePostModal() {
            if (typeof window.openCreatePostModal === "function") {
                window.openCreatePostModal();
                return;
            }

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
                titleEl.textContent = gettext("Giriş Kodu");
            }
            if (textEl) {
                var titleStrong = document.createElement("strong");
                titleStrong.textContent = '"' + (examTitle || "");
                var instruction = gettext('"</strong> imtahanına keçid üçün kodu yazın.').replace("</strong>", "");
                textEl.replaceChildren(titleStrong, document.createTextNode(instruction));
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

        ctx.isMobileViewport = isMobileViewport;
        ctx.setSidebarCollapsed = setSidebarCollapsed;
        ctx.syncAllSidebarMenuGroupLayouts = syncAllSidebarMenuGroupLayouts;
        ctx.initSidebarAccordionMenu = initSidebarAccordionMenu;
        ctx.updateSidebarActiveState = updateSidebarActiveState;

        // A11y (U18): server-render olunan ilkin aktiv linkə aria-current ver.
        if (ctx.sidebar) {
            ctx.sidebar.querySelectorAll(".js-profile-section-link.active").forEach(function (link) {
                link.setAttribute("aria-current", "page");
            });
        }
        ctx.ensureModalRoot = ensureModalRoot;
        ctx.openCreatePostModal = openCreatePostModal;
        ctx.initDebouncedSearchForms = initDebouncedSearchForms;

        if (ctx.sidebar) {
            if (ctx.toggleBtn) {
                ctx.toggleBtn.addEventListener("click", function () {
                    setSidebarCollapsed(!ctx.sidebar.classList.contains("collapsed"));
                });
            }

            if (localStorage.getItem("profileSidebarCollapsed") === "true") {
                ctx.sidebar.classList.add("collapsed");
            }
            // Mobil görünüşdə ilk yükləmə: sidebar overlay kimi məzmunu örtməsin —
            // AJAX swap-dan sonrakı davranışla (section_loader → setSidebarCollapsed)
            // eyni. localStorage-a yazılmır ki, desktop seçimi pozulmasın (QA P2-1).
            if (isMobileViewport()) {
                ctx.sidebar.classList.add("collapsed");
            }
            syncSidebarToggleState();
        }

        if (ctx.mobileSidebarTrigger && ctx.sidebar) {
            ctx.mobileSidebarTrigger.addEventListener("click", function () {
                setSidebarCollapsed(false);
            });
        }

        if (ctx.sidebarBackdrop && ctx.sidebar) {
            ctx.sidebarBackdrop.addEventListener("click", function () {
                if (isMobileViewport()) {
                    setSidebarCollapsed(true);
                }
            });
        }

        if (typeof ctx.mobileMediaQuery.addEventListener === "function") {
            ctx.mobileMediaQuery.addEventListener("change", syncSidebarToggleState);
        } else if (typeof ctx.mobileMediaQuery.addListener === "function") {
            ctx.mobileMediaQuery.addListener(syncSidebarToggleState);
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
})(window.EMSProfile = window.EMSProfile || {});
