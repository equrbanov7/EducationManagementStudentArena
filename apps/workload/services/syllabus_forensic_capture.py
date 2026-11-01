"""Fresh independent fixed027/029 READ ONLY body capsules; never normal usable content."""

from .syllabus_content_export import _capture


def capture(username, batch):
    return _capture(username, batch, _forensic=True)
