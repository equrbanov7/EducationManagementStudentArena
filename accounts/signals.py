from django.apps import apps
from django.db.models.signals import post_migrate
from django.dispatch import receiver

DEFAULT_GROUPS = ["student", "teacher", "assistant_teacher", "moderator"]

@receiver(post_migrate)
def create_default_groups(sender, **kwargs):
    # yalnız "accounts" migrate olanda işlə (boşuna hər migrate-da qaçmasın)
    if sender.name != "accounts":
        return

    Group = apps.get_model("auth", "Group")

    for name in DEFAULT_GROUPS:
        Group.objects.get_or_create(name=name)
