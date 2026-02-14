/**
 * Manage Roles page - client-side search functionality.
 */
function filterUsers() {
    var input = document.getElementById('searchInput');
    var filter = input.value.toUpperCase();
    var table = document.getElementById('usersTable');
    if (!table) return;
    var rows = table.getElementsByTagName('tr');

    for (var i = 1; i < rows.length; i++) {
        var userInfo = rows[i].getElementsByClassName('user-info')[0];
        if (userInfo) {
            var text = userInfo.textContent || userInfo.innerText;
            rows[i].style.display = text.toUpperCase().indexOf(filter) > -1 ? '' : 'none';
        }
    }
}
