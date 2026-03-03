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
    var sectionTitle = document.getElementById("profileSectionTitle");
    var createExamModal = document.getElementById("createExamModal");
    var createExamModalBody = document.getElementById("createExamModalBody");
    var closeCreateExamModalBtn = document.getElementById("closeCreateExamModal");
    var createExamSubmitInFlight = false;
    var sidebarMenuGroups = [];

    function setSidebarMenuGroupState(group, isOpen) {
        if (!group) {
            return;
        }
        group.classList.toggle("is-open", isOpen);
        var toggle = group.querySelector(".sidebar-menu-group-toggle");
        if (toggle) {
            toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
        }
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

        sidebar.setAttribute("data-accordion-ready", "1");
    }

    function resolveSectionFromUrl() {
        try {
            var params = new URLSearchParams(window.location.search);
            return params.get("section") || defaultSection;
        } catch (error) {
            return defaultSection;
        }
    }

    function setActiveSection(section, updateUrl) {
        var hasTargetPanel = false;

        sectionPanels.forEach(function (panel) {
            var isMatch = panel.getAttribute("data-profile-section-panel") === section;
            panel.classList.toggle("is-active", isMatch);
            if (isMatch) {
                hasTargetPanel = true;
            }
        });

        if (!hasTargetPanel) {
            return false;
        }

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
            return;
        }

        var hiddenSelect = form.querySelector('select[name="' + config.selectName + '"]');
        var listContainer = form.querySelector(config.listSelector);
        var searchInput = form.querySelector(config.searchSelector);
        var counter = form.querySelector(config.counterSelector);

        if (!hiddenSelect || !listContainer) {
            return;
        }

        function updateCounter() {
            if (counter) {
                counter.textContent = String(hiddenSelect.selectedOptions.length);
            }
        }

        function renderList() {
            var options = Array.from(hiddenSelect.options || []);
            listContainer.innerHTML = "";

            if (!options.length) {
                listContainer.innerHTML = '<div class="create-exam-list-empty">Məlumat tapılmadı.</div>';
                updateCounter();
                return;
            }

            options.forEach(function (option) {
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
                    checkbox.addEventListener("change", function () {
                        option.selected = checkbox.checked;
                        updateCounter();
                    });
                }

                row.addEventListener("click", function (event) {
                    if (!checkbox) {
                        return;
                    }
                    if (event.target === checkbox || event.target === label) {
                        return;
                    }
                    checkbox.checked = !checkbox.checked;
                    option.selected = checkbox.checked;
                    updateCounter();
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

        initCreateExamAccessToggle(form);
        initCreateExamSearchableSelect(form, {
            selectName: "allowed_groups",
            listSelector: "#createExamGroupsList",
            searchSelector: "#createExamGroupsSearch",
            counterSelector: "#createExamGroupsCount"
        });
        initCreateExamSearchableSelect(form, {
            selectName: "allowed_users",
            listSelector: "#createExamUsersList",
            searchSelector: "#createExamUsersSearch",
            counterSelector: "#createExamUsersCount"
        });

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

        ensureModalRoot(createExamModal);
        createExamModal.classList.add("active");
        document.body.style.overflow = "hidden";
        createExamModalBody.innerHTML = createExamModalLoadingMarkup();

        var modalUrl = buildCreateExamModalUrl(createExamUrl);
        createExamModal.dataset.createExamUrl = modalUrl;

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
            createExamModalBody.innerHTML = html;
            bindCreateExamModalForm();
        } catch (error) {
            createExamModalBody.innerHTML = '<div class="create-exam-modal-error">Form yüklənmədi. Yenidən cəhd edin.</div>';
        }
    }

    function closeCreateExamModal(resetContent) {
        if (!createExamModal) {
            return;
        }
        createExamModal.classList.remove("active");
        document.body.style.overflow = "";
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

            if (setActiveSection(section, true)) {
                event.preventDefault();
                if (isMobileViewport()) {
                    setSidebarCollapsed(true);
                }
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

    var resolvedSection = resolveSectionFromUrl();
    if (!setActiveSection(resolvedSection, false)) {
        setActiveSection(defaultSection, false);
    }

    window.addEventListener("popstate", function () {
        var section = resolveSectionFromUrl();
        if (!setActiveSection(section, false)) {
            setActiveSection(defaultSection, false);
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && createExamModal && createExamModal.classList.contains("active")) {
            closeCreateExamModal(true);
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
