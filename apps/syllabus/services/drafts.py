"""Qaralama həyat dövrü: yaratma, köçürmə, yeni versiya, bölmə autosave.

Bütün yazı əməliyyatları BURADADIR — view qatı modelə birbaşa toxunmur.
Audit üçün mövcud sistem (``core.audit.log_action`` → ``audit_auditlog``)
işlədilir; yeni jurnal cədvəli YARADILMIR.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .. import completion as completion_rules
from ..constants import (
    EDITABLE_STATUSES,
    LESSON_HOUR_KINDS,
    OPEN_STATUSES,
    PERM_EDIT,
    SECTION_ORDER,
    SELFWORK_OPTIONS,
    WEEK_ROWS,
    SectionKey,
    SyllabusStatus,
)
from ..models import ApprovalSource, ChangeKind, Syllabus, SyllabusSection, SyllabusVersion
from ..state_machine import TransitionDenied
from .scoping import is_author
from .units import resolve_syllabus_chair_unit

#: Bölmələrin BOŞ məzmun sxemi — autosave müqaviləsinin (public.py) əsasıdır.
BLANK_SECTION_DATA = {
    SectionKey.INFO.value: {"teacher": "", "office_hours": "", "prerequisites": ""},
    SectionKey.DESC.value: {"description": "", "goal": ""},
    SectionKey.OUT.value: {"outcomes": []},
    SectionKey.WEEK.value: {"rows": []},
    SectionKey.METHOD.value: {"methods": [], "note": ""},
    SectionKey.ASSESS.value: {"midterm": 0, "project": 0, "note": ""},
    SectionKey.SELF.value: {"option": "", "topics": [], "archived": []},
    SectionKey.LIT.value: {"primary": [], "additional": []},
    SectionKey.PREV.value: {},
    SectionKey.SEND.value: {},
}


def blank_section_data(section_id: str) -> dict:
    """Bölmənin boş sxemi (dərin kopya)."""
    import copy

    if section_id == SectionKey.WEEK.value:
        return {
            "rows": [{"topic": "", **{kind: 0 for kind in LESSON_HOUR_KINDS}, "outcome": ""} for _ in range(WEEK_ROWS)]
        }
    return copy.deepcopy(BLANK_SECTION_DATA.get(section_id, {}))


def _create_sections(version, *, source=None, actor_user=None):
    """10 bölməni yaradır; ``source`` verilibsə məzmunu ondan köçürür."""
    source_map = {}
    if source is not None:
        source_map = {row.section_id: row.data for row in source.sections.all()}
    rows = [
        SyllabusSection(
            organization_id=version.organization_id,
            version=version,
            section_id=section_id,
            data=source_map.get(section_id) or blank_section_data(section_id),
            updated_by=actor_user,
        )
        for section_id in SECTION_ORDER
    ]
    SyllabusSection.objects.bulk_create(rows)
    return rows


def section_data_map(version) -> dict:
    """``{section_id: data}`` — tamamlanma hesablaması üçün."""
    return {row.section_id: (row.data or {}) for row in version.sections.all()}


def recompute_completion(version, *, persist: bool = True):
    """Biznes qaydalarına görə tamamlanmanı yenidən hesablayır.

    Bölmə sətirlərinin ``is_complete`` bayrağı və versiyanın
    ``completion_percent`` sahəsi KEŞDİR — həqiqət mənbəyi
    :mod:`apps.syllabus.completion`-dır.
    """
    report = completion_rules.evaluate(section_data_map(version), version.plan_hours or {})
    if persist:
        for row in version.sections.all():
            expected = bool(report.sections.get(row.section_id, False))
            if row.is_complete != expected:
                SyllabusSection.objects.filter(pk=row.pk).update(is_complete=expected)
        if version.completion_percent != report.percent:
            SyllabusVersion.objects.filter(pk=version.pk).update(completion_percent=report.percent)
            version.completion_percent = report.percent
    return report


#: Dosye göstəricisinin seçim sırası — «üzərində işlənən / ən son versiya».
#: Model iki unikal məhdudiyyət daşıyır: bir dosyedə YALNIZ BİR açıq və YALNIZ
#: BİR təsdiqlənmiş versiya ola bilər, ona görə ilk iki addım TƏK nəticə verir.
def resolve_pointer_versions(syllabus):
    """``(current_version, approved_version)`` — YALNIZ statusdan çıxarılır.

    Sıra: açıq (qərar gözləyən) versiya → qüvvədə olan təsdiqlənmiş versiya →
    ən böyük nömrəli versiya.  Bu, ``offerings.offering_syllabus_state``-in
    banner seçimi ilə EYNİ sıradır; fərq yalnız odur ki, orada oxunur, burada
    dosyenin göstəricisinə yazılır.

    ⚠️ ARXİVLƏNMİŞ versiya heç vaxt ``current_version`` OLA BİLMƏZ (dosyedə
    arxivlənməmiş versiya varsa): ``current_version`` siyahının, redaktorun və
    ``coverage`` hesabatının oxuduğu göstəricidir, arxiv pilləsi isə «bu
    versiya bir vaxt qüvvədə idi» deməkdir.  Arxivlənmiş versiyaya ilişən
    göstərici dosyeni bütövlükdə «Arxivlənib» kimi göstərir.
    """
    versions = list(syllabus.versions.order_by("-major", "-minor"))
    open_version = next((row for row in versions if row.status in OPEN_STATUSES), None)
    approved = next((row for row in versions if row.status == SyllabusStatus.APPROVED.value), None)
    return (open_version or approved or (versions[0] if versions else None)), approved


def refresh_pointers(syllabus):
    """Dosyenin iki göstəricisini versiyaların STATUSU ilə uzlaşdırır.

    Status dəyişən HƏR yolun sonunda çağırılmalıdır.  Yazı ŞƏRTSİZDİR: çağıran
    ``syllabus`` obyekti çox vaxt keçiddən ƏVVƏL yüklənib, yəni onun
    ``*_version_id`` sahələri köhnədir — «dəyişibsə yaz» optimizasiyası məhz o
    köhnə dəyərə baxıb yazını buraxardı.  Bir ``UPDATE`` onsuz da əvvəlki
    davranışın qiymətidir və ``updated_at``-ə (auto_now) toxunmur.
    """
    current, approved = resolve_pointer_versions(syllabus)
    Syllabus.objects.filter(pk=syllabus.pk).update(current_version=current, approved_version=approved)
    syllabus.current_version = current
    syllabus.approved_version = approved
    return current


@transaction.atomic
def create_draft(
    *,
    organization,
    subject,
    period,
    actor,
    offering=None,
    program=None,
    chair_unit=None,
    author=None,
    plan_hours=None,
    request=None,
):
    """Yeni sillabus dosyesi + v1.0 qaralaması yaradır."""
    if not actor.has(PERM_EDIT):
        raise TransitionDenied("transition.permission_denied", params={"permission": PERM_EDIT})

    # R-2: çağıran tərəf ixtisas (``offering.group.parent``) ötürə bilər — təsdiq
    # əhatəsi isə KAFEDRA-ya bağlıdır.  Normallaşdırma burada, bir yerdədir ki,
    # hər yeni çağıran səth qaydanı təkrar yazmasın.
    chair_unit = resolve_syllabus_chair_unit(unit=chair_unit, author=author or actor.user, organization=organization)

    syllabus = Syllabus.objects.create(
        organization=organization,
        subject=subject,
        period=period,
        offering=offering,
        program=program,
        chair_unit=chair_unit,
        author=author or actor.user,
    )
    version = SyllabusVersion.objects.create(
        organization=organization,
        syllabus=syllabus,
        major=1,
        minor=0,
        status=SyllabusStatus.DRAFT,
        change_kind=ChangeKind.INITIAL,
        applies_to_period=period,
        plan_hours=dict(plan_hours or {}),
        created_by=actor.user,
    )
    _create_sections(version, actor_user=actor.user)
    Syllabus.objects.filter(pk=syllabus.pk).update(current_version=version)
    syllabus.current_version = version
    recompute_completion(version)
    log_action(
        AuditAction.CREATE,
        user=actor.user,
        organization=organization,
        obj=version,
        request=request,
        resource_type="syllabus.version",
        resource_id=str(version.pk),
        resource_repr=f"{subject} {version.label}",
        new_values={"status": version.status, "version": version.label},
    )
    return syllabus, version


@transaction.atomic
def create_next_version(*, syllabus, actor, kind: str, applies_to_period=None, plan_hours=None, request=None):
    """Təsdiqlənmiş/rədd edilmiş dosyedən YENİ qaralama versiyası açır.

    ``kind``: ``minor`` — cari semestr (v1.1 → v1.2); ``major`` — növbəti
    semestr (v1.2 → v2.0). Köhnə təsdiqlənmiş versiya TOXUNULMUR: o, yeni
    versiya TƏSDİQLƏNƏNƏ QƏDƏR qüvvədə qalır və yalnız onda arxivlənir.
    """
    if not actor.has(PERM_EDIT):
        raise TransitionDenied("transition.permission_denied", params={"permission": PERM_EDIT})
    if not is_author(actor, syllabus) and not actor.covers_unit(syllabus.chair_unit_id, PERM_EDIT):
        raise TransitionDenied("transition.out_of_scope", params={"transition": "new_version"})
    if kind not in {ChangeKind.MINOR.value, ChangeKind.MAJOR.value}:
        raise TransitionDenied("version.kind_unknown", params={"kind": kind})

    open_version = syllabus.versions.filter(status__in=sorted(OPEN_STATUSES)).first()
    if open_version is not None:
        raise TransitionDenied("version.open_version_exists", params={"version": open_version.label})

    base = syllabus.versions.order_by("-major", "-minor").first()
    if base is None:
        raise TransitionDenied("version.base_missing")

    if kind == ChangeKind.MINOR.value:
        major, minor = base.major, base.minor + 1
        period = applies_to_period or base.applies_to_period or syllabus.period
    else:
        major, minor = base.major + 1, 0
        period = applies_to_period or base.applies_to_period or syllabus.period

    version = SyllabusVersion.objects.create(
        organization=syllabus.organization,
        syllabus=syllabus,
        major=major,
        minor=minor,
        status=SyllabusStatus.DRAFT,
        change_kind=kind,
        applies_to_period=period,
        source_version=base,
        plan_hours=dict(plan_hours or base.plan_hours or {}),
        created_by=actor.user,
    )
    _create_sections(version, source=base, actor_user=actor.user)
    Syllabus.objects.filter(pk=syllabus.pk).update(current_version=version)
    syllabus.current_version = version
    recompute_completion(version)
    log_action(
        AuditAction.CREATE,
        user=actor.user,
        organization=syllabus.organization,
        obj=version,
        request=request,
        resource_type="syllabus.version",
        resource_id=str(version.pk),
        resource_repr=f"{syllabus.subject_id} {version.label}",
        new_values={"status": version.status, "version": version.label, "kind": kind},
        changes={"source_version": base.label},
    )
    return version


@transaction.atomic
def copy_from_previous(*, source_syllabus, target_period, actor, offering=None, request=None):
    """«Keçən ildən köçür» — nəticə HƏR ZAMAN QARALAMADIR, avtomatik təsdiqlənmir.

    ƏHATƏ QAPISI ``create_next_version`` ilə EYNİDİR (2026-09-02 audit, P1-2):
    əvvəl bu funksiya MƏNBƏ sillabusu heç yoxlamırdı, ona görə istənilən müəllim
    ``{"action": "copy", "syllabus": <yad id>}`` göndərib başqasının məzmununu
    öz adına klonlaya bilirdi (auditor bunu canlı klonda icra etdi).
    """
    if not actor.has(PERM_EDIT):
        raise TransitionDenied("transition.permission_denied", params={"permission": PERM_EDIT})
    if not is_author(actor, source_syllabus) and not actor.covers_unit(source_syllabus.chair_unit_id, PERM_EDIT):
        raise TransitionDenied("transition.out_of_scope", params={"transition": "copy"})

    base = source_syllabus.approved_version or source_syllabus.versions.order_by("-major", "-minor").first()
    if base is None:
        raise TransitionDenied("version.base_missing")

    syllabus, version = create_draft(
        organization=source_syllabus.organization,
        subject=source_syllabus.subject,
        period=target_period,
        actor=actor,
        offering=offering,
        program=source_syllabus.program,
        chair_unit=source_syllabus.chair_unit,
        author=actor.user,
        plan_hours=base.plan_hours,
        request=request,
    )
    SyllabusVersion.objects.filter(pk=version.pk).update(change_kind=ChangeKind.COPIED, source_version=base)
    version.change_kind = ChangeKind.COPIED
    version.source_version = base
    SyllabusSection.objects.filter(version=version).delete()
    _create_sections(version, source=base, actor_user=actor.user)
    recompute_completion(version)
    return syllabus, version


class SectionConflict(TransitionDenied):
    """Bölmə başqa sessiyada dəyişilib (redaktorun ``conflict`` vəziyyəti)."""

    def __init__(self, current_revision: int):
        super().__init__("section.conflict", "", {"revision": current_revision})
        self.current_revision = current_revision


@transaction.atomic
def save_section(*, version, section_id: str, data: dict, actor, expected_revision=None, request=None):
    """Bölmə autosave (**PATCH**) — optimistik kilid ilə.

    ``expected_revision`` verilibsə və serverdəki ``revision`` ondan fərqlidirsə
    ``SectionConflict`` atılır; redaktor bunu ``conflict`` banneri kimi göstərir.

    ⚠️ Yazı BÜTÖV ƏVƏZLƏMƏ DEYİL — göndərilən açarlar birləşdirilir
    =============================================================
    Səth adı «PATCH»dir, davranış isə PUT idi: ``row.data = data or {}``
    göndərilməyən HƏR açarı silirdi.  Bu, sübutlu data itkisi idi:

    * ``create_next_version``/``copy_from_previous`` bölmə məzmununu OLDUĞU
      KİMİ irs alır, yəni köçürülmüş sillabusun ``assess.note`` (canlı: 5,893
      sillabus), ``assess.exam_questions`` (685 uniqid), ``info.welcome``,
      ``info.research_interests``, ``info.certificates``, ``info.language`` və
      ``info.lesson_hours`` sahələri yeni qaralamaya keçir;
    * bugünkü redaktorun həmin sahələr üçün **input-u yoxdur**
      (``legacy_syllabus_*_unsurfaced`` kodları məhz bunu sayır), ona görə
      autosave gövdəsi onları DAŞIMIR;
    * nəticədə müəllimin İLK avtosave-i onları silirdi və növbəti versiya
      təsdiqlənəndə itki TƏLƏBƏNİN ekranına çatırdı.

    Ona görə birləşmə (merge) EDİLİR: yalnız göndərilən açarlar yenilənir,
    göndərilməyən açar toxunulmaz qalır.  **Silmək niyyəti yox olmur** — açar
    AÇIQ boş dəyərlə (``""``, ``[]``, ``{}``, ``0``) göndərilir, o da yazılır.
    Bu istiqamət qəsdən seçildi: sahə sxeminə gələcəkdə əlavə olunan hər açar
    avtomatik qorunur, halbuki «redaktor hər sahəni toplasın» yolu hər yeni
    sahədə YENİDƏN unudula bilər.

    ⚠️ Redaktor tərəfində tamamlayıcı qayda: panel öz DOM-unda olmayan açarı
    UYDURMAMALIDIR.  ``collectAssess`` ``note`` üçün input olmadığı halda
    ``note: ""`` göndərirdi — açıq boş dəyər, yəni birləşmə onu haqlı olaraq
    SİLƏRDİ.  Bax ``syllabus_editor_fields.js``.
    """
    if version.status not in EDITABLE_STATUSES:
        raise TransitionDenied("version.locked", params={"status": version.status})
    if not actor.has(PERM_EDIT):
        raise TransitionDenied("transition.permission_denied", params={"permission": PERM_EDIT})
    if not is_author(actor, version.syllabus):
        raise TransitionDenied("transition.author_only", params={"transition": "save_section"})
    if section_id not in SECTION_ORDER:
        raise TransitionDenied("section.unknown", params={"section": section_id})
    if section_id == SectionKey.SELF.value:
        option = (data or {}).get("option") or ""
        if option and option not in SELFWORK_OPTIONS:
            raise TransitionDenied("self.option_not_allowed", params={"option": option})

    row = SyllabusSection.objects.select_for_update().get(version=version, section_id=section_id)
    if expected_revision is not None and int(expected_revision) != row.revision:
        raise SectionConflict(row.revision)

    old_data = row.data
    # Merge, PUT deyil: göndərilməyən açar saxlanılır (bax docstring).
    row.data = {**(old_data or {}), **(data or {})}
    row.revision += 1
    row.updated_by = actor.user
    row.save(update_fields=["data", "revision", "updated_by", "updated_at"])

    report = recompute_completion(version)
    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=version.organization,
        obj=version,
        request=request,
        resource_type="syllabus.section",
        resource_id=f"{version.pk}:{section_id}",
        resource_repr=f"{version.label} · {section_id}",
        old_values={"revision": row.revision - 1},
        new_values={"revision": row.revision, "completion_percent": report.percent},
        changes={"section": section_id, "changed": old_data != row.data},
    )
    return row, report


#: Köçürmə borusunun yaza bildiyi YEGANƏ statuslar (bax migrasiya spesifikasiyası:
#: təkrarlar versiya kimi gəlir — sonuncusu APPROVED, əvvəlkilər ARCHIVED).
IMPORTABLE_STATUSES = (SyllabusStatus.APPROVED.value, SyllabusStatus.ARCHIVED.value)


@transaction.atomic
def import_migrated_version(
    *,
    organization,
    subject,
    approved_at,
    period=None,
    offering=None,
    program=None,
    chair_unit=None,
    author=None,
    plan_hours=None,
    section_data=None,
    major: int = 1,
    minor: int = 0,
    status: str = SyllabusStatus.APPROVED,
    note: str = "",
):
    """KÖÇÜRMƏ girişi — köhnə sistemin sillabusunu qərarı VERİLMİŞ kimi gətirir.

    ⚠️ Sahibin qərarı: köçürülən qeydlər «TƏSDİQLƏNMİŞ» statusla gəlir. SAXTA
    insan təsdiqi UYDURULMUR: ``approved_by`` NULL qalır, ``approval_source`` =
    ``migration`` damğalanır və UI təsdiqləyəni «sistem/köçürmə» kimi göstərir.
    DB ``syllabus_version_human_approval_has_approver`` check-i məhz bu istisnaya
    icazə verir (mənbə ``human`` olsa təsdiqləyən MƏCBURİDİR).

    ``period`` BOŞ ola bilər — köhnə bazada sillabusun semestri yoxdur, uydurmaq
    əvəzinə «baza sillabus» yaradılır (``docs/migration/SILLABUS_KOCURME_SPEC.md``).
    Təkrarlanan qeydlər ``major``/``minor`` ilə versiya kimi gəlir: adətən
    sonuncusu ``approved``, əvvəlkilər ``archived`` — AMMA HƏMİŞƏ YOX (mənbədə
    ``active`` bayrağı sonra sönə bilir).  Dosyenin göstəriciləri ona görə hər
    yazıdan sonra ``refresh_pointers`` ilə STATUSDAN yenidən çıxarılır.

    Bu funksiya İCAZƏ YOXLAMIR — yalnız idxal borusundan (management command)
    çağırılmalıdır; HTTP səthinə bağlanmamalıdır.
    """
    if status not in IMPORTABLE_STATUSES:
        raise TransitionDenied("import.status_not_allowed", params={"status": status})

    stamp = approved_at or timezone.now()
    syllabus, _created = Syllabus.objects.get_or_create(
        organization=organization,
        subject=subject,
        period=period,
        offering=offering,
        author=author,
        defaults={"program": program, "chair_unit": chair_unit},
    )
    version = SyllabusVersion.objects.create(
        organization=organization,
        syllabus=syllabus,
        major=major,
        minor=minor,
        status=status,
        change_kind=ChangeKind.IMPORTED,
        applies_to_period=period,
        plan_hours=dict(plan_hours or {}),
        approved_at=stamp,
        approved_by=None,
        approval_source=ApprovalSource.MIGRATION,
        locked_at=stamp,
        decided_at=stamp,
        decision_reason=note,
        archived_at=stamp if status == SyllabusStatus.ARCHIVED else None,
    )
    rows = _create_sections(version)
    if section_data:
        for row in rows:
            if row.section_id in section_data:
                row.data = section_data[row.section_id]
        SyllabusSection.objects.bulk_update([row for row in rows if row.section_id in section_data], ["data"])
    # ⚠️ ``current_version = version`` YAZILMIR.  Köçürmə bir dosyeyə birdən çox
    # pillə yazır və APPROVED pillə HƏMİŞƏ sonuncu deyil: canlı ölçmədə 44
    # dosyedə (48 quyruq versiyası) təsdiqlənmiş pillədən SONRA arxiv pilləsi
    # gəlir.  Sonuncu yazını kor-koranə göstərici etmək o dosyeləri
    # «Arxivlənib» kimi göstərərdi.  Göstərici ona görə STATUSDAN çıxarılır.
    refresh_pointers(syllabus)
    recompute_completion(version)
    return syllabus, version


__all__ = [
    "BLANK_SECTION_DATA",
    "SectionConflict",
    "blank_section_data",
    "copy_from_previous",
    "create_draft",
    "create_next_version",
    "import_migrated_version",
    "recompute_completion",
    "refresh_pointers",
    "resolve_pointer_versions",
    "save_section",
    "section_data_map",
]
