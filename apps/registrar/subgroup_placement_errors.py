"""«Alt qrupa yerləşdirmə» xəta kodları — hər imtina aydın KOD + Azərbaycanca mətnlə (sahib 2026-10-18).

Kodlar sabit müqavilədir: «Alt qrupa tələbə əlavə et» aləti, 25% təkrar imtahan axını (dekan alt qrup
müraciətini təsdiqləyəndə ``place_in_subgroup`` çağırır) və testlər onlara söykənir. Mətn dəyişə bilər, kod YOX.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

FORBIDDEN = "forbidden"
OUT_OF_SCOPE = "out_of_scope"
WRONG_ORGANIZATION = "wrong_organization"
STUDENT_INACTIVE = "student_inactive"
OFFERING_INACTIVE = "offering_inactive"
ROSTER_CLOSED = "roster_closed"
OWN_GROUP = "own_group"
ALREADY_ENROLLED = "already_enrolled"
ACTIVE_ELSEWHERE = "active_elsewhere"
ALREADY_PASSED = "already_passed"
CREDIT_LIMIT = "credit_limit"
CAPACITY_FULL = "capacity_full"
SCHEDULE_CLASH = "schedule_clash"
DOCUMENT_REQUIRED = "document_required"
DOCUMENT_INVALID = "document_invalid"
REASON_REQUIRED = "reason_required"
ENROLL_FAILED = "enroll_failed"
NOT_FOUND = "not_found"
ALREADY_UNDONE = "already_undone"
UNDO_BLOCKED = "undo_blocked"
SUBJECT_EXEMPT = "subject_exempt"
SUPERSEDED = "superseded"

#: Kod → standart mətn (çağıran konkret mətn verə bilər — məs. rəqəmlərlə).
MESSAGES = {
    FORBIDDEN: pgettext_lazy(
        "registrar.subgroup_placement", "Alt qrupa yerləşdirmə üçün «retake.manage» səlahiyyəti lazımdır."
    ),
    OUT_OF_SCOPE: pgettext_lazy("registrar.subgroup_placement", "Bu tələbə sizin struktur əhatənizdə deyil."),
    WRONG_ORGANIZATION: pgettext_lazy("registrar.subgroup_placement", "Tələbə və jurnal eyni təşkilata aid olmalıdır."),
    STUDENT_INACTIVE: pgettext_lazy(
        "registrar.subgroup_placement",
        "Tələbənin aktiv akademik qeydi (qrupu) yoxdur — akademik məzuniyyətdə, xaric və ya məzun ola bilər.",
    ),
    OFFERING_INACTIVE: pgettext_lazy("registrar.subgroup_placement", "Bu jurnal bu semestrdə aktiv deyil."),
    ROSTER_CLOSED: pgettext_lazy(
        "registrar.subgroup_placement", "Jurnalın siyahısı bağlıdır — tələbə əlavə edilə bilməz."
    ),
    OWN_GROUP: pgettext_lazy(
        "registrar.subgroup_placement", "Bu, tələbənin öz qrupunun jurnalıdır — alt qrup yerləşdirməsi tələb olunmur."
    ),
    ALREADY_ENROLLED: pgettext_lazy("registrar.subgroup_placement", "Tələbə artıq bu jurnaldadır."),
    ACTIVE_ELSEWHERE: pgettext_lazy(
        "registrar.subgroup_placement",
        "Tələbə bu fənn üzrə bu semestrdə başqa jurnalda aktivdir. «Öz jurnalından azad et» seçilməlidir — "
        "əvvəlki qeydiyyat tarixçəyə keçir, bal və davamiyyət saxlanılır.",
    ),
    ALREADY_PASSED: pgettext_lazy(
        "registrar.subgroup_placement", "Tələbə bu fənni artıq keçib — təkrar yazılış yalnız kəsilmiş fənn üçündür."
    ),
    CREDIT_LIMIT: pgettext_lazy("registrar.subgroup_placement", "Semestr kredit həddi keçilir."),
    CAPACITY_FULL: pgettext_lazy("registrar.subgroup_placement", "Jurnalda boş yer yoxdur (tutum həddi dolub)."),
    SCHEDULE_CLASH: pgettext_lazy(
        "registrar.subgroup_placement", "Alt qrupun dərs saatı tələbənin öz cədvəli ilə üst-üstə düşür."
    ),
    DOCUMENT_REQUIRED: pgettext_lazy(
        "registrar.subgroup_placement",
        "Sənəd məcburidir: təqdimat / sərəncam faylı (PDF, JPG, PNG) yükləyin və ya sərəncamın nömrəsi və tarixini yazın.",
    ),
    DOCUMENT_INVALID: pgettext_lazy(
        "registrar.subgroup_placement", "Sənəd faylı qəbul edilmədi — yalnız PDF, JPG və PNG (10 MB-a qədər)."
    ),
    REASON_REQUIRED: pgettext_lazy("registrar.subgroup_placement", "Səbəb yazılmalıdır (ən azı 10 simvol)."),
    ENROLL_FAILED: pgettext_lazy("registrar.subgroup_placement", "Tələbə jurnala yazıla bilmədi."),
    NOT_FOUND: pgettext_lazy("registrar.subgroup_placement", "Yerləşdirmə tapılmadı."),
    ALREADY_UNDONE: pgettext_lazy("registrar.subgroup_placement", "Bu yerləşdirmə artıq geri götürülüb."),
    UNDO_BLOCKED: pgettext_lazy("registrar.subgroup_placement", "Yerləşdirmə geri götürülə bilmir."),
    SUBJECT_EXEMPT: pgettext_lazy(
        "registrar.subgroup_placement",
        "Tələbə bu semestrdə bu fəndən azad edilib — əvvəlcə azadolma geri qaytarılmalıdır.",
    ),
    SUPERSEDED: pgettext_lazy(
        "registrar.subgroup_placement",
        "Bu qeydiyyat sonradan yenidən yerləşdirilib — yalnız ən son yerləşdirmə geri götürülə bilər.",
    ),
}

#: HTTP status xəritəsi (alət səthi üçün): icazə 403, əhatə 404, qalanı məzmun xətası.
HTTP_STATUS = {FORBIDDEN: 403, OUT_OF_SCOPE: 404, NOT_FOUND: 404, WRONG_ORGANIZATION: 404}


class SubgroupPlacementError(Exception):
    """Yerləşdirmə imtina etdi — ``code`` sabit, ``message`` istifadəçiyə göstərilir."""

    def __init__(self, code: str, message=None, details=None):
        super().__init__(code, message, details)
        self.code = code
        self.message = str(message if message is not None else MESSAGES.get(code, code))
        self.details = details or {}

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    @property
    def status(self) -> int:
        return HTTP_STATUS.get(
            self.code, 400 if self.code in (DOCUMENT_REQUIRED, DOCUMENT_INVALID, REASON_REQUIRED) else 409
        )


CODES = frozenset(MESSAGES)

__all__ = ["CODES", "HTTP_STATUS", "MESSAGES", "SubgroupPlacementError"]
