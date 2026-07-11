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
            syncSidebarToggleState();
        }

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
            ctx.sidebarMenuGroups.forEach(syncSidebarMenuGroupLayout);
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
            if (!section || !ctx.sidebarMenuGroups.length) {
                return;
            }
            var sectionLink = ctx.sidebar
                ? ctx.sidebar.querySelector('.js-profile-section-link[data-section="' + section + '"]')
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
            if (!ctx.sidebar || ctx.sidebar.getAttribute("data-accordion-ready") === "1") {
                return;
            }
            var menu = ctx.sidebar.querySelector(".sidebar-menu");
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

            ctx.sidebarMenuGroups = Array.from(menu.querySelectorAll(".sidebar-menu-group"));
            if (!ctx.sidebarMenuGroups.length) {
                ctx.sidebar.setAttribute("data-accordion-ready", "1");
                return;
            }

            var hasOpenGroup = false;
            ctx.sidebarMenuGroups.forEach(function (group) {
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
                setSidebarMenuGroupState(ctx.sidebarMenuGroups[0], true);
            }

            syncAllSidebarMenuGroupLayouts();
            ctx.sidebar.setAttribute("data-accordion-ready", "1");
        }

        function updateSidebarActiveState(section) {
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

        window.addEventListener("resize", syncAllSidebarMenuGroupLayouts);

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
