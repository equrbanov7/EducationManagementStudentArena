(function (ns, document) {
    "use strict";

    ns.filters = {
        init: function () {
            var managementFilterRoot = document.querySelector("[data-management-filter-root]");
            var managementAllButton = managementFilterRoot
                ? managementFilterRoot.querySelector("[data-management-all]")
                : null;
            var managementFilterButtons = managementFilterRoot
                ? Array.from(managementFilterRoot.querySelectorAll("[data-management-chip]"))
                : [];
            var managementPanels = Array.from(document.querySelectorAll("[data-management-panel]"));

            function getActiveManagementKeys() {
                return managementFilterButtons
                    .filter(function (button) {
                        return button.classList.contains("is-active");
                    })
                    .map(function (button) {
                        return button.getAttribute("data-management-chip") || "";
                    })
                    .filter(function (value) {
                        return value !== "";
                    });
            }

            function setAllManagementFiltersActive() {
                managementFilterButtons.forEach(function (button) {
                    button.classList.add("is-active");
                });
                if (managementAllButton) {
                    managementAllButton.classList.add("is-active");
                }
            }

            function syncManagementPanels() {
                if (!managementPanels.length) {
                    return;
                }

                if (!managementFilterButtons.length) {
                    managementPanels.forEach(function (panel) {
                        panel.hidden = false;
                    });
                    if (managementAllButton) {
                        managementAllButton.classList.add("is-active");
                    }
                    return;
                }

                var activeKeys = getActiveManagementKeys();
                if (!activeKeys.length) {
                    setAllManagementFiltersActive();
                    activeKeys = getActiveManagementKeys();
                }

                var showAllPanels = activeKeys.length === managementFilterButtons.length;
                if (managementAllButton) {
                    managementAllButton.classList.toggle("is-active", showAllPanels);
                    managementAllButton.setAttribute("aria-pressed", showAllPanels ? "true" : "false");
                }

                managementFilterButtons.forEach(function (button) {
                    button.setAttribute(
                        "aria-pressed",
                        button.classList.contains("is-active") ? "true" : "false"
                    );
                });

                managementPanels.forEach(function (panel) {
                    var panelKey = panel.getAttribute("data-management-panel") || "";
                    panel.hidden = !showAllPanels && activeKeys.indexOf(panelKey) === -1;
                });
            }

            if (managementAllButton) {
                managementAllButton.addEventListener("click", function () {
                    setAllManagementFiltersActive();
                    syncManagementPanels();
                });
            }

            managementFilterButtons.forEach(function (button) {
                button.addEventListener("click", function () {
                    var isAllState = managementFilterButtons.every(function (entry) {
                        return entry.classList.contains("is-active");
                    });

                    if (isAllState) {
                        managementFilterButtons.forEach(function (entry) {
                            entry.classList.remove("is-active");
                        });
                        button.classList.add("is-active");
                    } else {
                        button.classList.toggle("is-active");
                    }

                    syncManagementPanels();
                });
            });

            if (managementFilterButtons.length || managementPanels.length) {
                setAllManagementFiltersActive();
                syncManagementPanels();
            }
        }
    };
})(window.EMSStaffManagement = window.EMSStaffManagement || {}, document);
