/* "Ümumi tədris məlumatı" (overall-academic) cabinet section — client-side
 * search + filters over the server-rendered per-subject rows. No fetch: the
 * data ships pre-rendered (same contract as my-transcript); this file only
 * toggles visibility. Follows the same init/reinit pattern used across the
 * profile SPA (see permission_editor.entry.js / monitoring/system_monitoring.js):
 * bind once per fresh DOM node, re-bind on every AJAX section swap via the
 * "profile:section:loaded" event (the old node is removed by section_loader.js
 * on every swap, so there is no double-binding risk).
 */
(function (ns, document, window) {
    "use strict";

    function debounce(fn, wait) {
        var timer = null;
        return function () {
            var args = arguments;
            if (timer) {
                window.clearTimeout(timer);
            }
            timer = window.setTimeout(function () {
                fn.apply(null, args);
            }, wait);
        };
    }

    function initRoot(root) {
        if (!root || root.dataset.oaInit === "1") {
            return;
        }
        root.dataset.oaInit = "1";

        var searchInput = root.querySelector("[data-oa-search-input]");
        var yearSelect = root.querySelector("[data-oa-year-filter]");
        var seasonSelect = root.querySelector("[data-oa-season-filter]");
        var letterSelect = root.querySelector("[data-oa-letter-filter]");
        var failedCheckbox = root.querySelector('[data-oa-filter="failed"]');
        var qbCheckbox = root.querySelector('[data-oa-filter="qb"]');
        var exam25Checkbox = root.querySelector('[data-oa-filter="exam25"]');
        var resetButton = root.querySelector("[data-oa-reset]");
        var countEl = root.querySelector("[data-oa-count]");
        var emptyEl = root.querySelector("[data-oa-empty]");
        var semesterGroups = root.querySelectorAll("[data-oa-semester]");

        if (!semesterGroups.length) {
            // No record yet (empty state) — nothing to filter.
            return;
        }

        function applyFilters() {
            var query = (searchInput && searchInput.value || "").trim().toLowerCase();
            var year = yearSelect ? yearSelect.value : "";
            var season = seasonSelect ? seasonSelect.value : "";
            var letter = letterSelect ? letterSelect.value : "";
            var onlyFailed = Boolean(failedCheckbox && failedCheckbox.checked);
            var onlyQb = Boolean(qbCheckbox && qbCheckbox.checked);
            var onlyExam25 = Boolean(exam25Checkbox && exam25Checkbox.checked);
            var visibleTotal = 0;

            semesterGroups.forEach(function (group) {
                var groupYear = group.getAttribute("data-oa-year") || "";
                var groupSeason = group.getAttribute("data-oa-season") || "";
                var groupMatchesTerm = (!year || year === groupYear) && (!season || season === groupSeason);
                var groupVisibleCount = 0;

                group.querySelectorAll("[data-oa-row]").forEach(function (row) {
                    var matches = groupMatchesTerm;

                    if (matches && query) {
                        var haystack = row.getAttribute("data-oa-search") || "";
                        matches = haystack.indexOf(query) !== -1;
                    }
                    if (matches && letter) {
                        matches = (row.getAttribute("data-oa-letter") || "") === letter;
                    }
                    if (matches && onlyFailed) {
                        matches = row.getAttribute("data-oa-failed") === "1";
                    }
                    if (matches && onlyQb) {
                        // Q/B-DAN kəsilən = davamiyyət 25% həddi → imtahana buraxılmayıb.
                        matches = row.getAttribute("data-oa-fail-reason") === "qb";
                    }
                    if (matches && onlyExam25) {
                        // 25% = imtahana girib, kəsilib (təkrar imtahan hüququ).
                        matches = row.getAttribute("data-oa-fail-reason") === "exam25";
                    }

                    row.classList.toggle("is-hidden", !matches);
                    if (matches) {
                        groupVisibleCount += 1;
                    }
                });

                group.classList.toggle("is-hidden", groupVisibleCount === 0);
                visibleTotal += groupVisibleCount;
            });

            if (countEl) {
                var suffix = countEl.getAttribute("data-oa-count-suffix") || "";
                countEl.textContent = String(visibleTotal) + (suffix ? " " + suffix : "");
            }
            if (emptyEl) {
                emptyEl.hidden = visibleTotal !== 0;
            }
        }

        var debouncedApply = debounce(applyFilters, 200);

        if (searchInput) {
            searchInput.addEventListener("input", debouncedApply);
        }
        [yearSelect, seasonSelect, letterSelect].forEach(function (select) {
            if (select) {
                select.addEventListener("change", applyFilters);
            }
        });
        [failedCheckbox, qbCheckbox, exam25Checkbox].forEach(function (checkbox) {
            if (checkbox) {
                checkbox.addEventListener("change", applyFilters);
            }
        });
        if (resetButton) {
            resetButton.addEventListener("click", function () {
                if (searchInput) {
                    searchInput.value = "";
                }
                [yearSelect, seasonSelect, letterSelect].forEach(function (select) {
                    if (!select) {
                        return;
                    }
                    select.value = "";
                    if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.sync === "function") {
                        window.EMSBootstrapSelect.sync(select);
                    }
                });
                [failedCheckbox, qbCheckbox, exam25Checkbox].forEach(function (checkbox) {
                    if (checkbox) {
                        checkbox.checked = false;
                    }
                });
                applyFilters();
            });
        }

        applyFilters();
    }

    function initAll(scope) {
        var container = scope || document;
        var roots = container.querySelectorAll ? container.querySelectorAll("[data-oa-root]") : [];
        if ((!roots || !roots.length) && container.matches && container.matches("[data-oa-root]")) {
            roots = [container];
        }
        Array.prototype.forEach.call(roots || [], initRoot);
    }

    ns.init = initRoot;
    ns.initAll = initAll;

    if (window.EMSProfileReinitHooks && typeof window.EMSProfileReinitHooks === "object") {
        window.EMSProfileReinitHooks.overallAcademic = function (panel) {
            initAll(panel || document);
        };
    }

    document.addEventListener("profile:section:loaded", function (event) {
        initAll(event.detail && event.detail.panel ? event.detail.panel : document);
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            initAll(document);
        });
    } else {
        initAll(document);
    }
})(window.EMSOverallAcademic = window.EMSOverallAcademic || {}, document, window);
