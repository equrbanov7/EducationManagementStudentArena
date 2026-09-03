"""AÇIQ qaralamalarda bölünməmiş qiymətləndirmə bölgüsünü normallaşdırır.

Niyə
----
2026-09-03-dən ``assess`` bölməsi TAMAMLANMA qaydasına daxil oldu (README §8/4:
«davamiyyət 10, sərbəst iş 10, yekun 50 kilidli; müəllim qalan 30 balı bölür;
cəm həmişə 100»).  Köhnə sistemdən köçürülmüş sillabusların bölgüsü isə
``{"midterm": 0, "project": 0}``-dır, yəni cəmi 70 verir.

Yeni versiya yaradılanda bölgü onsuz da normallaşır
(``services.drafts._inherited_data``), amma ARTIQ AÇIQ olan qaralamalar (draft /
revision) köhnə dəyərlə qalardı və müəllim heç nə etmədən «tamamlanmamış»
görünərdi.  Bu migrasiya məhz o sətirləri düzəldir.

Nə TOXUNMUR
-----------
* ``approved`` / ``archived`` / ``submitted`` / ``review`` / ``rejected``
  versiyalar — təsdiqlənmiş nüsxə IMMUTABLE-dır (§8/1) və tarixi qeyd
  dəyişdirilmir;
* ``assess`` bölməsinin DİGƏR açarları (``note``, ``exam_questions``, …) —
  yalnız ``midterm``/``project`` cütü yazılır;
* onsuz da etibarlı olan bölgülər.

``completion_percent`` BURADA yenidən hesablanmır: o, keşdir və növbəti
autosave/təsdiqə göndərmə anında öz-özünə yenilənir (``recompute_completion``
təsdiqə göndərmədən ƏVVƏL işləyir, ona görə qapı hər halda düzgün qərar verir).
"""

from django.db import migrations

#: Redaktəyə açıq statuslar — yalnız bunlar düzəldilir.
OPEN_EDITABLE = ("draft", "revision")

#: Siyasət default-u (``apps.syllabus.policy.DEFAULT_ASSESSMENT``).
DEFAULT_LOCKED = {"attendance": 10, "selfwork": 10, "final": 50}
TOTAL = 100


def _flex_for(settings) -> int:
    weights = dict(DEFAULT_LOCKED)
    section = (settings or {}).get("syllabus") if isinstance(settings, dict) else None
    override = (section or {}).get("assessment") if isinstance(section, dict) else None
    if isinstance(override, dict):
        for key in DEFAULT_LOCKED:
            try:
                weights[key] = max(0, int(override[key]))
            except (KeyError, TypeError, ValueError):
                continue
    return max(0, TOTAL - sum(weights.values()))


def _as_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def normalize(apps, schema_editor):
    SyllabusSection = apps.get_model("syllabus", "SyllabusSection")
    Organization = apps.get_model("organizations", "Organization")

    flex_by_org = {row.pk: _flex_for(row.settings) for row in Organization.objects.all().only("pk", "settings")}

    updates = []
    queryset = SyllabusSection.objects.filter(section_id="assess", version__status__in=OPEN_EDITABLE).only(
        "pk", "data", "organization_id"
    )
    for row in queryset.iterator(chunk_size=500):
        flex = flex_by_org.get(row.organization_id, TOTAL - sum(DEFAULT_LOCKED.values()))
        data = row.data if isinstance(row.data, dict) else {}
        midterm, project = _as_int(data.get("midterm")), _as_int(data.get("project"))
        if midterm >= 0 and project >= 0 and midterm + project == flex:
            continue
        row.data = {**data, "midterm": flex // 2, "project": flex - flex // 2}
        updates.append(row)
        if len(updates) >= 500:
            SyllabusSection.objects.bulk_update(updates, ["data"])
            updates = []
    if updates:
        SyllabusSection.objects.bulk_update(updates, ["data"])


def noop(apps, schema_editor):
    """Geri qaytarma YOXDUR — köhnə 0/0 dəyəri bərpa edilmir (məlumat itkisi deyil)."""


class Migration(migrations.Migration):

    dependencies = [
        ("syllabus", "0002_rls_syllabus"),
        ("organizations", "0001_initial"),
    ]

    operations = [migrations.RunPython(normalize, noop)]
