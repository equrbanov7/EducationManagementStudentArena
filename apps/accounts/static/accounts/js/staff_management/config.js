(function (ns, document) {
    "use strict";

    var defaultI18n = {
        addSelectedUsers: "Add selected users to the organization",
        addSelectedUsersCount: "Add selected users to the organization ({count} selected)",
        selectAtLeastOneStudent: "Select at least 1 student",
        selectAtLeastOneUser: "Select at least 1 user",
        studentRole: "Student",
        thisUser: "This user",
        withdrawSelectedInvites: "Please confirm that you want to withdraw the selected invites.",
        selectedInvites: "Selected invites:",
        selectInviteFirst: "Please select at least one invite first.",
        confirmButtonDisabled: "The confirm button is disabled in this state.",
        confirmAddSelected: "Please confirm that you want to add the selected user(s) to the organization.",
        confirmAddSingle: "Please confirm that you want to add this user to the organization.",
        selectedUsers: "Selected users:",
        confirmInviteSelected: "Please confirm that you want to invite the selected user(s).",
        confirmInviteSingle: "Please confirm that you want to invite this user."
    };

    function readScriptData() {
        var node = document.getElementById("staff-management-script-data");
        if (!node) {
            return {};
        }
        try {
            return JSON.parse(node.textContent || "{}");
        } catch (error) {
            return {};
        }
    }

    ns.config = {
        createContext: function () {
            var scriptData = readScriptData();
            return {
                i18n: Object.assign({}, defaultI18n, scriptData.i18n || {})
            };
        }
    };
})(window.EMSStaffManagement = window.EMSStaffManagement || {}, document);
