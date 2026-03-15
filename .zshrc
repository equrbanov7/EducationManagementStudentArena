alias dj='DJANGO_SETTINGS_MODULE=config.settings.local python manage.py'
alias ddaphne='DJANGO_SETTINGS_MODULE=config.settings.local daphne -b 0.0.0.0 -p 8000 config.asgi:application'