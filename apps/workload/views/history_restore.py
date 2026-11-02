"""An explicit allocation form, with normal workload authority and amendment services."""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import pgettext_lazy
from django.views.decorators.http import require_http_methods

from apps.syllabus.public import TransitionDenied, approved_restore_sources

from ..constants import Activity
from ..services.history_restore import KINDS, plan, previous_plan, restore, syllabus_context
from ..services.scoping import WorkloadDenied

CTX = "workload.history_restore"


class RestoreForm(forms.Form):
    chair = forms.ChoiceField(label=pgettext_lazy(CTX, "Kafedra"))
    lecture = forms.IntegerField(label=Activity.LECTURE.label, min_value=0, max_value=1000)
    seminar = forms.IntegerField(label=Activity.SEMINAR.label, min_value=0, max_value=1000)
    lab = forms.IntegerField(label=Activity.LAB.label, min_value=0, max_value=1000)
    syllabus = forms.ChoiceField(label=pgettext_lazy(CTX, "Təsdiqli sillabus"), required=False)
    reason = forms.CharField(
        label=pgettext_lazy(CTX, "Səbəb"), min_length=10, max_length=2000, widget=forms.Textarea(attrs={"rows": 3})
    )


@login_required
@require_http_methods(["GET", "POST"])
def history_restore(request, offering_id):
    if getattr(request, "organization", None) is None:
        raise Http404
    try:
        actor, course, chairs = plan(request, offering_id)
    except WorkloadDenied:
        raise Http404 from None
    initial, provenance = previous_plan(course)
    if initial:
        initial["reason"] = "Tarixi jurnalın əvvəlki təsdiqlənmiş dərs yükü bərpa olunur."
    form = RestoreForm(request.POST if request.method == "POST" else None, initial=initial)
    sources = approved_restore_sources(course, context_for=syllabus_context)
    form.fields["syllabus"].choices = [("", "Avtomatik: yalnız bir dəqiq uyğun mənbə varsa")] + [
        (
            str(s.pk),
            str(s.offering.group.name)
            + " · "
            + " · ".join(
                str(Activity(kind).label) + ": " + str(s.approved_version.plan_hours.get(kind, 0))
                for kind in KINDS
                if s.approved_version.plan_hours.get(kind, 0)
            ),
        )
        for s in sources
    ]
    own_source = next((s for s in sources if s.offering_id == course.pk), None)
    if own_source is not None or len(sources) == 1:
        form.initial["syllabus"] = str((own_source or sources[0]).pk)
    elif len(sources) > 1:
        form.fields["syllabus"].required = True
    form.fields["chair"].choices = [(str(chair.pk), chair.name) for chair in chairs]
    if len(chairs) == 1:
        form.initial["chair"] = str(chairs[0].pk)
    for name, field in form.fields.items():
        field.widget.attrs["class"] = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
        if form.is_bound and form[name].errors:
            field.widget.attrs["aria-describedby"] = "restore-" + name + "-errors"
            field.widget.attrs["aria-invalid"] = "true"
    if request.method == "POST" and form.is_valid():
        try:
            restore(
                request=request,
                offering_id=offering_id,
                chair_id=form.cleaned_data["chair"],
                hours={kind: form.cleaned_data[kind] for kind in KINDS},
                reason=form.cleaned_data["reason"],
                syllabus_id=form.cleaned_data["syllabus"],
            )
        except WorkloadDenied as exc:
            form.add_error(None, exc.message)
        except (TransitionDenied, ValueError):
            form.add_error(
                None,
                pgettext_lazy(CTX, "Mənbə sillabusu və jurnal qeydləri yenidən yoxlanmalıdır; dəyişiklik edilmədi."),
            )
        else:
            messages.success(request, pgettext_lazy(CTX, "Cari dərs yükü bərpa edildi."))
            return redirect("registrar:journal_detail", offering_id=course.pk)
    return render(
        request,
        "workload/history_restore.html",
        {"restore_form": form, "offering": course, "plan_provenance": provenance},
    )
