"""Domen xətaları — maşın-oxunaqlı ``code`` + tərcümə olunan mətn.

Servis qatı HƏR imtinanı :class:`FolderError` ilə qaldırır. ``code`` sabitdir
(UI/testlər ona baxır), ``message`` isə :data:`MESSAGES` kataloqundan
``pgettext`` ilə gəlir — mətn bir yerdə saxlanılır, i18n skripti də bu
kataloqu əks etdirir. Kod ``permission.`` ilə başlayırsa HTTP səthi 403,
qalanlarda 400 qaytarır (``is_permission``).
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

_CTX = "subject_folder.error"


class FolderError(Exception):
    """Fənn qovluğu əməliyyatı rədd edildi."""

    # Arqumentlərin hamısı ``super()``-ə ötürülür ki, istisna pickle/copy
    # edilə bilsin (flake8-bugbear B042); oxunaqlı mətn ``__str__``-dan gəlir.
    def __init__(self, code: str, message: str = "", params: dict | None = None):
        super().__init__(code, message, params)
        self.code = code
        self.params = params or {}

    def __str__(self) -> str:
        return self.args[1] or self.code

    @property
    def is_permission(self) -> bool:
        return self.code.startswith("permission.")

    def as_dict(self) -> dict:
        return {"code": self.code, "message": str(self), "params": dict(self.params)}

    @classmethod
    def of(cls, code: str, **params) -> "FolderError":
        """Kataloqdan mətnli xəta qurur; mətn yoxdursa kod özü göstərilir."""
        template = MESSAGES.get(code)
        text = str(template) if template is not None else code
        if params:
            try:
                text = text % {key: display_number(value) for key, value in params.items()}
            except (KeyError, TypeError, ValueError):
                pass
        return cls(code, text, params)


def display_number(value):
    """Decimal ``4.0`` → ``4``; qalan dəyərlər olduğu kimi."""
    from decimal import Decimal

    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value == value.to_integral_value() else format(value, "f")
    return value


#: Xəta kodu → istifadəçi mətni (placeholder-lər ``%(ad)s``).
MESSAGES = {
    "permission.denied": pgettext_lazy(_CTX, "Bu əməliyyat üçün səlahiyyətiniz yoxdur."),
    "permission.not_owner": pgettext_lazy(_CTX, "Qovluğu yalnız onun sahibi olan müəllim redaktə edə bilər."),
    "permission.not_teaching": pgettext_lazy(_CTX, "Bu fənn açılışını (qrupu) siz tədris etmirsiniz."),
    "permission.not_reviewer": pgettext_lazy(_CTX, "Bu qrupun göndərişlərini yalnız fənnin müəllimi yoxlaya bilər."),
    "folder.not_teaching_subject": pgettext_lazy(
        _CTX, "Bu fənni tədris etmədiyiniz üçün onun qovluğunu yarada bilməzsiniz."
    ),
    "folder.organization_mismatch": pgettext_lazy(_CTX, "Seçilən obyektlər eyni təşkilata aid olmalıdır."),
    "folder.subject_mismatch": pgettext_lazy(_CTX, "Açılışın fənni qovluğun fənninə uyğun deyil."),
    "folder.period_mismatch": pgettext_lazy(_CTX, "Açılışın semestri qovluğun semestrinə uyğun deyil."),
    "folder.archived": pgettext_lazy(_CTX, "Arxivlənmiş qovluq dəyişdirilə bilməz."),
    "folder.not_active": pgettext_lazy(_CTX, "Qovluq hələ aktiv deyil."),
    "folder.status_invalid": pgettext_lazy(_CTX, "Qovluğun statusu yanlışdır."),
    "title.required": pgettext_lazy(_CTX, "Başlıq boş ola bilməz."),
    "text.too_long": pgettext_lazy(_CTX, "Mətn çox uzundur (ən çox %(max)s simvol)."),
    "topic.not_in_folder": pgettext_lazy(_CTX, "Mövzu bu qovluğa aid deyil."),
    "topic.syllabus_topic": pgettext_lazy(
        _CTX, "Sillabus mövzusu silinmir — onu gizlədə və ya adını dəyişə bilərsiniz."
    ),
    "topic.not_empty": pgettext_lazy(_CTX, "Mövzuya bağlı material və ya tapşırıq var — əvvəlcə onları köçürün."),
    "material.kind_unknown": pgettext_lazy(_CTX, "Material növü tanınmır."),
    "material.not_in_folder": pgettext_lazy(_CTX, "Material bu qovluğa aid deyil."),
    "material.file_required": pgettext_lazy(_CTX, "Fayl seçilməyib."),
    "material.url_invalid": pgettext_lazy(_CTX, "Keçid http:// və ya https:// ilə başlayan düzgün ünvan olmalıdır."),
    "material.code_required": pgettext_lazy(_CTX, "Kod mətni boşdur."),
    "material.note_required": pgettext_lazy(_CTX, "Qeyd mətni boşdur."),
    "upload.invalid": pgettext_lazy(_CTX, "Fayl qəbul edilmədi."),
    "task.selfwork_slots_fixed": pgettext_lazy(
        _CTX,
        "Sərbəst iş tapşırıqları sillabusun strukturundan yaranır — əlavə sərbəst iş yaratmaq olmaz.",
    ),
    "task.kind_unknown": pgettext_lazy(_CTX, "Tapşırıq növü tanınmır."),
    "task.not_in_folder": pgettext_lazy(_CTX, "Tapşırıq bu qovluğa aid deyil."),
    "task.archived": pgettext_lazy(_CTX, "Bu tapşırıq arxivlənib."),
    "task.not_published": pgettext_lazy(_CTX, "Tapşırıq hələ dərc edilməyib."),
    "task.has_submissions": pgettext_lazy(_CTX, "Tapşırığa göndəriş var — silmək olmaz, yalnız arxivləmək olar."),
    "task.extensions_invalid": pgettext_lazy(_CTX, "Dəstəklənməyən fayl tipi: %(ext)s"),
    "task.limits_invalid": pgettext_lazy(_CTX, "Fayl sayı 1–%(max_files)s, ölçü 1–%(max_mb)s MB aralığında olmalıdır."),
    "task.attachments_limit": pgettext_lazy(_CTX, "Tapşırığa ən çox %(max)s qoşma əlavə etmək olar."),
    "task.nothing_to_submit": pgettext_lazy(_CTX, "Tapşırıq nə mətn, nə də fayl qəbul edir."),
    "assignment.inactive": pgettext_lazy(_CTX, "Bu qrup üçün qovluq aktiv deyil."),
    "assignment.selfwork_elsewhere": pgettext_lazy(
        _CTX, "Bu qrupun sərbəst işləri başqa fənn qovluğundan qiymətləndirilir."
    ),
    "assignment.selfwork_option_mismatch": pgettext_lazy(
        _CTX,
        "Bu qrupun sillabusundakı sərbəst iş strukturu (%(offering_option)s) qovluğunkundan "
        "(%(folder_option)s) fərqlidir — sərbəst iş bu qrupda qovluqdan qəbul edilməyəcək.",
    ),
    "assignment.not_in_folder": pgettext_lazy(_CTX, "Təyinat bu qovluğa aid deyil."),
    "deadline.invalid_range": pgettext_lazy(_CTX, "Açılma vaxtı son tarixdən əvvəl olmalıdır."),
    "deadline.not_open": pgettext_lazy(_CTX, "Tapşırıq hələ açılmayıb."),
    "deadline.passed": pgettext_lazy(_CTX, "Son tarix keçib — bu tapşırıq gecikmə ilə qəbul edilmir."),
    "audience.not_enrolled": pgettext_lazy(_CTX, "Bu fənn açılışında aktiv qeydiyyatınız yoxdur."),
    "submission.empty": pgettext_lazy(_CTX, "Cavab mətni yazın və ya ən azı bir fayl əlavə edin."),
    "submission.text_not_allowed": pgettext_lazy(_CTX, "Bu tapşırıq mətn cavabı qəbul etmir — fayl yükləyin."),
    "submission.files_not_allowed": pgettext_lazy(_CTX, "Bu tapşırıq fayl qəbul etmir — cavabı mətn kimi yazın."),
    "submission.too_many_files": pgettext_lazy(_CTX, "Ən çox %(max)s fayl əlavə etmək olar."),
    "submission.pending": pgettext_lazy(_CTX, "Göndərişiniz yoxlanılır — müəllimin cavabını gözləyin."),
    "submission.closed": pgettext_lazy(_CTX, "Bu tapşırıq üzrə iş artıq yekunlaşıb."),
    "submission.not_draft": pgettext_lazy(_CTX, "Yalnız qaralamadakı fayl silinə bilər."),
    "submission.concurrent": pgettext_lazy(_CTX, "Eyni anda ikinci göndəriş alındı — səhifəni yeniləyib yoxlayın."),
    "submission.not_reviewable": pgettext_lazy(_CTX, "Bu göndəriş baxış növbəsində deyil."),
    "review.feedback_required": pgettext_lazy(_CTX, "Rəy yazın (ən azı %(min)s simvol)."),
    "review.points_invalid": pgettext_lazy(_CTX, "Bal 0-dan böyük olmalı və %(max)s-dən çox olmamalıdır."),
    "review.points_total_exceeded": pgettext_lazy(
        _CTX,
        "Sərbəst iş balı cəmi %(max_total)s-i keçə bilməz: tələbənin artıq %(already)s balı var, "
        "ən çox %(remaining)s əlavə etmək olar.",
    ),
    "review.already_awarded": pgettext_lazy(_CTX, "Bu sərbəst iş üçün bal artıq verilib — ikinci dəfə bal verilmir."),
    "review.homework_has_no_points": pgettext_lazy(
        _CTX, "Ev tapşırığına bal verilmir — yalnız «Yoxlanıldı» qeyd edin."
    ),
    "review.selfwork_needs_points": pgettext_lazy(_CTX, "Sərbəst iş bal ilə qəbul edilir."),
    "review.reason_invalid": pgettext_lazy(_CTX, "Rədd səbəbi seçilməyib."),
    "review.not_rejected": pgettext_lazy(_CTX, "Yalnız rədd edilmiş göndəriş yenidən açıla bilər."),
}

__all__ = ["FolderError", "MESSAGES", "display_number"]
