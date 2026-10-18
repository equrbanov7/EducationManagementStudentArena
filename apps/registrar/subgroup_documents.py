"""«Alt qrupa yerləşdirmə»nin SƏNƏDİ — fayl (PDF/JPG/PNG) və ya sərəncam nömrəsi + tarixi (sahib 2026-09-07).

Sahibin qaydası: alt qrupa əlavə SƏNƏDSİZ olmur. İki forma qəbul olunur və ikisi birlikdə də verilə bilər:

* **fayl** — təqdimat / sərəncamın skanı və ya fotosu. Yalnız ``.pdf`` / ``.jpg`` / ``.jpeg`` / ``.png``,
  ≤ 10 MB; məzmun imzası (magic bytes), markup/script rədd edilir, şəkil Pillow ilə yoxlanılır
  (:func:`core.upload_security.validate_uploaded_file`). Ad TƏSADÜFİ olur (``uuid4().hex`` + uzantı) və fayl
  qorunan media altında saxlanılır — mövcud :class:`GuestRosterDocument` sətri kimi (jurnal modalı da onu
  göstərir; oxu siyasəti ``core.media_policies.check_guest_roster_document_access``);
* **sərəncam** — nömrə (≤ 64 simvol) + tarix (ISO, gələcək tarix olmaz).

``document`` arqumenti çevikdir (25% təkrar imtahan axını öz müraciət sənədini ötürə bilsin):
``None`` · :class:`PlacementDocument` · ``dict`` (``file`` / ``number`` / ``date``) · yüklənmiş fayl ·
``FieldFile`` (mövcud saxlanmış fayl — oxunub yeni təsadüfi adla kopyalanır).
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db.models.fields.files import FieldFile
from django.utils import timezone

from core.upload_security import randomize_uploaded_filename, validate_uploaded_file

from . import subgroup_placement_errors as errors

ALLOWED_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png")
#: Brauzer bəzən ``application/octet-stream`` göndərir — məzmun imzası (``%PDF`` / JPEG / PNG) onsuz da yoxlanılır.
ALLOWED_MIME_TYPES = ("application/pdf", "image/jpeg", "image/pjpeg", "image/png", "application/octet-stream")
MAX_DOCUMENT_MB = 10
ORDER_NUMBER_MAX = 64


@dataclass(frozen=True)
class PlacementDocument:
    """Normallaşdırılmış sənəd: ``file`` (yüklənmiş/kopyalanmış fayl) və/və ya sərəncam."""

    file: object = None
    number: str = ""
    date: dt.date | None = None

    @property
    def has_file(self) -> bool:
        return self.file is not None

    @property
    def has_order(self) -> bool:
        return bool(self.number and self.date)


def _parse_date(raw):
    if raw in (None, ""):
        return None
    if isinstance(raw, dt.datetime):
        return raw.date()
    if isinstance(raw, dt.date):
        return raw
    try:
        return dt.date.fromisoformat(str(raw).strip())
    except ValueError:
        raise errors.SubgroupPlacementError(errors.DOCUMENT_INVALID, _invalid_date_message())


def _invalid_date_message():
    from django.utils.translation import pgettext

    return pgettext("registrar.subgroup_placement", "Sərəncam tarixi düzgün deyil.")


def _copy_field_file(field_file):
    """Saxlanmış faylı (məs. müraciət sənədi) yaddaşa oxuyub yeni yükləmə kimi qaytarır."""
    if not field_file:
        return None
    field_file.open("rb")
    try:
        content = field_file.read()
    finally:
        field_file.close()
    return ContentFile(content, name=os.path.basename(field_file.name or "document"))


def coerce(document) -> PlacementDocument:
    """Çağıranın verdiyi formanı :class:`PlacementDocument`-ə çevirir (hələ YOXLAMADAN)."""
    if document is None:
        return PlacementDocument()
    if isinstance(document, PlacementDocument):
        return document
    if isinstance(document, dict):
        file_obj = document.get("file")
        if isinstance(file_obj, FieldFile):
            file_obj = _copy_field_file(file_obj)
        return PlacementDocument(
            file=file_obj or None,
            number=" ".join(str(document.get("number") or "").split())[:ORDER_NUMBER_MAX],
            date=_parse_date(document.get("date")),
        )
    if isinstance(document, FieldFile):
        return PlacementDocument(file=_copy_field_file(document))
    if hasattr(document, "read"):
        return PlacementDocument(file=document)
    raise errors.SubgroupPlacementError(errors.DOCUMENT_INVALID)


def validate(document: PlacementDocument) -> PlacementDocument:
    """Sənəd qaydası: fayl VƏ YA (nömrə + tarix). Fayl məzmunca yoxlanılır, adı təsadüfiləşdirilir."""
    number_only = bool(document.number) and document.date is None
    date_only = document.date is not None and not document.number
    if not document.has_file and not document.has_order:
        if number_only or date_only:
            from django.utils.translation import pgettext

            raise errors.SubgroupPlacementError(
                errors.DOCUMENT_REQUIRED,
                pgettext("registrar.subgroup_placement", "Sərəncamın həm nömrəsi, həm tarixi yazılmalıdır."),
            )
        raise errors.SubgroupPlacementError(errors.DOCUMENT_REQUIRED)
    if document.date is not None and document.date > timezone.localdate():
        from django.utils.translation import pgettext

        raise errors.SubgroupPlacementError(
            errors.DOCUMENT_INVALID, pgettext("registrar.subgroup_placement", "Sərəncam tarixi gələcəkdə ola bilməz.")
        )
    if document.has_file:
        try:
            validate_uploaded_file(
                document.file,
                allowed_extensions=ALLOWED_EXTENSIONS,
                max_size_mb=MAX_DOCUMENT_MB,
                allowed_mime_types=ALLOWED_MIME_TYPES,
                allowed_mime_prefixes=(),
            )
        except ValidationError as exc:
            raise errors.SubgroupPlacementError(errors.DOCUMENT_INVALID, "; ".join(exc.messages))
        randomize_uploaded_filename(document.file)
    return document


def store(*, document: PlacementDocument, enrollment, actor, note: str = ""):
    """Faylı :class:`GuestRosterDocument` kimi saxlayır (fayl yoxdursa ``None``)."""
    if not document.has_file:
        return None
    from .models import GuestRosterDocument

    record = GuestRosterDocument(
        organization_id=enrollment.organization_id,
        enrollment=enrollment,
        document=document.file,
        note=str(note or "")[:255],
        uploaded_by=actor,
    )
    try:
        record.full_clean(exclude=["uploaded_by_name"])
    except ValidationError as exc:
        raise errors.SubgroupPlacementError(errors.DOCUMENT_INVALID, "; ".join(exc.messages))
    record.save()
    return record


__all__ = ["ALLOWED_EXTENSIONS", "MAX_DOCUMENT_MB", "PlacementDocument", "coerce", "store", "validate"]
