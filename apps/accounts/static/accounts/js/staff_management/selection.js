(function (ns, document) {
    "use strict";

    function syncBulkButtonState(button, selectedCount, hasRows, isPermissionDisabled, tooltipText) {
        if (!button) {
            return;
        }
        var shouldDisable = isPermissionDisabled || !hasRows || selectedCount === 0;
        button.disabled = shouldDisable;
        if (!isPermissionDisabled && shouldDisable) {
            button.setAttribute("title", tooltipText);
        } else {
            button.removeAttribute("title");
        }
    }

    function userFromCheckbox(checkbox, fallbackRole) {
        return {
            id: checkbox.value || "",
            fullName: checkbox.getAttribute("data-user-full-name") || "-",
            username: checkbox.getAttribute("data-user-username") || "-",
            email: checkbox.getAttribute("data-user-email") || "-",
            role: checkbox.getAttribute("data-target-role") || fallbackRole
        };
    }

    ns.selection = {
        init: function (ctx) {
            var i18n = ctx.i18n;
            var selectAll = document.getElementById("selectAllPendingStudents");
            var pendingCheckboxes = Array.from(document.querySelectorAll(".pending-student-checkbox"));
            var pendingSelectableCheckboxes = pendingCheckboxes.filter(function (checkbox) {
                return !checkbox.disabled;
            });
            var pendingAddBulkBtn = document.querySelector(".js-pending-add-confirm-bulk");
            var pendingRemoveBulkBtn = document.querySelector(".js-pending-remove-bulk");
            var pendingAddBulkLabel = document.querySelector(".js-pending-add-bulk-label");
            var pendingAddDefaultLabel = pendingAddBulkBtn
                ? (pendingAddBulkBtn.getAttribute("data-default-label") || i18n.addSelectedUsers)
                : i18n.addSelectedUsers;
            var pendingAddSelectedLabelTemplate = pendingAddBulkBtn
                ? (pendingAddBulkBtn.getAttribute("data-selected-label") || i18n.addSelectedUsersCount)
                : i18n.addSelectedUsersCount;
            var pendingAddDisabledTooltip = pendingAddBulkBtn
                ? (pendingAddBulkBtn.getAttribute("data-disabled-tooltip") || i18n.selectAtLeastOneStudent)
                : i18n.selectAtLeastOneStudent;
            var pendingAddPermissionDisabled = pendingAddBulkBtn
                ? pendingAddBulkBtn.getAttribute("data-permission-disabled") === "1"
                : false;
            var pendingRemovePermissionDisabled = pendingRemoveBulkBtn
                ? pendingRemoveBulkBtn.getAttribute("data-permission-disabled") === "1"
                : false;
            var pendingRemoveDisabledTooltip = pendingRemoveBulkBtn
                ? (pendingRemoveBulkBtn.getAttribute("data-disabled-tooltip") || i18n.selectAtLeastOneUser)
                : i18n.selectAtLeastOneUser;

            var inviteForms = [];
            document
                .querySelectorAll("[data-unassigned-form], .js-invite-confirm-bulk, .js-invite-confirm-single")
                .forEach(function (node) {
                    var form = node && node.tagName === "FORM" ? node : node.closest("form");
                    if (!form || inviteForms.indexOf(form) !== -1) {
                        return;
                    }
                    if (!form.querySelector(".js-invite-confirm-bulk") && !form.querySelector(".js-invite-confirm-single")) {
                        return;
                    }
                    inviteForms.push(form);
                });

            var unassignedFormConfigs = inviteForms.map(function (form) {
                var bulkButton = form.querySelector(".js-invite-confirm-bulk");
                return {
                    form: form,
                    selectAll: form.querySelector("[data-select-all-unassigned]"),
                    checkboxes: Array.from(form.querySelectorAll(".unassigned-student-checkbox")),
                    bulkButton: bulkButton,
                    permissionDisabled: bulkButton ? bulkButton.getAttribute("data-permission-disabled") === "1" : false,
                    disabledTooltip: bulkButton
                        ? (bulkButton.getAttribute("data-disabled-tooltip") || i18n.selectAtLeastOneUser)
                        : i18n.selectAtLeastOneUser
                };
            });

            var sentInviteFormConfigs = Array.from(document.querySelectorAll("[data-sent-invites-form]")).map(
                function (form) {
                    var bulkButton = form.querySelector(".js-sent-invite-revoke-bulk");
                    return {
                        form: form,
                        selectAll: form.querySelector("[data-select-all-sent-invites]"),
                        checkboxes: Array.from(form.querySelectorAll(".sent-invite-checkbox")),
                        bulkButton: bulkButton,
                        permissionDisabled: bulkButton
                            ? bulkButton.getAttribute("data-permission-disabled") === "1"
                            : false,
                        disabledTooltip: bulkButton
                            ? (bulkButton.getAttribute("data-disabled-tooltip") || i18n.selectAtLeastOneUser)
                            : i18n.selectAtLeastOneUser
                    };
                }
            );

            function syncPendingBulkSelectionUi() {
                var selectedPendingCount = pendingSelectableCheckboxes.filter(function (checkbox) {
                    return checkbox.checked;
                }).length;
                var hasPendingRows = pendingSelectableCheckboxes.length > 0;

                if (pendingAddBulkLabel) {
                    pendingAddBulkLabel.textContent = selectedPendingCount > 0
                        ? pendingAddSelectedLabelTemplate.replace("{count}", String(selectedPendingCount))
                        : pendingAddDefaultLabel;
                }

                syncBulkButtonState(
                    pendingAddBulkBtn,
                    selectedPendingCount,
                    hasPendingRows,
                    pendingAddPermissionDisabled,
                    pendingAddDisabledTooltip
                );
                syncBulkButtonState(
                    pendingRemoveBulkBtn,
                    selectedPendingCount,
                    hasPendingRows,
                    pendingRemovePermissionDisabled,
                    pendingRemoveDisabledTooltip
                );

                if (selectAll) {
                    var canToggleAll = hasPendingRows && !pendingAddPermissionDisabled && !pendingRemovePermissionDisabled;
                    selectAll.disabled = !canToggleAll;
                    if (!canToggleAll) {
                        selectAll.checked = false;
                        selectAll.indeterminate = false;
                        return;
                    }

                    if (selectedPendingCount === 0) {
                        selectAll.checked = false;
                        selectAll.indeterminate = false;
                    } else if (selectedPendingCount === pendingSelectableCheckboxes.length) {
                        selectAll.checked = true;
                        selectAll.indeterminate = false;
                    } else {
                        selectAll.checked = false;
                        selectAll.indeterminate = true;
                    }
                }
            }

            function syncScopedBulkSelectionUi(config) {
                var selectableCheckboxes = config.checkboxes.filter(function (checkbox) {
                    return !checkbox.disabled;
                });
                var selectedCount = selectableCheckboxes.filter(function (checkbox) {
                    return checkbox.checked;
                }).length;
                var hasRows = selectableCheckboxes.length > 0;

                syncBulkButtonState(
                    config.bulkButton,
                    selectedCount,
                    hasRows,
                    config.permissionDisabled,
                    config.disabledTooltip
                );

                if (!config.selectAll) {
                    return;
                }

                var canToggleAll = hasRows && !config.permissionDisabled;
                config.selectAll.disabled = !canToggleAll;
                if (!canToggleAll) {
                    config.selectAll.checked = false;
                    config.selectAll.indeterminate = false;
                    return;
                }

                if (selectedCount === 0) {
                    config.selectAll.checked = false;
                    config.selectAll.indeterminate = false;
                } else if (selectedCount === selectableCheckboxes.length) {
                    config.selectAll.checked = true;
                    config.selectAll.indeterminate = false;
                } else {
                    config.selectAll.checked = false;
                    config.selectAll.indeterminate = true;
                }
            }

            if (selectAll) {
                selectAll.addEventListener("change", function () {
                    pendingSelectableCheckboxes.forEach(function (checkbox) {
                        checkbox.checked = selectAll.checked;
                    });
                    syncPendingBulkSelectionUi();
                });
            }
            pendingSelectableCheckboxes.forEach(function (checkbox) {
                checkbox.addEventListener("change", syncPendingBulkSelectionUi);
            });
            syncPendingBulkSelectionUi();

            unassignedFormConfigs.forEach(function (config) {
                if (config.selectAll) {
                    config.selectAll.addEventListener("change", function () {
                        config.checkboxes.forEach(function (checkbox) {
                            if (!checkbox.disabled) {
                                checkbox.checked = config.selectAll.checked;
                            }
                        });
                        syncScopedBulkSelectionUi(config);
                    });
                }
                config.checkboxes.forEach(function (checkbox) {
                    if (!checkbox.disabled) {
                        checkbox.addEventListener("change", function () {
                            syncScopedBulkSelectionUi(config);
                        });
                    }
                });
                syncScopedBulkSelectionUi(config);
            });

            sentInviteFormConfigs.forEach(function (config) {
                if (config.selectAll) {
                    config.selectAll.addEventListener("change", function () {
                        config.checkboxes.forEach(function (checkbox) {
                            if (!checkbox.disabled) {
                                checkbox.checked = config.selectAll.checked;
                            }
                        });
                        syncScopedBulkSelectionUi(config);
                    });
                }
                config.checkboxes.forEach(function (checkbox) {
                    if (!checkbox.disabled) {
                        checkbox.addEventListener("change", function () {
                            syncScopedBulkSelectionUi(config);
                        });
                    }
                });
                syncScopedBulkSelectionUi(config);
            });

            return {
                pendingAddBulkBtn: pendingAddBulkBtn,
                unassignedFormConfigs: unassignedFormConfigs
            };
        },

        getSelectedUsers: function (ctx, selector) {
            return Array.from(document.querySelectorAll(selector + ":checked"))
                .filter(function (checkbox) {
                    return !checkbox.disabled;
                })
                .map(function (checkbox) {
                    return userFromCheckbox(checkbox, ctx.i18n.studentRole);
                })
                .filter(function (entry) {
                    return entry.id !== "";
                });
        },

        getSelectedUsersWithin: function (ctx, container, selector) {
            return Array.from((container || document).querySelectorAll(selector + ":checked"))
                .filter(function (checkbox) {
                    return !checkbox.disabled;
                })
                .map(function (checkbox) {
                    return userFromCheckbox(checkbox, ctx.i18n.studentRole);
                })
                .filter(function (entry) {
                    return entry.id !== "";
                });
        },

        getSelectedSentInviteUserIds: function (container) {
            return Array.from((container || document).querySelectorAll(".sent-invite-checkbox:checked"))
                .filter(function (checkbox) {
                    return !checkbox.disabled;
                })
                .map(function (checkbox) {
                    return checkbox.value || "";
                })
                .filter(function (value) {
                    return value !== "";
                });
        }
    };
})(window.EMSStaffManagement = window.EMSStaffManagement || {}, document);
