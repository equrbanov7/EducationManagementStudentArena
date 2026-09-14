"""«Dəyişən nəticələr» — apellyasiya / sənədli düzəlişlə DƏYİŞƏN imtahan balları (W2 `w2paper`, 2026-09-14).

Sahibin tələbi (2026-09-14): «apellyasiyadan və ya nədənsə sonra DƏYİŞƏN
nəticələrin izlənməsi lazımdır». Mənbə artıq var — append-only
``ExamScoreEntry`` jurnalı: hər dəyişiklik ``kind != initial`` sətridir
(``correction`` = sənədli düzəliş, ``appeal`` = apellyasiya nəticəsi), köhnə →
yeni bal, səbəb, qeyd, kim, sənəd / vərəq skanı ilə. Bu modul həmin sətirləri
tenant üzrə OXUYUR (yazmır):

* :func:`scope_q` — aktorun struktur əhatəsi (``final_score.entry``): org-wide
  → bütün təşkilat; unit-scoped (dekan/kafedra) → yalnız öz alt-ağacının
  qrupları — siyahı ilə EYNİ qayda, fail-closed;
* :func:`changes_queryset` — filtrlər: qrup, fənn, müəllim, növ, tarix aralığı,
  tələbə axtarışı (ad / istifadəçi adı / FİN / tələbə №);
* :func:`change_row` — cədvəl və CSV üçün ortaq sətir lüğəti;
* :func:`paginate` — səhifə başına 50;
* :func:`csv_rows` — ixrac sətirləri (yazıcı ``core.export_safety.safe_csv_writer``
  ilə çağıran tərəfdə — formula neytrallaşdırma orada).

Sorğu büdcəsi sətir sayından asılı deyil: ``select_related`` zənciri + bir
``count``. Heç bir ``apps.exams`` / ``apps.accounts`` importu yoxdur.
"""

from __future__ import annotations

import datetime

from django.core.paginator import Paginator
from django.db.models import Avg, Count, Exists, OuterRef, Q
from django.utils.translation import pgettext

from .exam_score_roster import file_url
from .models import ExamScoreEntry, ExamScoreEntryKind
from .models.exam_score_entry import ExamScoreSheetKind

_CTX = "registrar.exam_score_entry"

#: Səhifə ölçüsü («Dəyişən nəticələr» cədvəli).
PAGE_SIZE = 50
#: CSV ixracının yuxarı həddi (bir çağırışda) — səhifəsiz, amma sonsuz deyil.
EXPORT_LIMIT = 5000


def scope_q(user, organization, *, permission):
    """Aktorun ``final_score.entry`` əhatəsi üçün ``ExamScoreEntry`` Q-su; əhatə yoxdursa ``None``.

    Org-wide daşıyıcı (imtahan mərkəzi, RİM, superadmin) bütün təşkilatı görür;
    unit-scoped daşıyıcı yalnız alt-ağacındakı qrupların açılışlarını. Superadmin
    çağıran tərəfdə həll olunur (``organization`` seçicisi).
    """
    from django.apps import apps as django_apps

    from . import journal_scope

    scope = journal_scope.permission_scope_for(user, organization, permission)
    if not scope.has_structure_access:
        return None
    base = Q(organization=organization)
    if scope.is_org_wide:
        return base
    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    units = org_unit_model.objects.filter(organization=organization).filter(scope.unit_subtree_q()).values("pk")
    return base & Q(enrollment__offering__group__in=units)


def exam_kind_q(kind, *, prefix="sheet__"):
    """İmtahan növü filtri — ``written`` köhnə (vərəqsiz) sətirləri də əhatə edir (migrasiya defoltu)."""
    if kind == ExamScoreSheetKind.PRACTICAL:
        return Q(**{f"{prefix}exam_kind": ExamScoreSheetKind.PRACTICAL})
    if kind == ExamScoreSheetKind.WRITTEN:
        written = Q(**{f"{prefix}exam_kind": ExamScoreSheetKind.WRITTEN})
        if prefix:  # sətir → vərəq əlaqəsi: vərəqsiz köhnə sətir də «yazılı»
            written |= Q(**{f"{prefix.rstrip('_')}__isnull": True})
        return written
    return Q()


def exam_kind_options(*, with_all=True) -> list:
    """Növ çipləri: hamısı · yazılı · praktiki."""
    options = [{"value": "", "label": pgettext(_CTX, "hamısı")}] if with_all else []
    return options + [{"value": value, "label": str(label)} for value, label in ExamScoreSheetKind.choices]


def parse_date(raw):
    """``YYYY-MM-DD`` (``<input type=date>``) → ``date``; boş/yanlış → ``None`` (filtr sadəcə düşür)."""
    text = (raw or "").strip() if isinstance(raw, str) else raw
    if not text:
        return None
    if isinstance(text, datetime.date):
        return text
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def changes_queryset(
    *,
    scope,
    period=None,
    group_id="",
    subject_id="",
    instructor_id="",
    kind="",
    date_from=None,
    date_to=None,
    search="",
    exam_kind="",
):
    """Tenantın bütün DƏYİŞİKLİK sətirləri (``kind != initial``), filtrlərlə, ən yenidən köhnəyə.

    ``scope`` — :func:`scope_q` nəticəsi (``None`` → boş nəticə, fail-closed).
    ``kind`` yalnız ``correction`` / ``appeal`` qəbul edir; başqa dəyər → hər ikisi.
    ``exam_kind`` — ``written`` / ``practical`` (vərəqdən; addendum 2026-09-14).
    """
    if scope is None:
        return ExamScoreEntry.objects.none()
    queryset = ExamScoreEntry.objects.filter(scope).exclude(kind=ExamScoreEntryKind.INITIAL)
    if exam_kind:
        queryset = queryset.filter(exam_kind_q(exam_kind))
    if period is not None:
        queryset = queryset.filter(enrollment__offering__period=period)
    if group_id:
        queryset = queryset.filter(enrollment__offering__group_id=group_id)
    if subject_id:
        queryset = queryset.filter(enrollment__offering__subject_id=subject_id)
    if instructor_id:
        queryset = queryset.filter(enrollment__offering__instructor_id=instructor_id)
    if kind in ExamScoreEntryKind.change_kinds():
        queryset = queryset.filter(kind=kind)
    if date_from is not None:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to is not None:
        queryset = queryset.filter(created_at__date__lte=date_to)
    needle = (search or "").strip()
    if needle:
        queryset = queryset.filter(
            Q(enrollment__student__first_name__icontains=needle)
            | Q(enrollment__student__last_name__icontains=needle)
            | Q(enrollment__student__username__icontains=needle)
            | Q(enrollment__student__profile__fin__icontains=needle)
            | Q(enrollment__student__profile__institutional_identifier__icontains=needle)
        )
    return queryset.select_related(
        "enrollment",
        "enrollment__student",
        "enrollment__student__profile",
        "enrollment__offering",
        "enrollment__offering__subject",
        "enrollment__offering__group",
        "enrollment__offering__instructor",
        "sheet",
    ).order_by("-created_at", "-id")


def _score_text(value) -> str:
    """Bal TAM ədəddir (sahibin qaydası) — «20», yoxdursa «—» (lokal «20,00» formatı yox)."""
    if value is None:
        return "—"
    return str(int(value))


def _person_label(user) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.username


def change_row(entry) -> dict:
    """Cədvəl + CSV üçün ortaq sətir (tarix, tələbə, fənn/qrup, köhnə → yeni, növ, səbəb, kim, sənəd)."""
    enrollment = entry.enrollment
    student = enrollment.student
    offering = enrollment.offering
    sheet = entry.sheet if entry.sheet_id else None
    profile = getattr(student, "profile", None)
    group = getattr(offering, "group", None)
    exam_kind = sheet.exam_kind if sheet is not None else ExamScoreSheetKind.WRITTEN
    return {
        "id": str(entry.id),
        "enrollment_id": str(enrollment.id),
        "exam_kind": exam_kind,
        "exam_kind_label": str(ExamScoreSheetKind(exam_kind).label),
        "is_practical": exam_kind == ExamScoreSheetKind.PRACTICAL,
        "date": entry.created_at.strftime("%d.%m.%Y %H:%M"),
        "date_iso": entry.created_at.isoformat(),
        "student": student.get_full_name() or student.username,
        "username": student.username,
        "fin": getattr(profile, "fin", "") or "",
        "subject_code": offering.subject.code or "",
        "subject_name": offering.subject.name,
        "group": group.name if group is not None else pgettext(_CTX, "(qrupsuz açılış)"),
        "instructor": _person_label(getattr(offering, "instructor", None)),
        "old": _score_text(entry.old_score),
        "new": _score_text(entry.new_score),
        "question_scores": list(entry.question_scores) if entry.question_scores else [],
        "kind": entry.kind,
        "kind_label": str(entry.get_kind_display()),
        "is_appeal": entry.kind == ExamScoreEntryKind.APPEAL,
        "reason": str(entry.get_reason_display()) if entry.reason else "",
        "note": entry.note,
        "by": entry.entered_by_name,
        "evidence_url": file_url(entry.evidence),
        "sheet_id": str(sheet.id) if sheet is not None else "",
        "sheet_protocol": sheet.protocol_number if sheet is not None else "",
        "sheet_exam_date": sheet.exam_date.strftime("%d.%m.%Y") if sheet is not None and sheet.exam_date else "",
        "sheet_evidence_url": file_url(sheet.evidence) if sheet is not None else "",
    }


def paginate(queryset, page_number, *, per_page=PAGE_SIZE):
    """Səhifə obyekti (``page_obj``) — yanlış nömrə → 1-ci səhifə."""
    paginator = Paginator(queryset, per_page)
    try:
        number = int(page_number or 1)
    except (TypeError, ValueError):
        number = 1
    return paginator.get_page(number)


def csv_header() -> list:
    return [
        pgettext(_CTX, "Tarix"),
        pgettext(_CTX, "Tələbə"),
        pgettext("registrar.exam_score_import", "Tələbə №"),
        pgettext("registrar.exam_score_import", "FİN"),
        pgettext(_CTX, "Fənn"),
        pgettext(_CTX, "Qrup"),
        pgettext(_CTX, "Müəllim"),
        pgettext(_CTX, "İmtahan növü"),
        pgettext(_CTX, "Köhnə bal"),
        pgettext(_CTX, "Yeni bal"),
        pgettext(_CTX, "Sual balları"),
        pgettext(_CTX, "Növ"),
        pgettext(_CTX, "Səbəb"),
        pgettext(_CTX, "Qeyd"),
        pgettext(_CTX, "Kim"),
        pgettext(_CTX, "Protokol №"),
        pgettext(_CTX, "Sənəd"),
    ]


def csv_rows(queryset, *, limit=EXPORT_LIMIT):
    """CSV sətirləri (başlıqsız) — ``change_row`` ilə eyni məlumat, mətn kimi."""
    for entry in queryset[:limit]:
        row = change_row(entry)
        yield [
            row["date"],
            row["student"],
            row["username"],
            row["fin"],
            f"{row['subject_code']} — {row['subject_name']}" if row["subject_code"] else row["subject_name"],
            row["group"],
            row["instructor"],
            row["exam_kind_label"],
            str(row["old"]),
            str(row["new"]),
            " ".join(str(v) for v in row["question_scores"]),
            row["kind_label"],
            row["reason"],
            row["note"],
            row["by"],
            row["sheet_protocol"],
            row["evidence_url"] or row["sheet_evidence_url"],
        ]


def paper_kind_stats(*, organization, year_start=None, months=None, exam_kind="") -> list:
    """İmtahan mərkəzi statistikası üçün KAĞIZ imtahan KPI-ları — növ üzrə (addendum 2026-09-14).

    Hər növ üçün: vərəq sayı, daxiletmə sayı, dəyişiklik sayı (``kind != initial``),
    tələbə sayı və ORTA imtahan balı (hər qeydiyyatın SONUNCU daxiletməsi üzrə —
    düzəlişlər iki dəfə sayılmır). Dövr filtri sətrin ``created_at``-ına görədir
    (tədris ili sentyabrdan; ``months`` semestr ayları). Sabit sayda sorğu (2):
    sətir aqreqatı + vərəq aqreqatı — sətir sayından asılı deyil.
    """
    import datetime

    from django.utils import timezone

    entries = ExamScoreEntry.objects.filter(organization=organization)
    sheets = organization.exam_score_sheets.all()
    if year_start is not None:
        lo = timezone.make_aware(datetime.datetime(int(year_start), 9, 1))
        hi = timezone.make_aware(datetime.datetime(int(year_start) + 1, 9, 1))
        entries = entries.filter(created_at__gte=lo, created_at__lt=hi)
        sheets = sheets.filter(created_at__gte=lo, created_at__lt=hi)
    if months:
        entries = entries.filter(created_at__month__in=list(months))
        sheets = sheets.filter(created_at__month__in=list(months))
    if exam_kind:
        entries = entries.filter(exam_kind_q(exam_kind))
        sheets = sheets.filter(exam_kind_q(exam_kind, prefix=""))
    later = ExamScoreEntry.objects.filter(
        enrollment_id=OuterRef("enrollment_id"), created_at__gt=OuterRef("created_at")
    )
    entry_rows = {
        row["sheet__exam_kind"] or ExamScoreSheetKind.WRITTEN: row
        for row in entries.annotate(is_latest=~Exists(later))
        .values("sheet__exam_kind")
        .annotate(
            entries=Count("id"),
            students=Count("enrollment_id", distinct=True),
            changes=Count("id", filter=~Q(kind=ExamScoreEntryKind.INITIAL)),
            avg=Avg("new_score", filter=Q(is_latest=True)),
        )
    }
    sheet_rows = {row["exam_kind"]: row["n"] for row in sheets.values("exam_kind").annotate(n=Count("id"))}
    result = []
    for value, label in ExamScoreSheetKind.choices:
        if exam_kind and value != exam_kind:
            continue
        stats = entry_rows.get(value, {})
        avg = stats.get("avg")
        result.append(
            {
                "kind": value,
                "label": str(label),
                "sheets": sheet_rows.get(value, 0),
                "entries": stats.get("entries", 0),
                "changes": stats.get("changes", 0),
                "students": stats.get("students", 0),
                "avg": round(float(avg), 1) if avg is not None else None,
            }
        )
    return result


def kind_options() -> list:
    """Növ filtri seçimləri: hamısı · sənədli düzəliş · apellyasiya nəticəsi."""
    return [{"value": "", "label": pgettext(_CTX, "Bütün növlər")}] + [
        {"value": value, "label": str(label)}
        for value, label in ExamScoreEntryKind.choices
        if value != ExamScoreEntryKind.INITIAL
    ]


__all__ = [
    "EXPORT_LIMIT",
    "PAGE_SIZE",
    "change_row",
    "changes_queryset",
    "csv_header",
    "csv_rows",
    "exam_kind_options",
    "exam_kind_q",
    "kind_options",
    "paper_kind_stats",
    "paginate",
    "parse_date",
    "scope_q",
]
