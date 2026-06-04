/* ===========================================================================
   home_loading.js — light-weight page-transition + skeleton handling.
   ---------------------------------------------------------------------------
   Goals:
   1. Show a top progress bar while the user navigates between pages so the
      site feels responsive even before the new HTML arrives.
   2. Hide skeleton placeholders once the real content is in the DOM.
   3. Fade the listing in gently — no jank, no layout shift, respects
      `prefers-reduced-motion`.

   Pure vanilla JS, no dependencies. Safe to load on every blog page.
   ===========================================================================*/

(function () {
    "use strict";

    const reducedMotion = window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // ---- 1. Top progress bar -------------------------------------------------
    function ensureProgressBar() {
        let bar = document.querySelector(".route-progress");
        if (!bar) {
            bar = document.createElement("div");
            bar.className = "route-progress";
            bar.setAttribute("role", "presentation");
            document.body.appendChild(bar);
        }
        return bar;
    }

    function startProgress() {
        ensureProgressBar();
        document.body.classList.add("is-route-loading");
        document.body.classList.remove("is-route-loaded");
    }

    function finishProgress() {
        document.body.classList.remove("is-route-loading");
        document.body.classList.add("is-route-loaded");
        setTimeout(() => document.body.classList.remove("is-route-loaded"), 600);
    }

    // Intercept same-origin internal navigations only — external links, mailto,
    // tel, anchors, downloads and target=_blank are left untouched.
    function isInternalNavigation(anchor) {
        if (!anchor || !anchor.href) return false;
        if (anchor.target && anchor.target !== "_self") return false;
        if (anchor.hasAttribute("download")) return false;
        if (anchor.matches(
            ".js-open-create-exam, .js-open-create-course, .js-open-create-post, " +
            ".js-open-exam-form-modal, .js-open-question-form-modal, " +
            ".js-open-delete-confirm-modal, .js-open-assigned-exam-modal, [data-open-exam-start-modal], " +
            "[data-no-route-loading]"
        )) {
            return false;
        }

        const url = new URL(anchor.href, window.location.href);
        if (url.origin !== window.location.origin) return false;

        const protocol = url.protocol;
        if (protocol !== "http:" && protocol !== "https:") return false;

        // Skip anchor-only links (just a hash on the current page)
        if (
            url.pathname === window.location.pathname &&
            url.search === window.location.search &&
            url.hash
        ) {
            return false;
        }
        return true;
    }

    document.addEventListener("click", function (event) {
        if (event.defaultPrevented) return;
        if (event.button !== 0) return;
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

        const anchor = event.target.closest && event.target.closest("a");
        if (!isInternalNavigation(anchor)) return;

        startProgress();
    });

    // Some navigations (form submits, history pop) finish without our click
    // handler firing — clean up either way once the page becomes visible again.
    window.addEventListener("pageshow", finishProgress);
    window.addEventListener("DOMContentLoaded", finishProgress);

    // ---- 2. Skeleton hide + fade-in ----------------------------------------
    function hydrateListing() {
        document.body.classList.add("is-page-loaded");

        if (reducedMotion) return;

        // Fade-in for major content surfaces — kept minimal so it doesn't
        // interfere with native scroll-restoration on back/forward.
        const fadeTargets = document.querySelectorAll(
            ".home-top-posts-grid, #blogContainer, .home-content-layout"
        );
        fadeTargets.forEach(function (el) {
            el.classList.add("page-fade-in");
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", hydrateListing);
    } else {
        hydrateListing();
    }

    // Mark the listing shell as loaded — used by other code that wants to know
    // when initial content is ready (e.g. infinite-scroll add-ons later).
    document.addEventListener("DOMContentLoaded", function () {
        const shell = document.getElementById("homeListingShell");
        if (shell) shell.dataset.pageLoaded = "true";
    });
})();
