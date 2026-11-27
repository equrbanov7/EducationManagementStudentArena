"""Seed or open one private course attachment in the offsite drill's disposable database."""

import hashlib
import re
import sys

import django
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import connection
from django.test import Client, override_settings


def exercise(action, media, marker):
    from apps.courses.models import Course, CourseResource
    from apps.organizations.models import Membership, Organization
    from core.constants import OrganizationType

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        if not re.fullmatch(r"ems_drill_[0-9a-f]{32}", cursor.fetchone()[0]) or not re.fullmatch(
            r"[0-9a-f]{32}", marker
        ):
            raise ValueError("Expected an isolated drill database and fixture ID")

    username = "drill_" + marker
    content = f"EMSArena restore drill attachment {marker}\n".encode()
    with override_settings(MEDIA_ROOT=media, MEDIA_ACCEL_REDIRECT_URL="", OBJECT_STORAGE_ENABLED=False):
        if action == "seed":
            user = get_user_model().objects.create_user(username=username)
            org = Organization.objects.create(
                name=username, org_type=OrganizationType.UNIVERSITY, owner=user, status="active", is_active=True
            )
            Membership.objects.update_or_create(
                user=user, organization=org, defaults={"role": org.roles.get(name="teacher"), "is_active": True}
            )
            course = Course.objects.create(title=marker, organization=org, owner=user)
            resource = CourseResource(course=course, title=marker)
            resource.file.save(f"{marker}.txt", ContentFile(content))
            return

        if action != "verify":
            raise ValueError("Expected seed or verify")
        resource = CourseResource.objects.select_related("course__owner").get(
            title=marker, course__owner__username=username
        )
        client = Client()
        client.force_login(resource.course.owner)
        response = client.get(resource.file.url)
        try:
            if response.status_code != 200 or not response.streaming:
                raise ValueError(f"Restored attachment GET failed (HTTP {response.status_code})")
            actual = hashlib.sha256()
            for chunk in response.streaming_content:
                actual.update(chunk)
            if actual.digest() != hashlib.sha256(content).digest():
                raise ValueError("Application served unexpected attachment bytes")
        finally:
            response.close()
        print("Restored course attachment opened through Django (HTTP 200, matching SHA-256).")


if __name__ == "__main__":
    django.setup()
    exercise(*sys.argv[1:])
