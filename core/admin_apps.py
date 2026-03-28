from django.contrib.admin.apps import AdminConfig


class SecureAdminConfig(AdminConfig):
    default_site = "core.admin_site.EMSArenaAdminSite"
