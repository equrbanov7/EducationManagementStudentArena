"""
Core abstract models for EMS Arena project.
Base models that can be inherited by app models.
"""

import uuid

from django.db import models
from django.utils.text import slugify


class TimeStampedModel(models.Model):
    """
    Abstract model that provides self-updating created_at and updated_at fields.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """
    Abstract model that uses UUID as primary key.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """
    Abstract model that provides soft delete functionality.
    """

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class TitleSlugModel(models.Model):
    """
    Abstract model that provides title and auto-generated slug fields.
    """

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class ActiveManager(models.Manager):
    """
    Manager that returns only active records.
    """

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class ActiveModel(models.Model):
    """
    Abstract model that provides is_active field with custom manager.
    """

    is_active = models.BooleanField(default=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        abstract = True


class OrderedModel(models.Model):
    """
    Abstract model that provides ordering functionality.
    """

    order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        abstract = True
        ordering = ["order"]
