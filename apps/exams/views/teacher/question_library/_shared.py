"""question_library paketi — _shared."""

import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
from django.template.loader import render_to_string
from django.utils.translation import pgettext

from apps.exams.constants import DEFAULT_EXAM_LANGUAGE, EXAM_LANGUAGE_CHOICES
from apps.exams.models import BankQuestion, BankQuestionOption, QuestionBlock
from apps.exams.services.import_media import attach_import_media_batch
from apps.exams.services.question_bank_attach import _question_fingerprint, bank_questions_queryset
from core.audit import log_action
from core.constants import AuditAction

logger = logging.getLogger(__name__)

_DIFFICULTY_CHOICES = (("easy", "Asan"), ("medium", "Orta"), ("hard", "Çətin"))


_ALLOWED_STATUSES = {"all", "active", "inactive"}


_ALLOWED_SORTS = {"newest", "oldest", "az", "za"}


_PICKER_PAGE_SIZE = 40


def _bank_template_test_txt():
    brand = getattr(settings, "SITE_BRAND_NAME", "") or "Qərbi Kaspi Universiteti"
    return f"""\
# {brand} — Test sual bankı şablonu
# Hər sualın 4 və ya 5 variantı olmalıdır (A–E). Düz cavabı 3 üsuldan biri ilə qeyd edin:
#   1) Sual sonunda "Cavab: B"   2) Düz variantın əvvəlinə * qoyun "*B)"   3) İşarə yoxdursa A.
# Çox cavablı: "Cavab: A,C". Hər sualdan sonra boş sətir buraxın.

1. Şəbəkədə məlumat hansı ölçü vahidi ilə ötürülür?
A) Bit
B) Bayt
C) Volt
D) Hertz
Cavab: A

2. Aşağıdakılardan hansı proqramlaşdırma dilidir?
A) Python
*B) JavaScript
C) Word
D) Excel

3. HTML nədir?
A) Proqramlaşdırma dili
B) İşarələmə dili
C) Verilənlər bazası
D) Əməliyyat sistemi
Cavab: B
"""


def _bank_template_written_txt():
    brand = getattr(settings, "SITE_BRAND_NAME", "") or "Qərbi Kaspi Universiteti"
    return f"""\
# {brand} — Yazılı sual bankı şablonu
# Hər sual yeni sətirdə nömrə ilə başlasın. Variant lazım deyil — yalnız sual mətni.

1. Verilənlər strukturu nədir? İzah edin.
2. Stack və Queue arasındakı fərqi yazın.
3. Binary axtarış alqoritmini addım-addım təsvir edin.
"""


def _normalize_format(value):
    candidate = (value or "test").strip().lower()
    return candidate if candidate in ("test", "written") else "test"


def _is_modal_request(request):
    return (
        request.GET.get("modal") == "1"
        or request.POST.get("modal") == "1"
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )


def _empty_analysis():
    return {
        "parsed": [],
        "category_counts": {"errors": 0, "warnings": 0, "duplicates": 0, "structure": 0, "balance": 0, "clean": 0},
        "warning_count": 0,
        "duplicate_count": 0,
        "error_count": 0,
        "test_level_warnings": [],
    }


def _save_bank_questions(
    *,
    bank,
    parsed,
    selected,
    language,
    q_format,
    points_payload,
    created_by,
    math_token="",
    media_owner_id=None,
):
    rows = []
    option_payloads = []
    source_indices = []
    for index, question in enumerate(parsed, start=1):
        if index not in selected:
            continue
        text = (question.get("text") or "").strip()
        if not text:
            continue
        raw_points = str(points_payload.get(str(index)) or "").strip()
        points = int(raw_points) if raw_points.isdigit() and int(raw_points) > 0 else 1

        if q_format == "written":
            rows.append(
                BankQuestion(
                    bank=bank,
                    text=text,
                    question_type="written",
                    answer_mode="single",
                    difficulty="medium",
                    language=language,
                    points=points,
                    fingerprint=_question_fingerprint(text),
                    created_by=created_by,
                )
            )
            option_payloads.append(None)
            source_indices.append(question.get("source_index"))
        else:
            options = question.get("options") or {}
            if any(label not in options for label in ("A", "B", "C", "D")):
                continue
            rows.append(
                BankQuestion(
                    bank=bank,
                    text=text,
                    question_type="test",
                    answer_mode=question.get("answer_mode", "single"),
                    difficulty="medium",
                    language=language,
                    points=points,
                    fingerprint=_question_fingerprint(text),
                    created_by=created_by,
                )
            )
            option_payloads.append((options, set(question.get("correct") or [])))
            source_indices.append(question.get("source_index"))

    if not rows:
        return 0
    with transaction.atomic():
        created = BankQuestion.objects.bulk_create(rows, batch_size=100)
        option_rows = []
        for bank_question, payload in zip(created, option_payloads):
            if not payload:
                continue
            options, correct = payload
            for label in "ABCDE":
                if label in options:
                    option_rows.append(
                        BankQuestionOption(
                            question=bank_question, label=label, text=options[label], is_correct=(label in correct)
                        )
                    )
        if option_rows:
            BankQuestionOption.objects.bulk_create(option_rows, batch_size=500)

        # Mənbə PDF-in canonical vizual segmentlərini sual+variantlara bağla.
        if math_token:
            attach_import_media_batch(
                math_token,
                list(zip(source_indices, created)),
                owner_id=media_owner_id or created_by.pk,
                organization_id=bank.organization_id,
            )
    return len(created)


def _render_bank_question_form_html(request, *, bank, form, editing=False, question=None):
    return render_to_string(
        "exams/teacher/partials/_question_form.html",
        {"bank": bank, "form": form, "editing": editing, "question": question, "is_modal": True},
        request=request,
    )


def _exam_compatible_question_type(exam):
    """İmtahanın tipinə uyğun bank sual tipi (uyğunsuz sual əlavə olunmasın)."""
    return "test" if exam.exam_type == "test" else "written"


def _first_or_default_block(exam):
    """Yazılı imtahan üçün birinci blok (yoxdursa yarat).

    Bankdan əlavə edilən suallar birinci bloka düşür ki, müəllim sonradan onları
    redaktorda istədiyi kimi bloklara böləbilsin.
    """
    block = exam.question_blocks.order_by("order", "id").first()
    if block is None:
        block = QuestionBlock.objects.create(
            exam=exam,
            name=pgettext("exams.view.bank.message", "Bölmə 1"),
            order=1,
        )
    return block


def _bank_language_stats(bank, *, question_type=None):
    """Bank üçün dil üzrə statistika: [(code, label, count)], ümumi, dil sayı."""
    labels = dict(EXAM_LANGUAGE_CHOICES)
    rows = (
        bank_questions_queryset(bank, question_type=question_type)
        .values("language")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    stats = []
    total = 0
    for row in rows:
        code = row["language"] or DEFAULT_EXAM_LANGUAGE
        count = row["count"]
        total += count
        stats.append({"code": code, "label": labels.get(code, code), "count": count})
    return stats, total, len(stats)


def _can_mutate_bank(user, bank) -> bool:
    """Bankın MƏZMUNUNU dəyişməyə kimin haqqı var.

    Audit 2026-09-13 EX-10: `crud.py`-dən bura köçürüldü ki, `questions.py`-dəki
    dörd yazı view-u (tək/toplu əlavə, redaktə, AI generasiya) da eyni qapıdan
    keçsin — onlar hələ də yalnız oxu görünürlüyü ilə yazırdı.

    2026-09-02 audit, P0-2: ``question_bank_detail`` POST budağı yalnız OXU
    görünürlüyünə (``accessible_banks``) söykənirdi.  Həmin köməkçi imtahan
    mərkəzi rollarına başqa müəllimin bankını GÖSTƏRİR — nəticədə
    ``bulk_action=delete`` ilə yad müəllimin sualları HARD-DELETE olunurdu
    (audit sətri də yazılmırdı).  Mutasiya artıq sahibliyə bağlıdır.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if bank.created_by_id == user.id:
        return True
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    organization = getattr(bank, "organization", None)
    return organization is not None and getattr(organization, "owner_id", None) == user.id


def _ensure_bank_mutation_allowed(request, bank, action: str):
    """Sahib deyilsə: rədd et + audit yaz (səssiz keçid YOXDUR)."""
    if _can_mutate_bank(request.user, bank):
        return
    log_action(
        AuditAction.DENY,
        user=request.user,
        organization=getattr(bank, "organization", None),
        obj=bank,
        reason=f"question bank mutation refused (not owner): bulk_action={action or '-'}",
        request=request,
        resource_type="exams.QuestionBank",
        resource_id=str(bank.pk),
        resource_repr=bank.name[:500],
    )
    raise PermissionDenied(pgettext("exams.view.bank.message", "Yalnız bankın sahibi bu əməliyyatı edə bilər."))
