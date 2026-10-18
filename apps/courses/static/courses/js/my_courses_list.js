/*
 * courses/js/my_courses_list.js — «Kurslarım» görünüş açarı: kartlar / siyahı (2026-10-18).
 *
 * Seçim yalnız brauzerin rahatlığıdır (localStorage, xəta olsa sükutla keçir) — server
 * vəziyyəti deyil. AJAX-safe: klik `EMSDelegate` ilə bir dəfə, bərpa `EMSReady` ilə hər
 * bölmə swap-ından sonra (idempotent, null-safe).
 */
(function () {
    "use strict";

    var KEY = "ems.myCourses.view";

    function stored() {
        try {
            return window.localStorage.getItem(KEY) === "list" ? "list" : "grid";
        } catch (err) {
            return "grid";
        }
    }

    function remember(view) {
        try {
            window.localStorage.setItem(KEY, view);
        } catch (err) {
            /* gizli pəncərə / bloklanmış yaddaş — seçim yalnız bu səhifədə qalır */
        }
    }

    function apply(view) {
        var panel = document.querySelector('[data-profile-section-panel="my-courses"]');
        if (!panel) {
            return;
        }
        var grid = panel.querySelector("[data-mcl-grid]");
        if (grid) {
            grid.classList.toggle("mcl-grid--list", view === "list");
        }
        panel.querySelectorAll("[data-mcl-view]").forEach(function (btn) {
            btn.setAttribute("aria-pressed", btn.getAttribute("data-mcl-view") === view ? "true" : "false");
        });
    }

    if (!window.__emsMyCoursesView && window.EMSDelegate) {
        window.__emsMyCoursesView = true;
        window.EMSDelegate.on("click", "[data-mcl-view]", function (event, btn) {
            var view = btn.getAttribute("data-mcl-view") === "list" ? "list" : "grid";
            remember(view);
            apply(view);
        });
    }

    if (window.EMSReady) {
        window.EMSReady(function () {
            apply(stored());
        });
    }
})();
