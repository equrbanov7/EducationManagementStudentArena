"""Kurs dashboard-u üçün task-modul kontribusiya registry-si.

M2 (2026-07-02, AGENTS §5 pattern 3): kurs dashboard-u əvvəllər
assignments/projects/labs modellərini birbaşa import edirdi —
courses↔{assignments,projects,labs} dövri asılılıqları. İndi hər task modulu
öz bölmə-kontekst provider-ini `AppConfig.ready()`-də bura qeyd edir
(bax apps/<modul>/course_dashboard.py); courses heç bir task modulunu tanımır.

Provider müqaviləsi:
    provider(*, course, user, membership, can_manage, is_student) -> dict
Qaytarılan dict dashboard kontekstinə merge olunur. Açarlar modullar arasında
kəsişməməlidir (hər modul yalnız öz template açarlarını doldurur).
"""

_PROVIDERS = []


def register(provider):
    """Dashboard bölmə provider-ini qeyd et (idempotent — təkrarı atır)."""
    if provider not in _PROVIDERS:
        _PROVIDERS.append(provider)


def build_context(*, course, user, membership, can_manage, is_student):
    """Bütün qeydli provider-lərin kontekstini birləşdirir."""
    data = {}
    for provider in _PROVIDERS:
        data.update(
            provider(
                course=course,
                user=user,
                membership=membership,
                can_manage=can_manage,
                is_student=is_student,
            )
        )
    return data


# ════════════════════════════════════════════════════════════════════════════
# Kart sayğacları (2026-10-18, «Kurslarım» redizaynı)
# ────────────────────────────────────────────────────────────────────────────
# Kurs siyahısı hər kartda «tapşırıq» sayını (tapşırıq + lab + layihə) göstərir.
# courses task modellərini tanımır — hər task modulu `ready()`-də öz
# queryset-ini qeyd edir:
#     dashboard_sources.register_task_counter(lambda: Assignment.objects.all())
# Siyahı bunu korrelyasiyalı alt-sorğu kimi annotate edir (kart sayından asılı
# olmayaraq SIFIR əlavə sorğu; hər modulun `course` FK-sı indekslidir).
# ════════════════════════════════════════════════════════════════════════════

_TASK_COUNTERS = []


def register_task_counter(factory):
    """``factory() -> QuerySet`` (``course`` FK-lı task modeli) — idempotent."""
    if factory not in _TASK_COUNTERS:
        _TASK_COUNTERS.append(factory)


def task_count_expression(outer_ref="pk"):
    """Qeydli task modullarının cəmi — ``Course`` queryset-ində annotate üçün ifadə."""
    from django.db.models import Count, IntegerField, OuterRef, Subquery, Value
    from django.db.models.functions import Coalesce

    total = Value(0, output_field=IntegerField())
    for factory in _TASK_COUNTERS:
        queryset = (
            factory()
            .filter(course_id=OuterRef(outer_ref))
            .order_by()
            .values("course_id")
            .annotate(n=Count("pk"))
            .values("n")
        )
        total = total + Coalesce(Subquery(queryset, output_field=IntegerField()), Value(0))
    return total
