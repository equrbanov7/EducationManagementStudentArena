"""Keep the established physical journal UI until the combined UI is reviewed."""

from django.conf import settings


def enabled():
    return getattr(settings, "REGISTRAR_JOINT_JOURNAL_UI_ENABLED", False) is True
