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
