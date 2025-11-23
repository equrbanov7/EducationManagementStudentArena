# your_app/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from .models import Post, Subscriber # Post və Subscriber modellərini import et

# Yeni post üçün email göndərmək
@receiver(post_save, sender=Post)
def send_new_post_notification(sender, instance, created, **kwargs):
    # Yalnız yeni yaradılan və yayımlanan postlar üçün işləsin
    if created and instance.is_published: 
        
        # 1. Bütün aktiv abunəçiləri çək
        active_subscribers = Subscriber.objects.filter(is_active=True).values_list('email', flat=True)
        
        if not active_subscribers:
            return # Abunəçi yoxdursa dayandır

        # 2. Şablonu hazırla
        html_message = render_to_string(
            'email_templates/new_post_notification.html',
            {'post': instance}
        )
        
        # 3. Toplu mail göndər
        send_mail(
            f'YENİ MƏQALƏ: {instance.title}',
            f'Yeni məqalə yayımlandı: {instance.title}. Ətraflı: [Link]', # Text versiyası
            settings.DEFAULT_FROM_EMAIL,
            active_subscribers, # Bütün abunəçilərə göndər
            html_message=html_message,
            fail_silently=True, # Əgər xəta olsa proqram dayanmasın
        )
        # Qeyd: Yüzlərlə abunəçi varsa, bu, Asynchronous Tasks (Celery) vasitəsilə edilməlidir.

# signals.py faylını app konfiqurasiyasında aktivləşdir:

# your_app/apps.py
from django.apps import AppConfig

class YourAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'your_app'

    def ready(self):
        import your_app.signals # Sinyalları burada import edirik