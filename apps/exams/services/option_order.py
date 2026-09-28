"""Test variantlarının yaradılma sırasını müəllif sırasından ayırmaq.

Audit 2026-09-28 EX28-01: variantlar müəllif sırası ilə (A→E) ``bulk_create``
olunurdu, ona görə ``id`` sırası müəllif hərfini, END_QUESTION konvensiyasında
isə birbaşa düzgün cavabı (birinci variant) açırdı. İndi hər yaradılma yolu
variantları təsadüfi sıra ilə yaradır və etiketləri (A..E) YENİ yaradılma
sırası ilə yenidən hərfləyir. Beləliklə müəllim UI-si (``options.all()`` —
id sırası, redaktə formu da id sırası ilə A..E verir) ardıcıl qalır: A, B, C…
göstərilir, düzgün cavab isə təsadüfi hərfdə olur.

PDF/DOCX media bağlanması (``attach_import_media_batch``) variantları MƏNBƏ
etiketi ilə tapır — o yollarda sətirlər mənbə etiketi ilə yaradılır, media
bağlanır, sonra ``relabel_options_by_creation_order`` çağırılır.
"""

import secrets

from apps.exams.constants import LABELS

_RNG = secrets.SystemRandom()


def display_label(index):
    return LABELS[index] if index < len(LABELS) else None


def shuffled_option_specs(options, correct):
    """``[(mənbə_etiketi, mətn, düzgündür)]`` — kriptoqrafik təsadüfi sırada."""
    correct = set(correct or [])
    specs = [(label, options[label], label in correct) for label in LABELS if label in options]
    _RNG.shuffle(specs)
    return specs


def shuffled_option_rows(option_model, question, options, correct, *, relabel=True):
    """Bir sual üçün təsadüfi sıralı, ``bulk_create``-ə hazır variant sətirləri.

    ``relabel=False`` — mənbə etiketi saxlanır (media bağlandıqdan sonra
    ``relabel_options_by_creation_order`` ilə yenidən hərflənməlidir).
    """
    return [
        option_model(
            question=question,
            label=display_label(index) if relabel else source_label,
            text=text,
            is_correct=is_correct,
        )
        for index, (source_label, text, is_correct) in enumerate(shuffled_option_specs(options, correct))
    ]


def relabel_options_by_creation_order(option_model, question_ids):
    """Verilən sualların variant etiketlərini id (yaradılma) sırası ilə A..E et."""
    question_ids = [question_id for question_id in question_ids if question_id]
    if not question_ids:
        return 0
    rows = option_model.objects.filter(question_id__in=question_ids).order_by("question_id", "id")
    positions = {}
    changed = []
    for row in rows:
        index = positions.get(row.question_id, 0)
        positions[row.question_id] = index + 1
        label = display_label(index)
        if row.label != label:
            row.label = label
            changed.append(row)
    if changed:
        option_model.objects.bulk_update(changed, ["label"], batch_size=500)
    return len(changed)


def shuffled(items):
    """Siyahının təsadüfi sıralı surəti (bank→imtahan köçürməsi üçün)."""
    items = list(items)
    _RNG.shuffle(items)
    return items


__all__ = [
    "display_label",
    "relabel_options_by_creation_order",
    "shuffled",
    "shuffled_option_rows",
    "shuffled_option_specs",
]
