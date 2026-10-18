"""«Əmək müqavilələri» sabitləri (sahib tələbi, 2026-10-19).

Sahib: «Kadrlar üçün yer et, müəllimlərin əmək müqaviləsinə uyğun yer olsun — təkcə müəllimdə yox, hər kəs
işləyən. Müqavilə bitərkən HR və həmin şəxsə bildiriş getsin; «müqavilə göndərildi» seçiləndə işçiyə
«daxil olub e-poçtdan təsdiqləyin» bildirişi getsin.»
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext_lazy

CTX = "hr_contracts"

#: İcazə açarları (kataloq: ``apps/organizations/permissions_hr_contracts.py``).
PERM_VIEW = "hr.contracts_view"
PERM_MANAGE = "hr.contracts_manage"

#: Kabinet bölmələri.
HR_SECTION = "hr-contracts"
EMPLOYEE_SECTION = "my-contracts"

#: Qorunan media prefiksi (``apps.py`` ``register_media_policy`` ilə qeyd edir).
MEDIA_PREFIX = "hr_contracts/"
FILE_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png")
#: Brauzer bəzən ``application/octet-stream`` göndərir — məzmun imzası onsuz da yoxlanılır.
FILE_MIME_TYPES = ("application/pdf", "image/jpeg", "image/pjpeg", "image/png", "application/octet-stream")
FILE_MAX_MB = 10
FILE_ACCEPT = ".pdf,.jpg,.jpeg,.png"

NUMBER_MAX = 64
POSITION_MAX = 150
NOTE_MAX = 500
NOTES_MAX = 4000
TERMINATION_REASON_MIN = 10

#: Siyahının səhifə ölçüsü.
PAGE_SIZE = 25

#: Runtime açarları (``core/runtime_settings_hr_contracts.py``).
SETTING_REMINDER_DAYS = "hr.contract_reminder_days"
SETTING_EXPIRING_WINDOW = "hr.contract_expiring_window"
SETTING_EMAIL_ENABLED = "hr.contract_email_enabled"
DEFAULT_REMINDER_DAYS = "60,30,14,7,1"
DEFAULT_EXPIRING_WINDOW = 60

#: Əmək müqaviləsi bağlana bilməyən (tələbə ailəsi) rollar — işçi seçicisi və servis bunları rədd edir.
NON_EMPLOYEE_ROLE_NAMES = frozenset({"student", "lead_student", "alumni", "parent"})

#: ``Organization.settings`` açarı — «Müqavilələrim» menyusunu SORĞUSUZ açmaq üçün görünən müqaviləsi olan işçi
#: id-ləri (yeganə yazıçı ``services.contracts.sync_employee_snapshot``; ``apps.py`` onu managed açar kimi qeyd edir).
SNAPSHOT_KEY = "hr_contracts_employees"

#: Kabinet sorğu parametrlərinin prefiksi (filtr paneli toqquşmasın deyə).
PARAM_PREFIX = "hrc_"


class ContractType(models.TextChoices):
    FIXED_TERM = "fixed_term", pgettext_lazy(CTX, "Müddətli")
    INDEFINITE = "indefinite", pgettext_lazy(CTX, "Müddətsiz")
    SECONDARY = "secondary", pgettext_lazy(CTX, "Əvəzçilik")
    HOURLY = "hourly", pgettext_lazy(CTX, "Saathesabı")
    OTHER = "other", pgettext_lazy(CTX, "Digər")


class ContractStatus(models.TextChoices):
    """SAXLANAN həyat dövrü. «Yaxınlaşır» / «Müddəti bitib» tarixdən HESABLANIR (``ContractState``)."""

    DRAFT = "draft", pgettext_lazy(CTX, "Qaralama")
    ACTIVE = "active", pgettext_lazy(CTX, "Qüvvədədir")
    TERMINATED = "terminated", pgettext_lazy(CTX, "Xitam verilib")
    RENEWED = "renewed", pgettext_lazy(CTX, "Yenilənib")
    #: Rəy A2 (2026-10-19): qaralama «ləğv edilir» (silinmir — hadisə jurnalı append-only qalır); işçiyə HEÇ VAXT görünmür.
    DISCARDED = "discarded", pgettext_lazy(CTX, "Ləğv edilib")


class ContractState(models.TextChoices):
    """Göstərilən vəziyyət = saxlanan status + tarix (``services.queries.state_of``)."""

    DRAFT = "draft", pgettext_lazy(CTX, "Qaralama")
    ACTIVE = "active", pgettext_lazy(CTX, "Qüvvədədir")
    EXPIRING = "expiring", pgettext_lazy(CTX, "Bitmək üzrədir")
    EXPIRED = "expired", pgettext_lazy(CTX, "Müddəti bitib")
    TERMINATED = "terminated", pgettext_lazy(CTX, "Xitam verilib")
    RENEWED = "renewed", pgettext_lazy(CTX, "Yenilənib")
    DISCARDED = "discarded", pgettext_lazy(CTX, "Ləğv edilib")


class EventKind(models.TextChoices):
    CREATED = "created", pgettext_lazy(CTX, "Qeydə alındı")
    EDITED = "edited", pgettext_lazy(CTX, "Redaktə olundu")
    ACTIVATED = "activated", pgettext_lazy(CTX, "Qüvvəyə mindi")
    FILE_REPLACED = "file_replaced", pgettext_lazy(CTX, "Fayl yeniləndi")
    SENT = "sent", pgettext_lazy(CTX, "İşçiyə göndərildi")
    ACKNOWLEDGED = "acknowledged", pgettext_lazy(CTX, "İşçi təsdiqlədi")
    REMINDER_SENT = "reminder_sent", pgettext_lazy(CTX, "Bitmə xatırlatması göndərildi")
    EXPIRED_NOTICE = "expired_notice", pgettext_lazy(CTX, "Müddəti bitdi bildirişi göndərildi")
    TERMINATED = "terminated", pgettext_lazy(CTX, "Xitam verildi")
    RENEWED = "renewed", pgettext_lazy(CTX, "Yeni müqavilə ilə yeniləndi")
    #: Rəy A1: göndərilmiş, hələ təsdiqlənməmiş müqavilə dəyişdi — işçi YEKUN mətni təsdiqləsin deyə yenidən göndərilməli.
    RESEND_REQUIRED = "resend_required", pgettext_lazy(CTX, "Dəyişdi — yenidən göndərilməlidir")
    DISCARDED = "discarded", pgettext_lazy(CTX, "Qaralama ləğv edildi")


#: Bir müqavilə + hədd üçün BİR dəfə yazılan (DB unikal) hadisələr — xatırlatmanın idempotentliyi.
ONCE_PER_THRESHOLD_EVENTS = (EventKind.REMINDER_SENT, EventKind.EXPIRED_NOTICE)

#: Bitmə tarixi MƏCBURİ / QADAĞAN olan növlər.
END_REQUIRED_TYPES = (ContractType.FIXED_TERM,)
END_FORBIDDEN_TYPES = (ContractType.INDEFINITE,)

#: İşçiyə görünən statuslar — qaralama və ləğv edilmiş qaralama HEÇ VAXT (rəy A2: «göndərildi» qaralamanı əvvəlcə
#: qüvvəyə mindirir, ona görə işçi «qaralama» görmür).
EMPLOYEE_VISIBLE_STATUSES = (ContractStatus.ACTIVE, ContractStatus.TERMINATED, ContractStatus.RENEWED)
#: Redaktə olunan / «göndərildi» qeyd oluna bilən statuslar.
OPEN_STATUSES = (ContractStatus.DRAFT, ContractStatus.ACTIVE)
#: Yeniləmə və xitam YALNIZ qüvvədə olan müqavilədən (rəy A2).
CLOSABLE_STATUSES = (ContractStatus.ACTIVE,)
#: Təsdiqdən sonra dəyişdirilə bilən YEGANƏ sahə (daxili HR qeydi) — rəy A1.
POST_ACK_EDITABLE_FIELDS = ("notes",)
