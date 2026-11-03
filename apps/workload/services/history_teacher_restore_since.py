"""«Sonradan yazılıb?» — jurnal müəllimdən alınandan sonra indiki sahibin(lərin) yazdıqları (yalnız oxu).

Sahib (2026-11-04): «müəllimdən əgər çıxmışdısa o fənn, sonra isə yazmayıbsa, çox daha rahat formada o müəllimə
keçsin». Yəni: heç kim yazmayıbsa bərpa bir kliklə (səbəb istəyə bağlı); indiki sahib yazıbsa yenə olur, amma modal
KİMİN, NƏ QƏDƏR, NƏ VAXTDAN yazdığını göstərir və səbəb məcburidir. Qeydlər heç vaxt köçürülmür/silinmir.

«Nə vaxtdan»: bu müəllimdən edilmiş geri qaytarılmamış təhvilin anı; təhvil yoxdursa (yük «Yük bölgüsü»ndə
dəyişib) müəllimin bu jurnaldakı SON öz qeydi (dərs yaratması/keçməsi və ya bal yazması) — ondan sonrakılar sayılır.
"""

from __future__ import annotations

from django.apps import apps
from django.db.models import Max, Q


def _last_own_activity(organization, course, teacher):
    lessons = apps.get_model("registrar.Lesson").objects.filter(organization=organization, offering=course)
    marks = apps.get_model("registrar.LessonMark").objects.filter(
        organization=organization, lesson__offering=course, entered_by=teacher
    )
    stamps = [
        lessons.filter(Q(instructor=teacher) | Q(created_by=teacher)).aggregate(at=Max("created_at"))["at"],
        marks.aggregate(at=Max("updated_at"))["at"],
    ]
    stamps = [stamp for stamp in stamps if stamp is not None]
    return max(stamps) if stamps else None


def written_since(*, organization, course, teacher, holders, handover=None):
    """``None`` — heç kim yazmayıb; əks halda ``{"since": datetime|None, "people": [(user, lessons, marks)]}``."""
    holders = [user for user in holders if user is not None and user.pk != teacher.pk]
    if not holders:
        return None
    since = handover.created_at if handover is not None else _last_own_activity(organization, course, teacher)
    lessons = apps.get_model("registrar.Lesson").objects.filter(organization=organization, offering=course)
    marks = apps.get_model("registrar.LessonMark").objects.filter(organization=organization, lesson__offering=course)
    if since is not None:
        lessons, marks = lessons.filter(created_at__gt=since), marks.filter(updated_at__gt=since)
    people = []
    for user in {user.pk: user for user in holders}.values():
        own_lessons = lessons.filter(Q(instructor=user) | Q(created_by=user)).count()
        own_marks = marks.filter(entered_by=user).count()
        if own_lessons or own_marks:
            people.append((user, own_lessons, own_marks))
    return {"since": since, "people": people} if people else None
