"""Publik (girişsiz) möhür oxusu — layihədə ``bypass_rls()``-in ƏN DAR istifadəsi.

Niyə bypass? ``/yoxla/<kod>/`` sorğusunda tenant konteksti YOXDUR (anonim ziyarətçi, hansı universitetin
sənədi olduğu əvvəlcədən bilinmir) — RLS siyasəti ``organization_id = current_org`` olmadan heç bir sətri
göstərmir. ``live_exam``-ın PIN girişi ilə eyni sinif (kateqoriya **B** — publik token girişi,
``scripts/rls_bypass_inventory.py``):

* sorğu YALNIZ dəqiq, kanonik formaya salınmış 80 bitlik kod üzrə (``UNIQUE`` indeks) — siyahı, axtarış,
  prefiks uyğunluğu YOXDUR;
* yalnız publik səhifənin göstərdiyi sütunlar oxunur (``values``) — sahibin FK-sı, verən əməkdaş, struktur
  yolu oxunmur;
* yazı yoxdur; kontekst menecerdən çıxanda bypass bağlanır.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.rls import bypass_rls

from .models import DocType, DocumentSeal

STATUS_VALID = "valid"
STATUS_REVOKED = "revoked"

_PUBLIC_COLUMNS = (
    "code",
    "doc_type",
    "organization_id",
    "issued_at",
    "payload",
    "file_sha256",
    "revoked_at",
)


@dataclass(frozen=True)
class PublicSeal:
    code: str
    doc_type: str
    organization_id: object
    issued_at: object
    payload: dict
    file_sha256: str
    revoked_at: object

    @property
    def status(self) -> str:
        return STATUS_REVOKED if self.revoked_at is not None else STATUS_VALID

    @property
    def doc_type_label(self) -> str:
        try:
            return str(DocType(self.doc_type).label)
        except ValueError:
            return self.doc_type


def find_by_code(code: str | None) -> PublicSeal | None:
    """Kanonik kod → ``PublicSeal`` və ya ``None``. Kod ``codes.normalize``-dan keçmiş olmalıdır."""
    if not code:
        return None
    with bypass_rls():
        row = DocumentSeal.objects.filter(code=code).values(*_PUBLIC_COLUMNS).first()
    if row is None:
        return None
    row["payload"] = dict(row.get("payload") or {})
    return PublicSeal(**row)


__all__ = ["STATUS_REVOKED", "STATUS_VALID", "PublicSeal", "find_by_code"]
