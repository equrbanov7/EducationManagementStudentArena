"""An organization's own catalogue entries and overrides of shipped help guides."""

from uuid import uuid4

from django.db import models

from .faq_storage import faq_upload_storage


def faq_upload_path(instance, filename):
    suffix = filename.rsplit(".", 1)[-1].lower()
    return f"faq_guides/{instance.organization_id}/{uuid4().hex}.{suffix}"


class FaqVideoGuide(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    key = models.SlugField(max_length=100)
    title = models.CharField(max_length=200, blank=True)
    topic = models.CharField(max_length=120, blank=True)
    steps = models.JSONField(default=list)
    audience_roles = models.JSONField(default=list)
    required_guides = models.JSONField(default=list, blank=True)
    chapters = models.JSONField(default=list)
    video_file = models.FileField(upload_to=faq_upload_path, storage=faq_upload_storage, blank=True)
    subtitle_file = models.FileField(upload_to=faq_upload_path, storage=faq_upload_storage, blank=True)
    omit_subtitles = models.BooleanField(default=False)
    duration = models.FloatField(default=0)
    hidden = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("organization", "key"), name="accounts_unique_faq_guide")]
