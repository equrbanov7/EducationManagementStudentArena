/* Profile page namespace and bootstrapping helpers. */
(function () {
    "use strict";

    var ns = window.EMSProfile = window.EMSProfile || {};
    ns._installers = ns._installers || [];

    ns.register = function register(installer) {
        if (typeof installer === "function") {
            ns._installers.push(installer);
        }
    };

    ns.createContext = function createContext() {
        var toggleBtn = document.getElementById("sidebarToggle");
        var profilePage = document.querySelector(".profile-page");
        var ajaxSectionsRaw = profilePage ? profilePage.getAttribute("data-ajax-sections") || "" : "";

        return {
            toggleBtn: toggleBtn,
            sidebar: document.getElementById("profileSidebar"),
            mobileSidebarTrigger: document.getElementById("profileMobileSidebarTrigger"),
            sidebarBackdrop: document.getElementById("profileSidebarBackdrop"),
            mobileMediaQuery: window.matchMedia("(max-width: 768px)"),
            sidebarExpandTitle: toggleBtn ? toggleBtn.getAttribute("data-title-expand") || "Open sidebar" : "Open sidebar",
            sidebarCollapseTitle: toggleBtn
                ? toggleBtn.getAttribute("data-title-collapse") || "Close sidebar"
                : "Close sidebar",

            profilePage: profilePage,
            profileBaseUrl: profilePage ? profilePage.getAttribute("data-profile-base-url") || window.location.pathname : window.location.pathname,
            defaultSection: profilePage ? profilePage.getAttribute("data-default-section") || "profile-info" : "profile-info",
            defaultSectionTitle: profilePage ? profilePage.getAttribute("data-default-section-title") || "Profile" : "Profile",
            sectionLinks: document.querySelectorAll(".js-profile-section-link[data-section]"),
            sidebarSectionLinks: document.querySelectorAll(".profile-sidebar .js-profile-section-link[data-section]"),
            sectionPanels: document.querySelectorAll("[data-profile-section-panel]"),
            ajaxSafeSections: ajaxSectionsRaw
                .split(",")
                .map(function (s) { return s.trim(); })
                .filter(function (s) { return !!s; }),
            sectionFragmentUrlTemplate: profilePage ? profilePage.getAttribute("data-section-fragment-url") || "" : "",
            badgesUrl: profilePage ? profilePage.getAttribute("data-badges-url") || "" : "",
            sectionsHost: document.getElementById("profileSectionsContainer"),
            ajaxLoadInFlight: null,
            badgesRefreshInFlight: null,

            sectionTitle: document.getElementById("profileSectionTitle"),
            createExamModal: document.getElementById("createExamModal"),
            createExamModalBody: document.getElementById("createExamModalBody"),
            closeCreateExamModalBtn: document.getElementById("closeCreateExamModal"),
            createExamSubmitInFlight: false,
            sidebarMenuGroups: []
        };
    };

    ns.start = function start() {
        if (ns._started) {
            return;
        }
        ns._started = true;

        var ctx = ns.createContext();
        ns.ctx = ctx;
        ns._installers.forEach(function (installer) {
            installer(ctx);
        });
    };
})();
