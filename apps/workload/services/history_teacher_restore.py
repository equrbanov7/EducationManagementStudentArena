"""«Bu müəllimə bərpa et» — tarixçə jurnalını HƏMİN müəllimin cari jurnalına qaytarmaq (sahib 2026-11-03).

Sahib (RİM, çox vaxt «istifadəçi kimi bax» rejimində): «Əvvəlki jurnal qeydlərim» siyahısındakı hər sətirdə
«bərpa et» olsun, «bəzən gəlir, bəzən yox».

NİYƏ GƏLİB-GETMİRDİ. Köhnə düymə (:func:`.history_restore.attach_actions`) yalnız bir halı tanıyırdı: jurnalın
sahibi (``CourseOffering.instructor``) elə bu müəllimdir, sadəcə cari yük sətri/təyinatı yoxdur. Qalan hər hal
SƏSSİZ ``return`` idi — ən çox rast gələni: jurnal mühazirəçinin adınadır, seminarçı müəllimin seminar yükü
«Yük bölgüsü»ndə başqasına (və ya vakansiyaya) keçib (məs. 2026/2027 Payız «Azərbaycan tarixi», 536 ML / 536 İ).
Belə sətirdə nə düymə, nə səbəb görünürdü.

İNDİ. Siyahının hər tarixçə sətri üçün bir QƏRAR hesablanır (:class:`Decision`): ``ready`` (bir kliklə bərpa,
nə dəyişəcəyi əvvəlcədən yazılır), ``form`` (saat bölgüsü lazımdır — mövcud bərpa forması) və ya ``blocked``
(düymə söndürülüb, konkret səbəb + lazım olsa «Yük bölgüsü» keçidi). Səlahiyyəti olmayan (adi müəllim) heç nə
görmür.

YAZI YOLU YENİ DEYİL — mövcud servislər ardıcıl işləyir, hamısı TƏK tranzaksiyada:

1. yük: :func:`.row_edit.assign_amended` (təsdiqlənmiş sənəddə rəsmi düzəliş + audit; jurnal sahibi/payı
   ``offering_sync`` ilə dərhal izləyir) və ya sıfır-saatlıq sətirdə :func:`.history_restore.restore`;
2. sahiblik (yalnız lazımdırsa): bu müəllimdən edilmiş təhvil varsa ``handover_actions.revert``, yoxsa
   ``handover_actions.reassign`` (səbəb, audit, bildiriş — «Fənn təhvili» ilə eyni);
3. SON YOXLAMA: jurnal müəllimin «Cari dərs yüküm» siyahısına (``teacher_journal_list.own_visible_queryset``)
   həqiqətən keçməyibsə hər şey geri qaytarılır və səbəb deyilir — «bərpa edildi» deyib heç nə dəyişməmək olmur.

Patok (çoxqruplu) sətir bir kliklə bölünmür (PR #180 qərarı) — keçid «Yük bölgüsü»nə aparır.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.registrar.public import handover, handover_actions, teacher_journal_list
from core.audit import log_action
from core.constants import AuditAction

from ..constants import ASSIGNABLE_STATUSES, PERM_DISTRIBUTE, Activity, AmendmentReason, RowKind, TaskStatus
from ..models import TeacherAssignment, TeachingTaskRow
from .history_restore import KINDS, actor_for_restore, available_chairs, restore, shared_rows
from .history_restore_actions import automatic_plan
from .history_restore_zero_plan import zero_placeholder_plan
from .history_teacher_restore_since import written_since
from .row_edit import assign_amended, distributable_chair_ids, distribution_edit_url
from .scoping import WorkloadDenied, resolve_actor

CTX = "workload.history_teacher_restore"
READY, FORM, BLOCKED = "ready", "form", "blocked"
MIN_REASON, MAX_REASON = 10, 2000
#: Bölgü bu statuslarda dəyişir (``distributed`` — rəsmi düzəliş açılır, ``amended``-ə keçir).
OPEN_TASK_STATUSES = frozenset(ASSIGNABLE_STATUSES | {TaskStatus.DISTRIBUTED})
DENIED_PREFIX = "workload.history_teacher_restore_"
#: Heç kim sonradan yazmayıbsa (təhlükəsiz hal) səbəb boş qala bilər — audit/təhvil üçün bu mətn yazılır.
DEFAULT_REASON = "Tarixçə jurnalı müəllimə bərpa edildi: sonradan heç kim qeyd yazmayıb."


def _name(user) -> str:
    if user is None:
        return pgettext(CTX, "Vakant")
    return (user.get_full_name() or "").strip() or user.username


def message(code: str, **params) -> str:
    """Kod → istifadəçi mətni (sorğunun dilində; JSON və şablon eyni mətni göstərir)."""
    texts = {
        "inactive": pgettext(CTX, "Dərs açılışı aktiv deyil."),
        "not_regular": pgettext(CTX, "Yalnız fiziki qrupu olan adi jurnal bərpa olunur."),
        "period": pgettext(CTX, "Yalnız aktiv cari semestrin açıq jurnalı bərpa olunur."),
        "journal_closed": pgettext(CTX, "Jurnal bağlanıb — əvvəlcə jurnalı açın."),
        "no_records": pgettext(CTX, "Bu müəllimin bu jurnalda öz dərs qeydi yoxdur."),
        "patok": pgettext(CTX, "Yük çoxqruplu (patok) sətirdədir: %(groups)s — müəllim «Yük bölgüsü»ndə təyin edilir."),
        "task": pgettext(CTX, "Kafedranın yük sənədi bölgü mərhələsində deyil."),
        "scope_workload": pgettext(CTX, "Bu jurnalın kafedrası üzrə yük bölgüsü səlahiyyətiniz yoxdur."),
        "scope_handover": pgettext(CTX, "Jurnalın sahibini dəyişmək üçün «Fənn təhvili» səlahiyyətiniz yoxdur."),
        "kind_missing": pgettext(CTX, "Yük sətrində «%(kind)s» üçün saat yoxdur."),
        "split": pgettext(CTX, "«%(kind)s» bir neçə müəllim arasında bölünüb — «Yük bölgüsü»ndə dəyişin."),
        "owner_conflict": pgettext(
            CTX, "Jurnal %(owner)s adınadır və onun bu sətirdə yükü var — «Fənn təhvili» ilə həll edin."
        ),
        "mismatch": pgettext(CTX, "Yük bu müəllimdədir, amma jurnala bağlanmayıb — «Yük bölgüsü»ndə yoxlayın."),
        "view_as_mode": pgettext(CTX, "Bu baxış rejimində bərpa edilmir (yalnız tam baxış)."),
        "handover_blocked": pgettext(CTX, "Jurnalın sahibi dəyişdirilə bilmir: %(detail)s"),
        "reason": pgettext(CTX, "Səbəb ən azı 10 simvol olmalıdır."),
        "not_found": pgettext(CTX, "Bu jurnal müəllimin tarixçə siyahısında deyil."),
        "not_current": pgettext(
            CTX,
            "Dəyişikliklərdən sonra da jurnal cari yükə düşmədi — heç nə dəyişdirilmədi. «Yük bölgüsü»ndə yoxlayın.",
        ),
        "changed": pgettext(CTX, "Jurnalın vəziyyəti dəyişib — səhifəni yeniləyib yenidən baxın."),
    }
    text = texts.get(code, pgettext(CTX, "Bərpa mümkün olmadı."))
    return text % params if params else text


def step_text(step) -> str:
    op = step["op"]
    if op == "assign":
        return pgettext(CTX, "%(kind)s yükü: %(source)s → %(target)s (%(hours)s saat)") % {
            "kind": Activity(step["kind"]).label,
            "source": step["source_name"],
            "target": step["target_name"],
            "hours": step["hours"],
        }
    if op == "load_restore":
        return pgettext(CTX, "Yük sətrinin planı bu müəllimə təyin olunur (%(hours)s saat)") % {
            "hours": sum(step["hours"].values())
        }
    if op == "revert":
        return pgettext(CTX, "Fənn təhvili geri qaytarılır: jurnal yenidən %(target)s adına") % {
            "target": step["target_name"]
        }
    return pgettext(CTX, "Jurnalın sahibi: %(source)s → %(target)s") % {
        "source": step["source_name"],
        "target": step["target_name"],
    }


def warning_text(warning) -> list:
    """Modal xəbərdarlığı: kim, nə qədər, nə vaxtdan yazıb (qeydlər yerində qalır)."""
    lines = []
    for user, lessons, marks in warning["people"]:
        params = {"name": _name(user), "lessons": lessons, "marks": marks}
        if warning["since"] is not None:
            params["since"] = timezone.localtime(warning["since"]).strftime("%d.%m.%Y %H:%M")
            text = pgettext(
                CTX, "%(name)s %(since)s tarixindən bəri bu jurnalda %(lessons)s dərs və %(marks)s qeyd yazıb."
            )
        else:
            text = pgettext(CTX, "%(name)s bu jurnalda %(lessons)s dərs və %(marks)s qeyd yazıb.")
        lines.append(text % params)
    return lines


class Denied(WorkloadDenied):
    def __init__(self, code: str, status: int = 409, **params):
        super().__init__(DENIED_PREFIX + code, message(code, **params))
        self.status = status


@dataclass
class Decision:
    state: str
    code: str = ""
    params: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)
    link: str = ""
    #: :func:`.history_teacher_restore_since.written_since` — indiki sahib sonradan yazıbsa (səbəb məcburi).
    warning: dict | None = None

    def as_row(self, course, teacher) -> dict:
        data = {"state": self.state, "link": self.link}
        if self.state == READY:
            data["url"] = reverse("workload:history_teacher_restore", args=[course.pk])
            data["steps"] = [step_text(step) for step in self.steps]
            data["warnings"] = warning_text(self.warning) if self.warning else []
            data["teacher_id"], data["teacher_name"] = teacher.pk, _name(teacher)
        elif self.state == BLOCKED:
            data["reason"] = message(self.code, **self.params)
        return data


def _blocked(code, link="", **params):
    return Decision(BLOCKED, code=code, params=params, link=link)


def _row_url(row) -> str:
    return distribution_edit_url(chair_id=row.task.chair_id, academic_year=row.task.academic_year, row_id=row.pk)


class _Context:
    """Bir səhifənin bütün sətirləri üçün toplu oxu (sətir başına sorğu yoxdur)."""

    def __init__(self, actor, teacher, courses, *, view_as_blocked=False):
        organization = actor.organization
        self.actor, self.teacher, self.organization = actor, teacher, organization
        self.view_as_blocked = view_as_blocked
        ids = [course.pk for course in courses]
        self.closed = handover.closed_offering_ids(ids)
        self.distribute = distributable_chair_ids(actor) if actor.has(PERM_DISTRIBUTE) else set()
        self.can_reassign = handover.can_reassign(actor.user, organization)
        self.eligible = self.can_reassign and handover.is_eligible_target(organization, teacher.pk)
        self.handovers = {}
        if self.can_reassign:
            records = (
                apps.get_model("registrar.TeachingHandover")
                .objects.filter(
                    organization=organization, offering_id__in=ids, from_instructor=teacher, reverted_at__isnull=True
                )
                .order_by("created_at")
            )
            owners = {course.pk: course.instructor_id for course in courses}
            for record in records:
                if record.to_instructor_id == owners.get(record.offering_id):
                    self.handovers[record.offering_id] = record
        # :func:`.history_restore.restore` tələb edir: müəllimin ADINA keçirilmiş dərs (yalnız bal yazmaq deyil).
        self.taught = set(
            apps.get_model("registrar.Lesson")
            .objects.filter(organization=organization, offering_id__in=ids, instructor=teacher)
            .values_list("offering_id", flat=True)
        )
        grouped = [course for course in courses if course.group_id is not None]
        rows = list(
            TeachingTaskRow.objects.filter(
                organization=organization,
                task__organization=organization,
                row_kind=RowKind.TEACHING,
                period_id__in={c.period_id for c in grouped},
                subject_id__in={c.subject_id for c in grouped},
                groups__in={c.group_id for c in grouped},
            )
            .exclude(task__status=TaskStatus.CANCELLED)
            .distinct()
            .select_related("task")
            .prefetch_related("groups", "assignments__teacher")
        )
        self.rows = {
            course.pk: [
                row
                for row in rows
                if row.subject_id == course.subject_id
                and row.period_id == course.period_id
                and any(group.pk == course.group_id for group in row.groups.all())
            ]
            for course in grouped
        }

    def can_change_owner(self, course) -> bool:
        return self.eligible and handover.offering_in_scope(self.actor.user, self.organization, course)

    def owner_step(self, course):
        record = self.handovers.get(course.pk)
        names = {
            "source_id": course.instructor_id,
            "source_name": _name(course.instructor),
            "target_name": _name(self.teacher),
        }
        if record is not None:
            return {"op": "revert", "handover_id": record.pk, **names}
        return {"op": "reassign", **names}


def _gates(ctx, course):
    period = course.period
    if not course.is_active:
        return _blocked("inactive")
    if course.is_intensive or course.group_id is None:
        return _blocked("not_regular")
    if not (period.is_active and period.is_current and period.locked_at is None):
        return _blocked("period")
    if course.pk in ctx.closed:
        return _blocked("journal_closed")
    if ctx.view_as_blocked:
        return _blocked("view_as_mode")
    return None


def evaluate(ctx, course) -> Decision:
    """Bir tarixçə sətri üçün qərar + «sonradan yazılıb?» xəbərdarlığı (yazı yoxdur)."""
    decision = _decide(ctx, course)
    if decision.state == READY:
        users = {course.instructor_id: course.instructor}
        users.update({a.teacher_id: a.teacher for row in ctx.rows.get(course.pk, []) for a in row.assignments.all()})
        holders = [users.get(step.get("source_id")) for step in decision.steps]
        decision.warning = written_since(
            organization=ctx.organization,
            course=course,
            teacher=ctx.teacher,
            holders=holders,
            handover=ctx.handovers.get(course.pk),
        )
    return decision


def _decide(ctx, course) -> Decision:
    gate = _gates(ctx, course)
    if gate is not None:
        return gate
    teacher = ctx.teacher
    kinds = [kind for kind in KINDS if getattr(course, f"journal_recorded_{kind}", False)]
    if not kinds:
        return _blocked("no_records")
    rows = ctx.rows.get(course.pk, [])
    if len(rows) > 1 or (rows and {g.pk for g in rows[0].groups.all()} != {course.group_id}):
        shared = shared_rows(ctx.organization, [course]).get(course.pk) or {}
        return _blocked("patok", link=shared.get("url", ""), groups=shared.get("groups", ""))
    owner_is_teacher = course.instructor_id == teacher.pk
    if not rows:
        if owner_is_teacher:
            # Sətir yoxdur — saat bölgüsünü insan verməlidir (mövcud bərpa forması).
            if course.pk not in ctx.taught:
                return _blocked("no_records")
            if available_chairs(ctx.actor, course):
                return Decision(FORM, link=reverse("workload:history_restore", args=[course.pk]))
            return _blocked("scope_workload")
        # Rəsmi sətir olmayan jurnalı «Fənn təhvili» cari edir (current_handover_journals).
        if not ctx.can_change_owner(course):
            return _blocked("scope_handover")
        step = ctx.owner_step(course)
        step["op"] = "reassign"  # geri qaytarma təhvil izini silir — sətirsiz jurnal onda cari olmazdı
        return Decision(READY, steps=[step])
    row = rows[0]
    link = _row_url(row)
    if row.task.status not in OPEN_TASK_STATUSES:
        return _blocked("task", link=link)
    if str(row.task.chair_id) not in ctx.distribute:
        return _blocked("scope_workload", link=link)
    assignments = list(row.assignments.all())
    plan = automatic_plan(row, course) if owner_is_teacher else None
    if plan is None:
        plan = zero_placeholder_plan(row, course=course, group_ids={course.group_id}, assignments=assignments)
    if (
        plan is not None
        and course.pk in ctx.taught
        and any(chair.pk == row.task.chair_id for chair in available_chairs(ctx.actor, course))
    ):
        # Sətrin öz dəqiq planı — mövcud bərpa servisi (sillabus bağlantısı + akademik qrafın toxunulmazlığı).
        steps = []
        if not owner_is_teacher:
            if not ctx.can_change_owner(course):
                return _blocked("scope_handover", link=link)
            steps.append(ctx.owner_step(course))
        steps.append({"op": "load_restore", "hours": plan, "chair_id": row.task.chair_id})
        return Decision(READY, steps=steps, link=link)
    steps, moved = [], set()
    for kind in kinds:
        own = [a for a in assignments if a.activity == kind]
        if own and all(a.teacher_id == teacher.pk for a in own):
            continue
        total = row.activity_total(kind)
        if len(own) > 1:
            return _blocked("split", link=link, kind=Activity(kind).label)
        prior = own[0] if own else None
        hours = prior.hours if prior else total - sum(a.hours for a in own)
        if total <= 0 or hours <= 0:
            return _blocked("kind_missing", link=link, kind=Activity(kind).label)
        if prior is not None:
            moved.add(prior.pk)
        steps.append(
            {
                "op": "assign",
                "row_id": row.pk,
                "kind": kind,
                "assignment_id": getattr(prior, "pk", None),
                "hours": hours,
                "source_id": getattr(prior, "teacher_id", None),
                "source_name": _name(getattr(prior, "teacher", None)),
                "target_name": _name(teacher),
            }
        )
    if not owner_is_teacher:
        keeps = any(a.teacher_id == course.instructor_id and a.pk not in moved for a in assignments)
        if course.pk in ctx.handovers and ctx.can_change_owner(course):
            steps.append({**ctx.owner_step(course), "conditional": True})
        elif not keeps and ctx.can_change_owner(course):
            steps.append({**ctx.owner_step(course), "op": "reassign", "conditional": True})
        elif not steps:
            return _blocked("owner_conflict", link=link, owner=_name(course.instructor))
    if not steps:
        return _blocked("mismatch", link=link)
    return Decision(READY, steps=steps, link=link)


def _list_actor(request):
    """(aktor, view-as bloku) — səlahiyyəti olmayan üçün ``None`` (heç nə göstərilmir)."""
    try:
        return actor_for_restore(request), False
    except WorkloadDenied:
        pass
    real = getattr(request, "real_user", None)
    if not getattr(request, "is_view_as", False) or real is None:
        return None, False
    return resolve_actor(real, request.organization), True


def _privileged(actor) -> bool:
    return actor.has(PERM_DISTRIBUTE) or handover.can_reassign(actor.user, actor.organization)


def _teacher(teacher_id):
    try:
        pk = int(teacher_id)
    except (TypeError, ValueError):
        return None
    return get_user_model().objects.filter(pk=pk, is_active=True).first()


def attach(request, offerings, *, teacher_id=None):
    """Jurnal siyahısı: tarixçə sətrinə ``history_teacher_restore``.

    * müəllimin öz «Əvvəlki jurnal qeydlərim» görünüşü (view-as daxil) — müəllim ``request.user``-dir;
    * geniş (admin) siyahı + MÜƏLLİM süzgəci (``teacher_id``, sahib 2026-11-04) — sətirlər süzgəcdəki müəllimin
      gözü ilə yenidən annotasiya olunur; onun üçün artıq cari olan sətrə heç nə düşmür.
    """
    if request is None or getattr(request, "organization", None) is None:
        return
    teacher = request.user
    if teacher_id:
        teacher = _teacher(teacher_id)
        if teacher is None:
            return
    current = [course for course in offerings if course.period.is_current]
    if not current:
        return
    actor, view_as_blocked = _list_actor(request)
    if actor is None or not _privileged(actor):
        return
    if teacher_id:
        model = apps.get_model("registrar.CourseOffering")
        queryset = model.objects.filter(
            organization=actor.organization, pk__in=[course.pk for course in current]
        ).select_related("period", "subject", "group", "instructor")
        seen = {row.pk: row for row in teacher_journal_list.own_visible_queryset(queryset, teacher, actor.organization)}
        pairs = [(course, seen[course.pk]) for course in current if course.pk in seen]
    else:
        pairs = [(course, course) for course in current]
    pairs = [(row, view) for row, view in pairs if getattr(view, "journal_is_current_load", None) is False]
    if not pairs:
        return
    ctx = _Context(actor, teacher, [view for _row, view in pairs], view_as_blocked=view_as_blocked)
    for row, view in pairs:
        row.history_teacher_restore = evaluate(ctx, view).as_row(view, teacher)


def _current(teacher, organization, offering_id):
    model = apps.get_model("registrar.CourseOffering")
    queryset = model.objects.filter(organization=organization, pk=offering_id).select_related(
        "period", "subject", "group", "instructor"
    )
    return teacher_journal_list.own_visible_queryset(queryset, teacher, organization).first()


def _owner_change(step, *, actor, course, teacher, reason, request):
    try:
        if step["op"] == "revert":
            handover_actions.revert(
                actor=actor.user,
                organization=actor.organization,
                handover_id=step["handover_id"],
                reason=reason,
                request=request,
            )
        else:
            handover_actions.reassign(
                actor=actor.user,
                organization=actor.organization,
                offering_id=course.pk,
                new_instructor_id=teacher.pk,
                reason=reason,
                request=request,
            )
    except handover_actions.HandoverError as exc:
        raise Denied("handover_blocked", detail=_handover_detail(exc)) from None


def _handover_detail(exc) -> str:
    texts = {
        "outside_scope": pgettext(CTX, "jurnal səlahiyyət sahənizə düşmür"),
        "journal_closed": pgettext(CTX, "jurnal bağlanıb"),
        "past_period": pgettext(CTX, "semestr başa çatıb"),
        "offering_inactive": pgettext(CTX, "dərs açılışı aktiv deyil"),
        "target_not_eligible": pgettext(CTX, "müəllimin bal yazma səlahiyyəti yoxdur"),
        "chain_moved": pgettext(CTX, "fənn təhvildən sonra yenidən başqasına verilib"),
        "concurrent_change": pgettext(CTX, "jurnalın müəllimi az öncə dəyişdirilib"),
        "share_state_changed": pgettext(CTX, "jurnal payları təhvildən sonra dəyişib"),
    }
    codes = list(exc.codes or ()) or [exc.code]
    return "; ".join(texts.get(code, code) for code in codes)


def _assign(step, *, actor, teacher, reason, request):
    row = TeachingTaskRow.objects.select_related("task").get(pk=step["row_id"], organization=actor.organization)
    prior = None
    if step["assignment_id"]:
        prior = TeacherAssignment.objects.select_for_update().filter(pk=step["assignment_id"], row=row).first()
        if prior is None:
            raise Denied("changed")
    assign_amended(
        row=row,
        actor=actor,
        activity=step["kind"],
        teacher_id=teacher.pk,
        hours=step["hours"],
        assignment=prior,
        groups_note=getattr(prior, "groups_note", ""),
        is_hourly_paid=getattr(prior, "is_hourly_paid", False),
        note=reason,
        amend={"reason": AmendmentReason.CORRECTION, "note": reason},
        request=request,
    )


@transaction.atomic
def restore_for_teacher(*, request, offering_id, reason, teacher_id=None):
    """Tarixçə jurnalını müəllimin CARİ jurnalına qaytarır (hamısı və ya heç nə).

    Müəllim — ``teacher_id`` (admin siyahısının süzgəci) və ya siyahının sahibi ``request.user`` (view-as).
    Səbəb: indiki sahib sonradan yazıbsa MƏCBURİ (≥10); heç kim yazmayıbsa boş qala bilər (standart mətn).
    """
    actor = actor_for_restore(request)
    if not _privileged(actor):
        raise Denied("scope_workload", status=403)
    organization = actor.organization
    teacher = _teacher(teacher_id) if teacher_id not in (None, "") else request.user
    if teacher is None:
        raise Denied("not_found", status=404)
    reason = str(reason or "").strip()
    if reason and not MIN_REASON <= len(reason) <= MAX_REASON:
        raise Denied("reason", status=400)
    model = apps.get_model("registrar.CourseOffering")
    locked = model.objects.select_for_update(of=("self",)).filter(organization=organization, pk=offering_id)
    if locked.values_list("pk", flat=True).first() is None:
        raise Denied("not_found", status=404)
    course = _current(teacher, organization, offering_id)
    if course is None:
        raise Denied("not_found", status=404)
    if course.journal_is_current_load:
        return {"status": "already_current", "offering_id": str(course.pk)}
    decision = evaluate(_Context(actor, teacher, [course]), course)
    if decision.state != READY:
        raise Denied(decision.code or "changed", **decision.params)
    if not reason:
        if decision.warning:
            raise Denied("reason", status=400)
        reason = DEFAULT_REASON
    done = []
    for step in decision.steps:
        if step.get("conditional"):
            # Sahiblik yalnız yük addımlarından sonra da lazımdırsa: sinxron jurnalı artıq bu müəllimə
            # verə bilər (sahib yükün əvvəlki sahibi idi) — onda təhvil/geri qaytarma artıqdır.
            fresh = _current(teacher, organization, course.pk)
            if fresh is None or fresh.journal_is_current_load or fresh.instructor_id == teacher.pk:
                continue
        if step["op"] == "assign":
            _assign(step, actor=actor, teacher=teacher, reason=reason, request=request)
        elif step["op"] == "load_restore":
            restore(
                request=request,
                offering_id=course.pk,
                chair_id=step["chair_id"],
                hours=step["hours"],
                reason=reason,
            )
        else:
            _owner_change(step, actor=actor, course=course, teacher=teacher, reason=reason, request=request)
        done.append(step_text(step))
    fresh = _current(teacher, organization, course.pk)
    if fresh is None or not fresh.journal_is_current_load:
        raise Denied("not_current")
    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=organization,
        resource_type="workload.HistoryTeacherRestore",
        resource_id=str(course.pk),
        reason=reason,
        old_values={
            "journal_is_current_load": False,
            "teacher_id": teacher.pk,
            "written_since": warning_text(decision.warning) if decision.warning else [],
        },
        new_values={"journal_is_current_load": True, "teacher_id": teacher.pk, "steps": done},
        request=request,
    )
    return {"status": "restored", "offering_id": str(course.pk), "steps": done}


__all__ = ["BLOCKED", "FORM", "READY", "Decision", "Denied", "attach", "evaluate", "restore_for_teacher"]
