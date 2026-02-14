/**
 * Profile page sidebar toggle functionality.
 */
document.addEventListener('DOMContentLoaded', function () {
    var toggleBtn = document.getElementById('sidebarToggle');
    var sidebar = document.getElementById('profileSidebar');

    if (!toggleBtn || !sidebar) {
        return;
    }

    toggleBtn.addEventListener('click', function () {
        var icon = this.querySelector('i');
        sidebar.classList.toggle('collapsed');

        if (sidebar.classList.contains('collapsed')) {
            icon.classList.remove('fa-chevron-left');
            icon.classList.add('fa-chevron-right');
            this.title = 'Sidebar-ı aç';
        } else {
            icon.classList.remove('fa-chevron-right');
            icon.classList.add('fa-chevron-left');
            this.title = 'Sidebar-ı bağla';
        }

        // Save state to localStorage
        localStorage.setItem('profileSidebarCollapsed', sidebar.classList.contains('collapsed'));
    });

    // Restore sidebar state on page load
    var isCollapsed = localStorage.getItem('profileSidebarCollapsed') === 'true';
    if (isCollapsed) {
        toggleBtn.click();
    }
});
