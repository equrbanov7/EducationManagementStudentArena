/*
 * bulk_selection.js
 * Source: apps/accounts/templates/accounts/partials/student_org_management/_scripts.html
 * Student-org management: select-all + per-row bulk selection state for pending /
 * unassigned / sent-invite tables, and the add / invite / revoke / remove confirm
 * modals. i18n literals read from the .js-som-i18n JSON island.
 * AJAX-safe: EMSReady-wrapped, null-safe, per-element idempotency guards (dataset.somBound)
 * so listeners are not stacked when the section re-runs after a swap.
 */
(function () {
    "use strict";

    function readI18n() {
        var el = document.querySelector(".js-som-i18n");
        if (!el) { return {}; }
        try { return JSON.parse(el.textContent); } catch (e) { return {}; }
    }

    window.EMSReady(function () {
        var I18N = readI18n();

        var selectAll = document.getElementById("selectAllPendingStudents");
        var pendingCheckboxes = Array.from(document.querySelectorAll(".pending-student-checkbox"));
        var pendingSelectableCheckboxes = pendingCheckboxes.filter(function (checkbox) {
            return !checkbox.disabled;
        });
        var pendingAddBulkBtn = document.querySelector(".js-pending-add-confirm-bulk");
        var pendingRemoveBulkBtn = document.querySelector(".js-pending-remove-bulk");
        var pendingAddBulkLabel = document.querySelector(".js-pending-add-bulk-label");
        var pendingAddDefaultLabel = pendingAddBulkBtn
            ? (pendingAddBulkBtn.getAttribute("data-default-label") || I18N.add_selected)
            : I18N.add_selected;
        var pendingAddSelectedLabelTemplate = pendingAddBulkBtn
            ? (pendingAddBulkBtn.getAttribute("data-selected-label") || I18N.add_selected_count)
            : I18N.add_selected_count;
        var pendingAddDisabledTooltip = pendingAddBulkBtn
            ? (pendingAddBulkBtn.getAttribute("data-disabled-tooltip") || I18N.min_one_student)
            : I18N.min_one_student;
        var pendingAddPermissionDisabled = pendingAddBulkBtn
            ? pendingAddBulkBtn.getAttribute("data-permission-disabled") === "1"
            : false;
        var pendingRemovePermissionDisabled = pendingRemoveBulkBtn
            ? pendingRemoveBulkBtn.getAttribute("data-permission-disabled") === "1"
            : false;
        var pendingRemoveDisabledTooltip = pendingRemoveBulkBtn
            ? (pendingRemoveBulkBtn.getAttribute("data-disabled-tooltip") || I18N.min_one)
            : I18N.min_one;

        var selectAllUnassigned = document.getElementById("selectAllUnassignedStudents");
        var unassignedCheckboxes = Array.from(document.querySelectorAll(".unassigned-student-checkbox"));
        var unassignedSelectableCheckboxes = unassignedCheckboxes.filter(function (checkbox) {
            return !checkbox.disabled;
        });
        var inviteBulkBtn = document.querySelector(".js-invite-confirm-bulk");
        var unassignedPermissionDisabled = inviteBulkBtn
            ? inviteBulkBtn.getAttribute("data-permission-disabled") === "1"
            : false;
        var unassignedDisabledTooltip = inviteBulkBtn
            ? (inviteBulkBtn.getAttribute("data-disabled-tooltip") || I18N.min_one)
            : I18N.min_one;

        var selectAllSentInvites = document.getElementById("selectAllSentInvites");
        var sentInviteCheckboxes = Array.from(document.querySelectorAll(".sent-invite-checkbox"));
        var sentInviteSelectableCheckboxes = sentInviteCheckboxes.filter(function (checkbox) {
            return !checkbox.disabled;
        });
        var sentInviteRevokeBulkBtn = document.querySelector(".js-sent-invite-revoke-bulk");
        var sentInvitePermissionDisabled = sentInviteRevokeBulkBtn
            ? sentInviteRevokeBulkBtn.getAttribute("data-permission-disabled") === "1"
            : false;
        var sentInviteDisabledTooltip = sentInviteRevokeBulkBtn
            ? (sentInviteRevokeBulkBtn.getAttribute("data-disabled-tooltip") || I18N.min_one)
            : I18N.min_one;

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

        function syncUnassignedBulkSelectionUi() {
            var selectedCount = unassignedSelectableCheckboxes.filter(function (checkbox) {
                return checkbox.checked;
            }).length;
            var hasRows = unassignedSelectableCheckboxes.length > 0;

            syncBulkButtonState(
                inviteBulkBtn,
                selectedCount,
                hasRows,
                unassignedPermissionDisabled,
                unassignedDisabledTooltip
            );

            if (selectAllUnassigned) {
                var canToggleAll = hasRows && !unassignedPermissionDisabled;
                selectAllUnassigned.disabled = !canToggleAll;
                if (!canToggleAll) {
                    selectAllUnassigned.checked = false;
                    selectAllUnassigned.indeterminate = false;
                    return;
                }

                if (selectedCount === 0) {
                    selectAllUnassigned.checked = false;
                    selectAllUnassigned.indeterminate = false;
                } else if (selectedCount === unassignedSelectableCheckboxes.length) {
                    selectAllUnassigned.checked = true;
                    selectAllUnassigned.indeterminate = false;
                } else {
                    selectAllUnassigned.checked = false;
                    selectAllUnassigned.indeterminate = true;
                }
            }
        }

        function syncSentInvitesBulkSelectionUi() {
            var selectedCount = sentInviteSelectableCheckboxes.filter(function (checkbox) {
                return checkbox.checked;
            }).length;
            var hasRows = sentInviteSelectableCheckboxes.length > 0;

            syncBulkButtonState(
                sentInviteRevokeBulkBtn,
                selectedCount,
                hasRows,
                sentInvitePermissionDisabled,
                sentInviteDisabledTooltip
            );

            if (selectAllSentInvites) {
                var canToggleAll = hasRows && !sentInvitePermissionDisabled;
                selectAllSentInvites.disabled = !canToggleAll;
                if (!canToggleAll) {
                    selectAllSentInvites.checked = false;
                    selectAllSentInvites.indeterminate = false;
                    return;
                }

                if (selectedCount === 0) {
                    selectAllSentInvites.checked = false;
                    selectAllSentInvites.indeterminate = false;
                } else if (selectedCount === sentInviteSelectableCheckboxes.length) {
                    selectAllSentInvites.checked = true;
                    selectAllSentInvites.indeterminate = false;
                } else {
                    selectAllSentInvites.checked = false;
                    selectAllSentInvites.indeterminate = true;
                }
            }
        }

        if (selectAll && selectAll.dataset.somBound !== "1") {
            selectAll.dataset.somBound = "1";
            selectAll.addEventListener("change", function () {
                pendingSelectableCheckboxes.forEach(function (checkbox) {
                    checkbox.checked = selectAll.checked;
                });
                syncPendingBulkSelectionUi();
            });
        }
        pendingSelectableCheckboxes.forEach(function (checkbox) {
            if (checkbox.dataset.somBound === "1") { return; }
            checkbox.dataset.somBound = "1";
            checkbox.addEventListener("change", syncPendingBulkSelectionUi);
        });
        syncPendingBulkSelectionUi();

        if (selectAllUnassigned && selectAllUnassigned.dataset.somBound !== "1") {
            selectAllUnassigned.dataset.somBound = "1";
            selectAllUnassigned.addEventListener("change", function () {
                unassignedSelectableCheckboxes.forEach(function (checkbox) {
                    checkbox.checked = selectAllUnassigned.checked;
                });
                syncUnassignedBulkSelectionUi();
            });
        }
        unassignedSelectableCheckboxes.forEach(function (checkbox) {
            if (checkbox.dataset.somBound === "1") { return; }
            checkbox.dataset.somBound = "1";
            checkbox.addEventListener("change", syncUnassignedBulkSelectionUi);
        });
        syncUnassignedBulkSelectionUi();

        if (selectAllSentInvites && selectAllSentInvites.dataset.somBound !== "1") {
            selectAllSentInvites.dataset.somBound = "1";
            selectAllSentInvites.addEventListener("change", function () {
                sentInviteSelectableCheckboxes.forEach(function (checkbox) {
                    checkbox.checked = selectAllSentInvites.checked;
                });
                syncSentInvitesBulkSelectionUi();
            });
        }
        sentInviteSelectableCheckboxes.forEach(function (checkbox) {
            if (checkbox.dataset.somBound === "1") { return; }
            checkbox.dataset.somBound = "1";
            checkbox.addEventListener("change", syncSentInvitesBulkSelectionUi);
        });
        syncSentInvitesBulkSelectionUi();

        function getSelectedUsers(selector) {
            return Array.from(document.querySelectorAll(selector + ":checked"))
                .filter(function (checkbox) {
                    return !checkbox.disabled;
                })
                .map(function (checkbox) {
                    return {
                        id: checkbox.value || "",
                        fullName: checkbox.getAttribute("data-user-full-name") || "-",
                        username: checkbox.getAttribute("data-user-username") || "-",
                        email: checkbox.getAttribute("data-user-email") || "-",
                        role: checkbox.getAttribute("data-target-role") || I18N.role_student,
                    };
                })
                .filter(function (entry) {
                    return entry.id !== "";
                });
        }

        function getSelectedSentInviteUserIds() {
            return Array.from(document.querySelectorAll(".sent-invite-checkbox:checked"))
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

        var revokeModal = document.getElementById("revokeSentInvitesConfirmModal");
        if (revokeModal && revokeModal.dataset.somBound !== "1") {
            revokeModal.dataset.somBound = "1";
            var revokeTextNode = document.getElementById("revokeSentInvitesModalText");
            var revokeHintNode = document.getElementById("revokeSentInvitesModalHint");
            var revokeSingleInput = document.getElementById("revokeSentInvitesSingleUserId");
            var revokeSelectedInput = document.getElementById("revokeSentInvitesSelectedUserIds");
            var revokeConfirmBtn = document.getElementById("revokeSentInvitesConfirmBtn");

            revokeModal.addEventListener("show.bs.modal", function (event) {
                var trigger = event.relatedTarget;
                var mode = trigger ? (trigger.getAttribute("data-revoke-mode") || "bulk") : "bulk";

                if (revokeSingleInput) {
                    revokeSingleInput.value = "";
                }
                if (revokeSelectedInput) {
                    revokeSelectedInput.value = "";
                }
                if (revokeHintNode) {
                    revokeHintNode.textContent = "";
                }
                if (revokeConfirmBtn) {
                    revokeConfirmBtn.disabled = false;
                }

                if (mode === "single") {
                    var singleUserId = trigger ? (trigger.getAttribute("data-single-revoke-user-id") || "") : "";
                    var singleUsername = trigger ? (trigger.getAttribute("data-single-revoke-username") || I18N.this_user) : I18N.this_user;
                    if (revokeSingleInput) {
                        revokeSingleInput.value = singleUserId;
                    }
                    if (revokeTextNode) {
                        revokeTextNode.textContent = singleUsername + " " + I18N.revoke_single_suffix;
                    }
                    return;
                }

                var selectedUserIds = getSelectedSentInviteUserIds();
                if (revokeSelectedInput) {
                    revokeSelectedInput.value = selectedUserIds.join(",");
                }

                if (selectedUserIds.length) {
                    if (revokeTextNode) {
                        revokeTextNode.textContent = I18N.revoke_selected_confirm;
                    }
                    if (revokeHintNode) {
                        revokeHintNode.textContent = I18N.selected_invite_count + ": " + String(selectedUserIds.length);
                    }
                } else {
                    if (revokeTextNode) {
                        revokeTextNode.textContent = I18N.select_one_invite_first;
                    }
                    if (revokeHintNode) {
                        revokeHintNode.textContent = I18N.confirm_disabled_hint;
                    }
                    if (revokeConfirmBtn) {
                        revokeConfirmBtn.disabled = true;
                    }
                }
            });
        }

        var removeStudentModal = document.getElementById("removeStudentConfirmModal");
        if (removeStudentModal && removeStudentModal.dataset.somBound !== "1") {
            removeStudentModal.dataset.somBound = "1";
            var userIdInput = document.getElementById("removeStudentModalUserId");
            var fullNameNode = document.getElementById("removeStudentModalFullName");
            var usernameNode = document.getElementById("removeStudentModalUsername");
            var emailNode = document.getElementById("removeStudentModalEmail");
            var orgNode = document.getElementById("removeStudentModalOrg");
            var roleNode = document.getElementById("removeStudentModalRole");
            var reasonInput = document.getElementById("removeStudentReasonInput");
            removeStudentModal.addEventListener("show.bs.modal", function (event) {
                var trigger = event.relatedTarget;
                if (!trigger) { return; }
                if (userIdInput) {
                    userIdInput.value = trigger.getAttribute("data-student-user-id") || "";
                }
                if (fullNameNode) {
                    fullNameNode.textContent = trigger.getAttribute("data-student-full-name") || "-";
                }
                if (usernameNode) {
                    usernameNode.textContent = trigger.getAttribute("data-student-username") || I18N.this_user;
                }
                if (emailNode) {
                    emailNode.textContent = trigger.getAttribute("data-student-email") || "-";
                }
                if (orgNode) {
                    orgNode.textContent = trigger.getAttribute("data-student-org") || "-";
                }
                if (roleNode) {
                    roleNode.textContent = trigger.getAttribute("data-student-role") || I18N.role_student;
                }
                if (reasonInput) {
                    reasonInput.value = "";
                }
            });
        }

        var pendingAddModal = document.getElementById("pendingAddConfirmModal");
        if (pendingAddModal && window.bootstrap && pendingAddModal.dataset.somBound !== "1") {
            pendingAddModal.dataset.somBound = "1";
            var pendingAddModalInstance = new window.bootstrap.Modal(pendingAddModal);
            var pendingAddSingleInput = document.getElementById("pendingAddSingleUserId");
            var pendingAddSelectedInput = document.getElementById("pendingAddSelectedUserIds");
            var pendingAddLeadText = document.getElementById("pendingAddLeadText");
            var pendingAddFullName = document.getElementById("pendingAddModalFullName");
            var pendingAddUsername = document.getElementById("pendingAddModalUsername");
            var pendingAddEmail = document.getElementById("pendingAddModalEmail");
            var pendingAddRole = document.getElementById("pendingAddModalRole");
            var pendingAddHint = document.getElementById("pendingAddModalHint");
            var pendingAddConfirmBtn = document.getElementById("pendingAddConfirmBtn");

            var fillPendingAddModal = function (users, mode) {
                var firstUser = users.length ? users[0] : null;
                if (pendingAddSingleInput) {
                    pendingAddSingleInput.value = mode === "single" && firstUser ? firstUser.id : "";
                }
                if (pendingAddSelectedInput) {
                    pendingAddSelectedInput.value = mode === "bulk"
                        ? users.map(function (entry) { return entry.id; }).join(",")
                        : "";
                }
                if (pendingAddFullName) {
                    pendingAddFullName.textContent = firstUser ? firstUser.fullName : "-";
                }
                if (pendingAddUsername) {
                    pendingAddUsername.textContent = firstUser ? firstUser.username : "-";
                }
                if (pendingAddEmail) {
                    pendingAddEmail.textContent = firstUser ? firstUser.email : "-";
                }
                if (pendingAddRole) {
                    pendingAddRole.textContent = firstUser ? firstUser.role : I18N.role_student;
                }
                if (pendingAddLeadText) {
                    pendingAddLeadText.textContent = mode === "bulk"
                        ? I18N.add_lead
                        : I18N.add_lead_single;
                }
                if (pendingAddHint) {
                    pendingAddHint.textContent = users.length > 1
                        ? I18N.selected_user_count + ": " + String(users.length)
                        : "";
                }
                if (pendingAddConfirmBtn) {
                    pendingAddConfirmBtn.disabled = users.length === 0;
                }
            };

            document.querySelectorAll(".js-pending-add-confirm").forEach(function (button) {
                if (button.dataset.somBound === "1") { return; }
                button.dataset.somBound = "1";
                button.addEventListener("click", function () {
                    fillPendingAddModal(
                        [{
                            id: button.getAttribute("data-single-user-id") || "",
                            fullName: button.getAttribute("data-user-full-name") || "-",
                            username: button.getAttribute("data-user-username") || "-",
                            email: button.getAttribute("data-user-email") || "-",
                            role: button.getAttribute("data-target-role") || I18N.role_student,
                        }],
                        "single"
                    );
                    pendingAddModalInstance.show();
                });
            });

            if (pendingAddBulkBtn && pendingAddBulkBtn.dataset.somBulkBound !== "1") {
                pendingAddBulkBtn.dataset.somBulkBound = "1";
                pendingAddBulkBtn.addEventListener("click", function () {
                    fillPendingAddModal(getSelectedUsers(".pending-student-checkbox"), "bulk");
                    pendingAddModalInstance.show();
                });
            }
        }

        var inviteModal = document.getElementById("inviteConfirmModal");
        if (inviteModal && window.bootstrap && inviteModal.dataset.somBound !== "1") {
            inviteModal.dataset.somBound = "1";
            var inviteModalInstance = new window.bootstrap.Modal(inviteModal);
            var inviteSingleInput = document.getElementById("inviteConfirmSingleUserId");
            var inviteSelectedInput = document.getElementById("inviteConfirmSelectedUserIds");
            var inviteLeadText = document.getElementById("inviteConfirmLeadText");
            var inviteFullName = document.getElementById("inviteConfirmFullName");
            var inviteUsername = document.getElementById("inviteConfirmUsername");
            var inviteEmail = document.getElementById("inviteConfirmEmail");
            var inviteRole = document.getElementById("inviteConfirmRole");
            var inviteHint = document.getElementById("inviteConfirmHint");
            var inviteConfirmBtn = document.getElementById("inviteConfirmBtn");

            var fillInviteModal = function (users, mode) {
                var firstUser = users.length ? users[0] : null;
                if (inviteSingleInput) {
                    inviteSingleInput.value = mode === "single" && firstUser ? firstUser.id : "";
                }
                if (inviteSelectedInput) {
                    inviteSelectedInput.value = mode === "bulk"
                        ? users.map(function (entry) { return entry.id; }).join(",")
                        : "";
                }
                if (inviteFullName) {
                    inviteFullName.textContent = firstUser ? firstUser.fullName : "-";
                }
                if (inviteUsername) {
                    inviteUsername.textContent = firstUser ? firstUser.username : "-";
                }
                if (inviteEmail) {
                    inviteEmail.textContent = firstUser ? firstUser.email : "-";
                }
                if (inviteRole) {
                    inviteRole.textContent = firstUser ? firstUser.role : I18N.role_student;
                }
                if (inviteLeadText) {
                    inviteLeadText.textContent = mode === "bulk"
                        ? I18N.invite_lead
                        : I18N.invite_lead_single;
                }
                if (inviteHint) {
                    inviteHint.textContent = users.length > 1
                        ? I18N.selected_user_count + ": " + String(users.length)
                        : "";
                }
                if (inviteConfirmBtn) {
                    inviteConfirmBtn.disabled = users.length === 0;
                }
            };

            document.querySelectorAll(".js-invite-confirm-single").forEach(function (button) {
                if (button.dataset.somBound === "1") { return; }
                button.dataset.somBound = "1";
                button.addEventListener("click", function () {
                    fillInviteModal(
                        [{
                            id: button.getAttribute("data-single-invite-user-id") || "",
                            fullName: button.getAttribute("data-user-full-name") || "-",
                            username: button.getAttribute("data-user-username") || "-",
                            email: button.getAttribute("data-user-email") || "-",
                            role: button.getAttribute("data-target-role") || I18N.role_student,
                        }],
                        "single"
                    );
                    inviteModalInstance.show();
                });
            });

            if (inviteBulkBtn && inviteBulkBtn.dataset.somBulkBound !== "1") {
                inviteBulkBtn.dataset.somBulkBound = "1";
                inviteBulkBtn.addEventListener("click", function () {
                    fillInviteModal(getSelectedUsers(".unassigned-student-checkbox"), "bulk");
                    inviteModalInstance.show();
                });
            }
        }
    });
})();
