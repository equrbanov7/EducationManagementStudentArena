"""Jurnalın cari sahibi və görünən dərslərin faktiki müəllifliyi — tarixçəni yenidən yazmadan."""

from collections import defaultdict

from django.contrib.auth import get_user_model

from .handover import offering_history


def history_context(offering, journal):
    """Yalnız icazəsi yoxlanmış jurnalın artıq daraldılmış sətir/sütunları ilə çağırılır.

    ``Lesson.instructor`` keçilmiş dərsin müəllimidir; ``created_by`` dərsi yaradan,
    ``LessonMark.entered_by`` həmin xananın yazılmış müəllif məlumatıdır. NULL heç
    vaxt cari açılış sahibindən doldurulmur. Adlar toplu oxunur (sətir başına sorğu yoxdur).
    """
    lessons = journal.get("lessons", [])
    ids = {offering.instructor_id} if offering.instructor_id else set()
    for lesson in lessons:
        ids.update(pk for pk in (lesson.instructor_id, lesson.created_by_id) if pk)
    authors = defaultdict(set)
    unknown = defaultdict(bool)
    visible_ids = {lesson.pk for lesson in lessons}
    for row in journal.get("rows", []):
        for cell in row.get("cells", []):
            mark = cell.get("mark")
            if mark is None or mark.lesson_id not in visible_ids:
                continue
            if mark.entered_by_id:
                authors[mark.lesson_id].add(mark.entered_by_id)
                ids.add(mark.entered_by_id)
            else:
                unknown[mark.lesson_id] = True
    names = {
        user.pk: (user.get_full_name() or user.username)
        for user in get_user_model().objects.filter(pk__in=ids).only("id", "first_name", "last_name", "username")
    }
    return {
        "current_owner": names.get(offering.instructor_id),
        "handovers": list(offering_history(offering).filter(organization_id=offering.organization_id)),
        "lessons": [
            {
                "lesson": lesson,
                "instructor": names.get(lesson.instructor_id),
                "created_by": names.get(lesson.created_by_id),
                "authors": sorted(names[pk] for pk in authors[lesson.pk] if pk in names),
                "unknown_author": unknown[lesson.pk] or not authors[lesson.pk],
            }
            for lesson in lessons
        ],
    }
