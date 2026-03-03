/**
 * Manage roles interactions:
 * - Save button loading state during submit.
 * - Optional table filtering for legacy standalone page usage.
 */
document.addEventListener("DOMContentLoaded", function () {
    var roleForms = document.querySelectorAll(".js-manage-roles-form");
    roleForms.forEach(function (form) {
        form.addEventListener("submit", function () {
            var saveButton = form.querySelector("[data-manage-roles-save-btn]");
            if (!saveButton) {
                return;
            }

            var savingLabel = saveButton.getAttribute("data-saving-label") || "Saving...";
            saveButton.disabled = true;
            saveButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>'
                + savingLabel;
        });
    });
});

function filterUsers() {
    var input = document.getElementById("searchInput");
    var table = document.getElementById("usersTable");
    if (!input || !table) {
        return;
    }

    var filter = (input.value || "").toUpperCase();
    var rows = table.getElementsByTagName("tr");
    for (var i = 1; i < rows.length; i++) {
        var userInfo = rows[i].getElementsByClassName("user-info")[0];
        if (!userInfo) {
            continue;
        }
        var text = userInfo.textContent || userInfo.innerText || "";
        rows[i].style.display = text.toUpperCase().indexOf(filter) > -1 ? "" : "none";
    }
}
