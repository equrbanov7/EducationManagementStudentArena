"""Server-rendered, CSRF-protected language level cohort management."""

from django import forms
from django.apps import apps
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from . import guest_roster, language_cohort_placement, language_cohort_query, language_cohorts
from .integrity import eligible_instructor_user_ids
from .journal_home_groups import home_group_map
from .language_cohort_history import can_view_source
from .language_levels import level_of
from .models import Enrollment, LanguageLevelCohort, Subject


class TeacherChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.get_full_name()} {getattr(obj.profile, 'patronymic', '')}".strip()


class SourceChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.subject.name} · {obj.period.name} · {getattr(obj.group, 'name', '—')} · {obj.instructor.get_full_name() if obj.instructor else '—'}"


class CohortForm(forms.Form):
    name = forms.CharField(label=_("Qrup adı"), max_length=100, min_length=2)
    department = forms.ModelChoiceField(label=_("Kafedra"), queryset=None)
    period = forms.ModelChoiceField(label=_("Semestr"), queryset=None)
    subject = forms.ModelChoiceField(label=_("Səviyyə fənni"), queryset=None)
    instructor = TeacherChoice(label=_("Müəllim"), queryset=None)
    confirm_separate = forms.BooleanField(
        label=_("Mövcud eyni səviyyə jurnalından ayrıca yeni qrup yaratmağı təsdiqləyirəm"), required=False
    )
    lecture_hours = forms.IntegerField(label=_("Mühazirə saatı"), min_value=0, max_value=300)
    seminar_hours = forms.IntegerField(label=_("Seminar / praktiki məşğələ saatı"), min_value=0, max_value=300)
    lab_hours = forms.IntegerField(label=_("Laboratoriya saatı"), min_value=0, max_value=300)
    source_offering = SourceChoice(
        label=_("Eyni səviyyə, semestr və müəllimin qiymətləndirmə mənbəyi"), queryset=None, required=False
    )
    entry_score_max = forms.IntegerField(
        label=_("Giriş balının maksimumu (mənbə seçilməyibsə)"), min_value=1, max_value=100, required=False
    )
    pass_threshold = forms.IntegerField(
        label=_("Ümumi keçid balı (mənbə seçilməyibsə)"), min_value=1, max_value=100, required=False
    )
    min_final_exam_score = forms.IntegerField(
        label=_("Yekun imtahanın minimum balı (mənbə seçilməyibsə)"), min_value=0, max_value=100, required=False
    )

    def __init__(self, *args, actor, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = language_cohorts.department_choices(actor, organization)
        self.fields["period"].queryset = apps.get_model("organizations", "AcademicPeriod").objects.filter(
            organization=organization, is_active=True, is_current=True
        )
        subjects = Subject.objects.filter(organization=organization, is_active=True).order_by("name")
        self.fields["subject"].queryset = subjects.filter(pk__in=[row.pk for row in subjects if level_of(row.name)])
        from .models import CourseOffering

        self.fields["source_offering"].queryset = (
            CourseOffering.objects.filter(
                organization=organization,
                is_active=True,
                period__is_current=True,
                period__is_active=True,
                assessment_scheme__isnull=False,
                subject_id__in=self.fields["subject"].queryset.values("pk"),
            )
            .select_related("subject", "period", "group", "instructor")
            .order_by("subject__name", "group__name")
        )
        self.fields["instructor"].queryset = (
            get_user_model()
            .objects.filter(pk__in=eligible_instructor_user_ids(organization=organization))
            .select_related("profile")
            .order_by("last_name", "first_name", "pk")
        )


def _organization(request):
    org = getattr(request, "organization", None)
    if org is None or not org.is_active or not request.user.is_active:
        raise Http404
    return org


@login_required
@require_http_methods(["GET", "POST"])
def index(request):
    org = _organization(request)
    can_create = language_cohorts.department_choices(request.user, org).exists()
    cohorts = language_cohorts.authorized_cohorts(request.user, org)
    existing = language_cohort_query.existing_level_journals(request.user, org)
    if request.method == "GET" and request.GET.get("cohort"):
        selected = next((row for row in cohorts if str(row.pk) == request.GET["cohort"]), None)
        if selected is None:
            raise Http404
        return redirect("registrar:language_cohort_detail", cohort_id=selected.pk)
    if not can_create and not cohorts and not existing:
        raise Http404
    form = CohortForm(request.POST or None, actor=request.user, organization=org) if can_create else None
    if request.method == "POST":
        if not can_create:
            raise Http404
        if form.is_valid():
            try:
                cohort = language_cohorts.create_cohort(organization=org, actor=request.user, **form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, exc)
            except IntegrityError:
                form.add_error(None, "Bu kafedra və semestr üçün qrup adı artıq mövcuddur.")
            else:
                return redirect("registrar:language_cohort_detail", cohort_id=cohort.pk)
    return render(request, "registrar/language_cohorts.html", {"cohorts": cohorts, "existing": existing, "form": form})


@login_required
@require_http_methods(["GET", "POST"])
def detail(request, cohort_id):
    org = _organization(request)
    cohort = get_object_or_404(
        LanguageLevelCohort.objects.select_related(
            "organization", "offering__subject", "offering__period", "period", "department"
        ),
        organization=org,
        pk=cohort_id,
    )
    if not language_cohorts.can_manage(request.user, cohort):
        raise Http404
    if request.method == "POST":
        try:
            if request.POST.get("action") == "remove":
                language_cohort_placement.remove_student(
                    cohort=cohort,
                    enrollment_id=request.POST.get("enrollment"),
                    actor=request.user,
                    reason=request.POST.get("reason"),
                )
            elif request.POST.get("action") == "place":
                language_cohort_placement.place_student(
                    cohort=cohort,
                    record_id=request.POST.get("record"),
                    actor=request.user,
                    reason=request.POST.get("reason"),
                    source_enrollment_id=request.POST.get("source") or None,
                )
            else:
                raise ValidationError(_("Əməliyyat düzgün deyil."))
        except PermissionDenied:
            raise Http404 from None
        except (ValidationError, Enrollment.DoesNotExist) as exc:
            messages.error(
                request, "; ".join(exc.messages) if isinstance(exc, ValidationError) else "Qeydiyyat tapılmadı."
            )
        else:
            messages.success(request, _("Siyahı yeniləndi. Əvvəlki qiymətlər öz jurnalında saxlanılır."))
        return redirect(reverse("registrar:language_cohort_detail", args=[cohort.pk]))
    enrollments = list(
        Enrollment.objects.filter(organization=org, offering=cohort.offering, status=Enrollment.Status.ENROLLED)
        .select_related("student")
        .order_by("student__last_name", "student__first_name", "pk")
    )
    groups = home_group_map(organization_id=org.pk, student_ids=[e.student_id for e in enrollments])
    rows = [{"enrollment": e, "home_group": groups.get(e.student_id)} for e in enrollments]
    candidates = []
    if guest_roster.roster_is_open(cohort.offering):
        for record in language_cohort_query.candidate_records(
            cohort=cohort, actor=request.user, query=request.GET.get("q")
        ):
            sources = language_cohorts.eligible_family_enrollments(cohort=cohort, student_id=record.student_id)
            candidates.append({"record": record, "sources": sources, "ambiguous": len(sources) > 1})
    events = (
        cohort.placements.filter(organization=org)
        .select_related("student", "actor", "home_group")
        .order_by("-created_at")[:50]
    )
    events = list(events.select_related("source_enrollment__offering__organization"))
    for event in events:
        event.can_view_history = can_view_source(request.user, event)
        event.action_label = {
            "add": _("Əlavə edildi"),
            "remove": _("Çıxarıldı"),
            "move": _("Səviyyə dəyişdirildi"),
        }.get(event.action, event.action)
    return render(
        request,
        "registrar/language_cohort_detail.html",
        {
            "cohort": cohort,
            "level_choices": [
                row
                for row in language_cohorts.authorized_cohorts(request.user, org)
                if row.period_id == cohort.period_id and row.family == cohort.family
            ],
            "rows": rows,
            "candidates": candidates,
            "events": events,
            "roster_open": guest_roster.roster_is_open(cohort.offering),
            "query": request.GET.get("q", ""),
        },
    )
