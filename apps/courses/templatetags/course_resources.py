"""Resurs modalı üçün tip üzrə yükləmə siyasəti (2026-10-19) — ``apps/courses/resource_upload.py``.

``{% resource_upload_policy as policy %}`` → ``policy.video.accept`` / ``.hint`` / ``.max_bytes`` / ``.max_mb``
/ ``.extensions`` / ``.formats``. Modal data-atributlara yazır, xarici JS oradan oxuyur (CSP: inline JS yoxdur).
"""

from django import template

from apps.courses.resource_upload import UPLOAD_BODY_MAX_BYTES, policy_for_template

register = template.Library()


@register.simple_tag
def resource_upload_policy():
    policy = policy_for_template()
    policy["body_max_bytes"] = UPLOAD_BODY_MAX_BYTES
    return policy
