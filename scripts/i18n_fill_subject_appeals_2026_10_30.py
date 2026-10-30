"""Append-only localization of scoped subject appeals and teacher Exam Center invitation."""

import json
from pathlib import Path

import polib

ROOT = Path(__file__).resolve().parents[1]
MESSAGES = {
    ("organizations.permission.label", "Öz kafedrasının fənn apellyasiyalarına baxmaq"): (
        "View subject appeals for the assigned department",
        "Просмотр апелляций по предметам своей кафедры",
        "Kendi bölümünün ders itirazlarını görüntüleme",
        "Einsprüche zu Fächern des eigenen Fachbereichs anzeigen",
    ),
    (
        "appeals.notification",
        "Tələbə: {student} ({username}); qrup: {group}; fənn: {subject}; imtahan: {exam}; sual sayı: {count}.",
    ): (
        "Student: {student} ({username}); group: {group}; subject: {subject}; exam: {exam}; questions: {count}.",
        "Студент: {student} ({username}); группа: {group}; предмет: {subject}; экзамен: {exam}; вопросов: {count}.",
        "Öğrenci: {student} ({username}); grup: {group}; ders: {subject}; sınav: {exam}; soru sayısı: {count}.",
        "Studierende Person: {student} ({username}); Gruppe: {group}; Fach: {subject}; Prüfung: {exam}; Fragen: {count}.",
    ),
    ("appeals.notification", "Müəllim: {teachers}. Apellyasiya ilə bağlı İmtahan Mərkəzinə yaxınlaşın. {details}"): (
        "Teacher: {teachers}. Please visit the Exam Center regarding the appeal. {details}",
        "Преподаватель: {teachers}. Подойдите в Экзаменационный центр по поводу апелляции. {details}",
        "Öğretmen: {teachers}. İtirazla ilgili Sınav Merkezine başvurun. {details}",
        "Lehrkraft: {teachers}. Bitte kommen Sie wegen des Einspruchs zum Prüfungszentrum. {details}",
    ),
    (
        "appeals.notification",
        "Fənni tədris edən müəllim: {teachers}. Müəllim apellyasiya ilə bağlı İmtahan Mərkəzinə dəvət olunur. {details}",
    ): (
        "Subject teacher: {teachers}. The teacher is invited to the Exam Center regarding the appeal. {details}",
        "Преподаватель предмета: {teachers}. Преподаватель приглашён в Экзаменационный центр по поводу апелляции. {details}",
        "Dersi veren öğretmen: {teachers}. Öğretmen, itirazla ilgili Sınav Merkezine davet edilmiştir. {details}",
        "Lehrkraft des Fachs: {teachers}. Die Lehrkraft wird wegen des Einspruchs ins Prüfungszentrum gebeten. {details}",
    ),
    ("appeals.notification", "Fənn üzrə yeni apellyasiya"): (
        "New subject appeal",
        "Новая апелляция по предмету",
        "Dersle ilgili yeni itiraz",
        "Neuer Einspruch zum Fach",
    ),
}


def fill(language, index):
    path = ROOT / "locale" / language / "LC_MESSAGES" / "django.po"
    catalog = polib.pofile(path)
    for (context, message), translations in MESSAGES.items():
        if catalog.find(message, msgctxt=context):
            continue
        value = message if language == "az" else translations[index]
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                "\nmsgctxt "
                + json.dumps(context)
                + "\nmsgid "
                + json.dumps(message, ensure_ascii=False)
                + "\nmsgstr "
                + json.dumps(value, ensure_ascii=False)
                + "\n"
            )
    polib.pofile(path).save_as_mofile(path.with_suffix(".mo"))


if __name__ == "__main__":
    for language, index in (("az", 0), ("en", 0), ("ru", 1), ("tr", 2), ("de", 3)):
        fill(language, index)
