"""Unicode-aware exact name lookup on supported database engines."""

import re

from django.db import connections


def name_exists(queryset, name):
    if connections[queryset.db].vendor == "sqlite":
        # SQLite's built-in LIKE only folds ASCII; Django REGEXP uses Python.
        return queryset.filter(name__iregex=r"\A" + re.escape(name) + r"\Z").exists()
    return queryset.filter(name__iexact=name).exists()
