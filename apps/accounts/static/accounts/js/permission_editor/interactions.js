/* Permission editor accordion and search interactions. */
(function (ns, window) {
    "use strict";

    function bindModuleAccordionAnimation(modules) {
        if (!modules.length) {
            return;
        }

        var prefersReducedMotion = typeof window.matchMedia === "function"
            && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        if (prefersReducedMotion) {
            return;
        }

        modules.forEach(function (module) {
            var summary = module.querySelector(".permission-module-summary");
            var body = module.querySelector(".permission-module-body");
            if (!summary || !body || typeof module.animate !== "function") {
                return;
            }

            var currentAnimation = null;
            var isClosing = false;
            var isExpanding = false;

            function clearAnimationState() {
                module.style.height = "";
                module.style.overflow = "";
                currentAnimation = null;
                isClosing = false;
                isExpanding = false;
            }

            function onAnimationFinish(shouldOpen) {
                module.open = shouldOpen;
                clearAnimationState();
            }

            function onAnimationCancel() {
                clearAnimationState();
            }

            function collapse() {
                isClosing = true;
                var startHeight = module.offsetHeight + "px";
                var endHeight = summary.offsetHeight + "px";

                if (currentAnimation) {
                    currentAnimation.cancel();
                }

                module.style.overflow = "hidden";
                currentAnimation = module.animate(
                    { height: [startHeight, endHeight] },
                    { duration: 240, easing: "cubic-bezier(0.4, 0, 0.2, 1)" }
                );
                currentAnimation.onfinish = function () {
                    onAnimationFinish(false);
                };
                currentAnimation.oncancel = onAnimationCancel;
            }

            function expand() {
                isExpanding = true;
                var startHeight = module.offsetHeight + "px";
                var endHeight = summary.offsetHeight + body.offsetHeight + "px";

                if (currentAnimation) {
                    currentAnimation.cancel();
                }

                module.style.overflow = "hidden";
                currentAnimation = module.animate(
                    { height: [startHeight, endHeight] },
                    { duration: 240, easing: "cubic-bezier(0.4, 0, 0.2, 1)" }
                );
                currentAnimation.onfinish = function () {
                    onAnimationFinish(true);
                };
                currentAnimation.oncancel = onAnimationCancel;
            }

            function openModule() {
                module.style.height = module.offsetHeight + "px";
                module.open = true;
                window.requestAnimationFrame(expand);
            }

            summary.addEventListener("click", function (event) {
                event.preventDefault();
                if (isClosing || !module.open) {
                    openModule();
                } else if (isExpanding || module.open) {
                    collapse();
                }
            });
        });
    }

    function bindSearch(root, searchInput, searchSubmitButton, searchClearButton, emptyState, moduleApis) {
        function runFilter() {
            var query = ((searchInput && searchInput.value) || "").trim().toLowerCase();
            var visibleModules = 0;

            moduleApis.forEach(function (api) {
                var visibleRows = 0;

                api.rows.forEach(function (row) {
                    var haystack = row.getAttribute("data-search") || "";
                    var isMatch = !query || haystack.indexOf(query) !== -1;
                    row.hidden = !isMatch;
                    if (isMatch) {
                        visibleRows += 1;
                    }
                });

                api.module.hidden = visibleRows === 0;

                if (visibleRows > 0) {
                    visibleModules += 1;
                }

                if (query) {
                    api.module.open = visibleRows > 0;
                } else {
                    api.module.open = false;
                }
                api.module.style.height = "";
                api.module.style.overflow = "";

                api.syncBulkButtons();
            });

            if (emptyState) {
                emptyState.hidden = !query || visibleModules !== 0;
            }
        }

        function syncSearchClearButton() {
            if (!searchInput || !searchClearButton) {
                return;
            }
            searchClearButton.hidden = !searchInput.value.trim();
        }

        if (searchInput) {
            searchInput.addEventListener("input", runFilter);
            searchInput.addEventListener("input", syncSearchClearButton);
            searchInput.addEventListener("keydown", function (event) {
                if (
                    event.key !== "Enter" ||
                    event.shiftKey ||
                    event.ctrlKey ||
                    event.altKey ||
                    event.metaKey ||
                    event.isComposing
                ) {
                    return;
                }
                event.preventDefault();
                runFilter();
            });
        }

        if (searchSubmitButton) {
            searchSubmitButton.addEventListener("click", function () {
                runFilter();
            });
        }

        if (searchClearButton && searchInput) {
            searchClearButton.addEventListener("click", function () {
                searchInput.value = "";
                syncSearchClearButton();
                runFilter();
                searchInput.focus();
            });
        }

        syncSearchClearButton();
        runFilter();
    }

    ns.interactions = {
        bindModuleAccordionAnimation: bindModuleAccordionAnimation,
        bindSearch: bindSearch
    };
})(window.EMSPermissionEditor = window.EMSPermissionEditor || {}, window);
