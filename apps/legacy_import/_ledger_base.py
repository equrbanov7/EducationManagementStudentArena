"""Legacy import ledger-inin paylaşılan primitivləri (pattern, validator, abstract baza).

``models.py`` və ``review_models.py`` eyni token/digest formatlarını və eyni
"silinməyən ledger" davranışını paylaşır. Bu modul yalnız həmin primitivləri
saxlayır — model tərifi yoxdur, ona görə import zənciri dövrə yaratmır.
"""

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.db.models.deletion import ProtectedError

TOKEN_PATTERN = r"^[a-z0-9][a-z0-9._-]*$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
OPAQUE_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$"
MODEL_LABEL_PATTERN = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"
_RUN_MODE_CHECK = Q(mode__in=["profile", "rehearsal", "cutover"])
_RUN_ACCOUNTING_CHECK = Q(accounting_mode__in=["row", "batch"])

token_validator = RegexValidator(
    regex=TOKEN_PATTERN,
    message="Yalnız kiçik hərf, rəqəm, nöqtə, alt xətt və defis istifadə edilə bilər.",
)
sha256_validator = RegexValidator(
    regex=SHA256_PATTERN,
    message="Dəyər kiçik hərfli 64 simvolluq SHA-256 hex digest olmalıdır.",
)
opaque_key_validator = RegexValidator(
    regex=OPAQUE_KEY_PATTERN,
    message="Açar yalnız opaque identifikator simvollarından ibarət olmalıdır.",
)
model_label_validator = RegexValidator(
    regex=MODEL_LABEL_PATTERN,
    message="Target model etiketi app_label.model_name formatında olmalıdır.",
)


class _NoDeleteQuerySet(models.QuerySet):
    def delete(self):
        raise ProtectedError("Legacy import ledger sətirləri silinə bilməz.", self)


class _NoDeleteManager(models.Manager.from_queryset(_NoDeleteQuerySet)):
    pass


class _NonDeletableLedgerModel(models.Model):
    objects = _NoDeleteManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        raise ProtectedError("Legacy import ledger sətirləri silinə bilməz.", [self])
