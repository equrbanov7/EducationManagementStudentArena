"""EMS Arena base settings — apps komponenti.

Bu fayl `config/settings/base.py` tərəfindən paylaşılan namespace-də
`exec`-include olunur (django-split-settings üslubu). Ona görə burada
ayrıca import yoxdur — os, Path, messages, CSP sabitləri və `_env_*`
köməkçiləri base.py-dən gəlir. Sıra base.py-dəki _COMPONENTS siyahısı ilə
idarə olunur (asılılıqlar: bax base.py).
"""

# flake8: noqa: F821  (paylaşılan namespace: adlar base.py-dən gəlir)

# Application definition
INSTALLED_APPS = [
    "apps.courses.apps.CoursesConfig",
    "apps.blog",
    "apps.contact.apps.ContactConfig",
    "channels",
    "apps.live_exam",
    "apps.assignments",
    "apps.accounts.apps.AccountsConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.projects",
    "apps.labs",
    "apps.organizations.apps.OrganizationsConfig",
    "apps.registrar.apps.RegistrarConfig",
    "apps.syllabus.apps.SyllabusConfig",
    "apps.workload.apps.WorkloadConfig",
    "apps.legacy_import.apps.LegacyImportConfig",
    "apps.audit.apps.AuditConfig",
    "apps.monitoring.apps.MonitoringConfig",
    "apps.ai_assistant.apps.AIAssistantConfig",
    "daphne",
    "apps.exams",
    "apps.appeals.apps.AppealsConfig",
    "apps.trial_exams.apps.TrialExamsConfig",
    "core.admin_apps.SecureAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "csp",
]

MIDDLEWARE = [
    "core.middleware.RequestIdMiddleware",
    "core.middleware.MetricsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "csp.middleware.CSPMiddleware",
    "core.admin_security.AdminSecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Admin 2FA gate: parol keçmiş amma OTP təsdiqlənməmiş admin istifadəçini
    # verify-otp-dan başqa hər yerdən saxlayır (auth-dan dərhal sonra — pending
    # session heç bir authenticated səhifəyə çıxmasın). Bax core.admin_auth.
    "core.admin_auth.AdminOTPGateMiddleware",
    "core.middleware.RequestQueueMiddleware",
    "apps.accounts.middleware.SessionTimeoutMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.accounts.middleware.PostLoginRedirectGuardMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # "View as" — OrganizationMiddleware-dən ƏVVƏL: user swap-dan sonra
    # org/RLS konteksti hədəf istifadəçinin üzvlüyü üzərində qurulur.
    "apps.accounts.middleware.ViewAsMiddleware",
    "apps.organizations.middleware.OrganizationMiddleware",
    "apps.accounts.middleware.SuspendedOrganizationMiddleware",
    # First-login lock: provisioned users must set their own password + verify
    # email before using the system. Runs last (after auth/org/suspend checks) so
    # request.user and tenant context are resolved and a suspended org still logs
    # out first. Exempts the set-password view, logout, static, admin (see mw).
    "apps.accounts.middleware.FirstLoginPasswordMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.blog.context_processors.blog_navigation_context",
                "apps.organizations.context_processors.organization_context",
                "apps.accounts.context_processors.view_as_context",
                "core.context_processors.seo_context",
                "core.context_processors.feature_flags",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
