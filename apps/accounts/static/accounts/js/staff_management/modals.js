(function (ns, window, document) {
    "use strict";

    function initRevokeModal(ctx) {
        var revokeModal = document.getElementById("revokeSentInvitesConfirmModal");
        if (!revokeModal) {
            return;
        }

        var revokeTextNode = document.getElementById("revokeSentInvitesModalText");
        var revokeHintNode = document.getElementById("revokeSentInvitesModalHint");
        var revokeActionInput = document.getElementById("revokeSentInvitesAction");
        var revokeRoleTypeInput = document.getElementById("revokeSentInvitesRoleType");
        var revokeSingleInput = document.getElementById("revokeSentInvitesSingleUserId");
        var revokeSelectedInput = document.getElementById("revokeSentInvitesSelectedUserIds");
        var revokeConfirmBtn = document.getElementById("revokeSentInvitesConfirmBtn");

        revokeModal.addEventListener("show.bs.modal", function (event) {
            var trigger = event.relatedTarget;
            var mode = trigger ? (trigger.getAttribute("data-revoke-mode") || "bulk") : "bulk";
            var sourceForm = trigger ? trigger.closest("form") : null;

            if (revokeSingleInput) {
                revokeSingleInput.value = "";
            }
            if (revokeSelectedInput) {
                revokeSelectedInput.value = "";
            }
            if (revokeActionInput) {
                revokeActionInput.value = trigger
                    ? (trigger.getAttribute("data-revoke-action") || "revoke_sent_invites")
                    : "revoke_sent_invites";
            }
            if (revokeRoleTypeInput) {
                revokeRoleTypeInput.value = trigger
                    ? (trigger.getAttribute("data-revoke-role-type") || "student")
                    : "student";
            }
            if (revokeHintNode) {
                revokeHintNode.textContent = "";
            }
            if (revokeConfirmBtn) {
                revokeConfirmBtn.disabled = false;
            }

            if (mode === "single") {
                var singleUserId = trigger ? (trigger.getAttribute("data-single-revoke-user-id") || "") : "";
                var singleUsername = trigger
                    ? (trigger.getAttribute("data-single-revoke-username") || ctx.i18n.thisUser)
                    : ctx.i18n.thisUser;
                if (revokeSingleInput) {
                    revokeSingleInput.value = singleUserId;
                }
                if (revokeTextNode) {
                    revokeTextNode.textContent =
                        singleUsername + " \u00FC\u00E7\u00FCn g\u00F6nd\u0259rilmi\u015F d\u0259v\u0259ti geri \u00E7\u0259km\u0259k ist\u0259diyinizi t\u0259sdiql\u0259yin.";
                }
                return;
            }

            var selectedUserIds = ns.selection.getSelectedSentInviteUserIds(sourceForm);
            if (revokeSelectedInput) {
                revokeSelectedInput.value = selectedUserIds.join(",");
            }

            if (selectedUserIds.length) {
                if (revokeTextNode) {
                    revokeTextNode.textContent = ctx.i18n.withdrawSelectedInvites;
                }
                if (revokeHintNode) {
                    revokeHintNode.textContent = ctx.i18n.selectedInvites + " " + String(selectedUserIds.length);
                }
            } else {
                if (revokeTextNode) {
                    revokeTextNode.textContent = ctx.i18n.selectInviteFirst;
                }
                if (revokeHintNode) {
                    revokeHintNode.textContent = ctx.i18n.confirmButtonDisabled;
                }
                if (revokeConfirmBtn) {
                    revokeConfirmBtn.disabled = true;
                }
            }
        });
    }

    function initRemoveStudentModal(ctx) {
        var removeStudentModal = document.getElementById("removeStudentConfirmModal");
        if (!removeStudentModal) {
            return;
        }

        var userIdInput = document.getElementById("removeStudentModalUserId");
        var fullNameNode = document.getElementById("removeStudentModalFullName");
        var usernameNode = document.getElementById("removeStudentModalUsername");
        var emailNode = document.getElementById("removeStudentModalEmail");
        var orgNode = document.getElementById("removeStudentModalOrg");
        var roleNode = document.getElementById("removeStudentModalRole");
        var reasonInput = document.getElementById("removeStudentReasonInput");

        removeStudentModal.addEventListener("show.bs.modal", function (event) {
            var trigger = event.relatedTarget;
            if (!trigger) {
                return;
            }
            if (userIdInput) {
                userIdInput.value = trigger.getAttribute("data-student-user-id") || "";
            }
            if (fullNameNode) {
                fullNameNode.textContent = trigger.getAttribute("data-student-full-name") || "-";
            }
            if (usernameNode) {
                usernameNode.textContent = trigger.getAttribute("data-student-username") || ctx.i18n.thisUser;
            }
            if (emailNode) {
                emailNode.textContent = trigger.getAttribute("data-student-email") || "-";
            }
            if (orgNode) {
                orgNode.textContent = trigger.getAttribute("data-student-org") || "-";
            }
            if (roleNode) {
                roleNode.textContent = trigger.getAttribute("data-student-role") || ctx.i18n.studentRole;
            }
            if (reasonInput) {
                reasonInput.value = "";
            }
        });
    }

    function initPendingAddModal(ctx) {
        var pendingAddModal = document.getElementById("pendingAddConfirmModal");
        if (!pendingAddModal || !window.bootstrap) {
            return;
        }

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

        function fillPendingAddModal(users, mode) {
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
                pendingAddRole.textContent = firstUser ? firstUser.role : ctx.i18n.studentRole;
            }
            if (pendingAddLeadText) {
                pendingAddLeadText.textContent = mode === "bulk"
                    ? ctx.i18n.confirmAddSelected
                    : ctx.i18n.confirmAddSingle;
            }
            if (pendingAddHint) {
                pendingAddHint.textContent = users.length > 1
                    ? ctx.i18n.selectedUsers + " " + String(users.length)
                    : "";
            }
            if (pendingAddConfirmBtn) {
                pendingAddConfirmBtn.disabled = users.length === 0;
            }
        }

        document.querySelectorAll(".js-pending-add-confirm").forEach(function (button) {
            button.addEventListener("click", function () {
                fillPendingAddModal([
                    {
                        id: button.getAttribute("data-single-user-id") || "",
                        fullName: button.getAttribute("data-user-full-name") || "-",
                        username: button.getAttribute("data-user-username") || "-",
                        email: button.getAttribute("data-user-email") || "-",
                        role: button.getAttribute("data-target-role") || ctx.i18n.studentRole
                    }
                ], "single");
                pendingAddModalInstance.show();
            });
        });

        if (ctx.selection.pendingAddBulkBtn) {
            ctx.selection.pendingAddBulkBtn.addEventListener("click", function () {
                fillPendingAddModal(ns.selection.getSelectedUsers(ctx, ".pending-student-checkbox"), "bulk");
                pendingAddModalInstance.show();
            });
        }
    }

    function initInviteModal(ctx) {
        var inviteModal = document.getElementById("inviteConfirmModal");
        if (!inviteModal || !window.bootstrap) {
            return;
        }

        var inviteModalInstance = new window.bootstrap.Modal(inviteModal);
        var inviteActionInput = document.getElementById("inviteConfirmAction");
        var inviteRoleTypeInput = document.getElementById("inviteConfirmRoleType");
        var inviteSingleInput = document.getElementById("inviteConfirmSingleUserId");
        var inviteSelectedInput = document.getElementById("inviteConfirmSelectedUserIds");
        var inviteLeadText = document.getElementById("inviteConfirmLeadText");
        var inviteFullName = document.getElementById("inviteConfirmFullName");
        var inviteUsername = document.getElementById("inviteConfirmUsername");
        var inviteEmail = document.getElementById("inviteConfirmEmail");
        var inviteRole = document.getElementById("inviteConfirmRole");
        var inviteHint = document.getElementById("inviteConfirmHint");
        var inviteConfirmBtn = document.getElementById("inviteConfirmBtn");

        function fillInviteModal(users, mode, inviteConfig) {
            var firstUser = users.length ? users[0] : null;
            var effectiveConfig = inviteConfig || {};
            if (inviteActionInput) {
                inviteActionInput.value = effectiveConfig.action || "bulk_invite_students";
            }
            if (inviteRoleTypeInput) {
                inviteRoleTypeInput.value = effectiveConfig.roleType || "student";
            }
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
                inviteRole.textContent = firstUser ? firstUser.role : ctx.i18n.studentRole;
            }
            if (inviteLeadText) {
                inviteLeadText.textContent = mode === "bulk"
                    ? ctx.i18n.confirmInviteSelected
                    : ctx.i18n.confirmInviteSingle;
            }
            if (inviteHint) {
                inviteHint.textContent = users.length > 1
                    ? ctx.i18n.selectedUsers + " " + String(users.length)
                    : "";
            }
            if (inviteConfirmBtn) {
                inviteConfirmBtn.disabled = users.length === 0;
            }
        }

        ctx.selection.unassignedFormConfigs.forEach(function (config) {
            config.form.querySelectorAll(".js-invite-confirm-single").forEach(function (button) {
                button.addEventListener("click", function () {
                    fillInviteModal([
                        {
                            id: button.getAttribute("data-single-invite-user-id") || "",
                            fullName: button.getAttribute("data-user-full-name") || "-",
                            username: button.getAttribute("data-user-username") || "-",
                            email: button.getAttribute("data-user-email") || "-",
                            role: button.getAttribute("data-target-role") || ctx.i18n.studentRole
                        }
                    ], "single", {
                        action: button.getAttribute("data-invite-action") || "bulk_invite_students",
                        roleType: button.getAttribute("data-invite-role-type") || "student"
                    });
                    inviteModalInstance.show();
                });
            });

            if (config.bulkButton) {
                config.bulkButton.addEventListener("click", function () {
                    fillInviteModal(
                        ns.selection.getSelectedUsersWithin(ctx, config.form, ".unassigned-student-checkbox"),
                        "bulk",
                        {
                            action: config.bulkButton.getAttribute("data-invite-action") || "bulk_invite_students",
                            roleType: config.bulkButton.getAttribute("data-invite-role-type") || "student"
                        }
                    );
                    inviteModalInstance.show();
                });
            }
        });
    }

    ns.modals = {
        init: function (ctx) {
            initRevokeModal(ctx);
            initRemoveStudentModal(ctx);
            initPendingAddModal(ctx);
            initInviteModal(ctx);
        }
    };
})(window.EMSStaffManagement = window.EMSStaffManagement || {}, window, document);
