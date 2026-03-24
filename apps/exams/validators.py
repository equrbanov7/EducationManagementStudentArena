# exam/validators.py

import os
import zipfile

from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

from core.upload_security import validate_zip_archive

# İcazə verilən fayl tipləri
ALLOWED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".zip"]

# Bloklanan (virus riskli) fayl tipləri
BLOCKED_EXTENSIONS = [
    ".exe",
    ".js",
    ".sh",
    ".bat",
    ".cmd",
    ".msi",
    ".php",
    ".html",
    ".htm",
    ".py",
    ".rb",
]


def validate_file_extension(file):
    ext = os.path.splitext(file.name)[1].lower()

    if ext in BLOCKED_EXTENSIONS:
        raise ValidationError(pgettext("exams.validator.error", "blocked_extension"))

    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(pgettext("exams.validator.error", "unsupported_extension"))


def validate_file_size(file):
    max_size = 10 * 1024 * 1024  # 10 MB

    if file.size > max_size:
        raise ValidationError(pgettext("exams.validator.error", "file_too_large"))


def validate_zip_contents(file):
    ext = os.path.splitext(file.name)[1].lower()

    if ext != ".zip":
        return  # ZIP deyilsə, çıxırıq

    try:
        zip_file = zipfile.ZipFile(file)
    except zipfile.BadZipFile:
        raise ValidationError(pgettext("exams.validator.error", "invalid_zip"))

    for info in zip_file.infolist():
        inner_ext = os.path.splitext(info.filename)[1].lower()

        # ZIP içində qovluq varsa, keçirik (çünki .ext olmur)
        if not inner_ext:
            continue

        if inner_ext in BLOCKED_EXTENSIONS:
            raise ValidationError(
                pgettext("exams.validator.error", "blocked_extension_in_zip").format(filename=info.filename)
            )

    # Apply centralized ZIP bomb / archive-abuse protection.
    validate_zip_archive(file)
