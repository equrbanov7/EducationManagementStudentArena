"""
Profile views package.

Split out of a single ~2,300-line ``profile.py`` module. The public view
callables are re-exported here so existing imports
(``from .profile import user_profile`` / ``views.profile_avatar`` in URLConf)
keep working unchanged.

Modules:
* ``main`` — ``user_profile`` GET orchestrator
* ``post_handler`` — POST-form handling for ``user_profile``
* ``avatar`` — ``profile_avatar`` view
* ``public`` — ``public_user_profile`` view
* ``statistics_export`` — ``statistics_export_csv`` view
* ``search`` — pure input-sanitization helpers
* ``constants`` — length limits, regexes, section-name sets
"""

from .avatar import profile_avatar
from .main import user_profile
from .public import public_user_profile
from .statistics_export import statistics_export_csv

__all__ = [
    "user_profile",
    "profile_avatar",
    "public_user_profile",
    "statistics_export_csv",
]
