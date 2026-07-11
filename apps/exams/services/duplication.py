"""
İmtahan dublikatı (clone) servisi.

Müəllim mövcud imtahanın bütün **parametrlərini** (növ, vaxt, sual paylanması,
giriş icazələri, nəzarət konfiqurasiyası) yenidən qurmadan təkrar istifadə edə
bilsin deyə, imtahanın TƏRİFİNİ qaralama kimi kopyalayır.

Diqqət — suallar köçürülmür (kopya 0 sualla başlayır): suallar bloklara, dil
variantlarına və banka bağlıdır, dərin köçürmə kövrək olardı. Müəllim kopyaya
bankdan sual əlavə edə bilər. Bu, dizaynın "dublikat → qaralama" davranışı ilə
eynidir.
"""

from __future__ import annotations

from django.db import transaction

from apps.exams.models import Exam

# Kopyalanmamalı sahələr — yenisi avtomatik/əllə təyin olunur.
_EXCLUDED_SCALAR_FIELDS = frozenset(
    {
        "id",
        "slug",
        "created_at",
        "access_code",
        "is_active",
        "is_archived",
        "archived_at",
        "settings",
        "author",
        "organization",
        "course",
    }
)


def _clone_supervision_config(source_exam: Exam, target_exam: Exam) -> None:
    """Varsa, nəzarət (supervision) konfiqurasiyasını da kopyala."""
    try:
        config = source_exam.supervision_config
    except Exception:
        return
    if config is None:
        return

    from apps.exams.models import ExamSupervisionConfig

    clone = ExamSupervisionConfig(exam=target_exam)
    for field in config._meta.fields:
        if field.name in {"id", "exam"}:
            continue
        setattr(clone, field.name, getattr(config, field.name))
    clone.pk = None
    clone.save()


@transaction.atomic
def duplicate_exam(*, exam: Exam, user, title_suffix: str = " (kopya)") -> Exam:
    """
    `exam`-ı `user` adına eyni təşkilatda qaralama kimi dublikat edir.

    Qaytarır: yeni `Exam` obyekti (saxlanılmış).
    """
    copy = Exam(author=user, organization=exam.organization, course=exam.course)

    for field in exam._meta.fields:
        if field.name in _EXCLUDED_SCALAR_FIELDS:
            continue
        setattr(copy, field.name, getattr(exam, field.name))

    # JSON sahəni dayaz kopyala ki, mənbə ilə paylaşılan referans qalmasın.
    copy.settings = dict(exam.settings or {})

    # Qaralama kimi başlasın, kod təmiz, arxiv deyil.
    copy.pk = None
    copy.slug = ""
    copy.title = f"{exam.title}{title_suffix}"
    copy.is_active = False
    copy.is_archived = False
    copy.archived_at = None
    # Dublikat heç vaxt "silinmiş" başlamamalıdır (qaralama kimi yaranır).
    copy.is_deleted = False
    copy.deleted_at = None
    copy.access_code = ""
    copy.save()

    # Giriş icazələri (M2M) — eyni qrup və fərdi tələbələr.
    copy.allowed_groups.set(exam.allowed_groups.all())
    copy.allowed_users.set(exam.allowed_users.all())
    copy.excluded_users.set(exam.excluded_users.all())

    _clone_supervision_config(exam, copy)

    return copy
