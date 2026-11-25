#!/usr/bin/env python3
"""«Qrupdan çıxar» (sahib 2026-11-25): tələbə qrupsuz qalır / əlavə üzv qrupun jurnallarından çıxır — yeni msgid-lər.

Yalnız kataloqda OLMAYAN sətirlər əlavə olunur (idempotent); mövcud tərcümələrə toxunulmur.
"""

import json
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parents[1]
LANGS = ("az", "en", "ru", "tr", "de")


def t(en, ru, tr, de):
    return dict(zip(LANGS[1:], (en, ru, tr, de)))


def quote(text):
    return json.dumps(text, ensure_ascii=False)


GROUPS = {
    "Tələbəni qrupdan çıxar": t(
        "Remove student from group",
        "Исключить студента из группы",
        "Öğrenciyi gruptan çıkar",
        "Person aus der Gruppe entfernen",
    ),
    "Tələbə xaric edilmir və dondurulmur: statusu «Qeydiyyatlı» qalır, sadəcə qrupsuz olur — sonra «Tələbə əlavə et» "
    "ilə istənilən qrupa qoşmaq olar. Bu qrupun cari semestr jurnallarındakı qeydiyyatı tarixçəyə keçir, bal və "
    "davamiyyət silinmir. Səbəb audit jurnalına yazılır.": t(
        "The student is not expelled or put on leave: the status stays “Enrolled”, the student simply has no group — "
        "later “Add student” can attach them to any group. Their enrolments in this group's current-semester "
        "gradebooks move to history; marks and attendance are kept. The reason is written to the audit log.",
        "Студент не отчисляется и не замораживается: статус остаётся «Зачислен», он просто остаётся без группы — "
        "позже через «Добавить студента» его можно добавить в любую группу. Записи в журналах текущего семестра "
        "этой группы переходят в историю, оценки и посещаемость сохраняются. Причина записывается в журнал аудита.",
        "Öğrenci kaydı silinmez ve dondurulmaz: durumu «Kayıtlı» kalır, yalnızca grupsuz olur — daha sonra «Öğrenci "
        "ekle» ile herhangi bir gruba eklenebilir. Bu grubun bu dönemki defterlerindeki kaydı geçmişe taşınır; notlar "
        "ve devam silinmez. Gerekçe denetim kaydına yazılır.",
        "Die Person wird weder exmatrikuliert noch beurlaubt: der Status bleibt „Eingeschrieben“, sie ist nur ohne "
        "Gruppe — später kann sie über „Person hinzufügen“ einer beliebigen Gruppe zugeordnet werden. Ihre Belegungen "
        "in den Klassenbüchern dieser Gruppe im laufenden Semester gehen in die Historie über; Noten und Anwesenheit "
        "bleiben erhalten. Der Grund wird im Audit-Protokoll gespeichert.",
    ),
    "Əlavə üzvü qrupdan çıxar": t(
        "Remove additional member from group",
        "Исключить дополнительного участника из группы",
        "Ek üyeyi gruptan çıkar",
        "Zusätzliches Mitglied aus der Gruppe entfernen",
    ),
    "Tələbə yalnız bu qrupun cari semestr jurnallarından çıxır — öz qrupu və oradakı jurnalları dəyişmir. Bal və "
    "davamiyyət silinmir, jurnalın dəyişiklik tarixçəsinə yazılır.": t(
        "The student leaves only this group's current-semester gradebooks — their own group and its gradebooks stay "
        "unchanged. Marks and attendance are kept; the change is written to the gradebook history.",
        "Студент исключается только из журналов текущего семестра этой группы — его собственная группа и её журналы "
        "не меняются. Оценки и посещаемость сохраняются, изменение записывается в историю журнала.",
        "Öğrenci yalnızca bu grubun bu dönemki defterlerinden çıkar — kendi grubu ve oradaki defterleri değişmez. "
        "Notlar ve devam silinmez; değişiklik defter geçmişine yazılır.",
        "Die Person verlässt nur die Klassenbücher dieser Gruppe im laufenden Semester — die eigene Gruppe und deren "
        "Klassenbücher bleiben unverändert. Noten und Anwesenheit bleiben erhalten; die Änderung steht in der "
        "Klassenbuch-Historie.",
    ),
    "Tələbə bu qrupun tələbəsi deyil.": t(
        "The student is not a member of this group.",
        "Студент не состоит в этой группе.",
        "Öğrenci bu grubun üyesi değil.",
        "Die Person gehört nicht zu dieser Gruppe.",
    ),
    "Əmr tarixi düzgün deyil.": t(
        "The order date is invalid.",
        "Неверная дата приказа.",
        "Karar tarihi geçersiz.",
        "Das Bescheiddatum ist ungültig.",
    ),
    "Tələbə qrupdan çıxarıldı — statusu «Qeydiyyatlı» qaldı, %(count)d jurnal sətri tarixçəyə keçdi.": t(
        "The student was removed from the group — the status stays “Enrolled”, %(count)d gradebook rows moved to "
        "history.",
        "Студент исключён из группы — статус остался «Зачислен», %(count)d строк журнала перешли в историю.",
        "Öğrenci gruptan çıkarıldı — durumu «Kayıtlı» kaldı, %(count)d defter satırı geçmişe taşındı.",
        "Die Person wurde aus der Gruppe entfernt — der Status bleibt „Eingeschrieben“, %(count)d "
        "Klassenbuchzeilen gingen in die Historie über.",
    ),
    "Bu tələbə qrupun öz tələbəsidir — əlavə üzv deyil.": t(
        "This student belongs to the group itself — not an additional member.",
        "Этот студент — собственный студент группы, а не дополнительный участник.",
        "Bu öğrenci grubun kendi öğrencisidir — ek üye değil.",
        "Diese Person gehört zur Gruppe selbst — sie ist kein zusätzliches Mitglied.",
    ),
    "Əlavə üzv qrupun %(count)d jurnalından çıxarıldı — öz qrupu dəyişmədi.": t(
        "The additional member was removed from %(count)d of the group's gradebooks — their own group is unchanged.",
        "Дополнительный участник исключён из %(count)d журналов группы — его собственная группа не изменилась.",
        "Ek üye grubun %(count)d defterinden çıkarıldı — kendi grubu değişmedi.",
        "Das zusätzliche Mitglied wurde aus %(count)d Klassenbüchern der Gruppe entfernt — die eigene Gruppe bleibt.",
    ),
}

REMOVAL = {
    "Akademik dövr tələbənin təşkilatına aid deyil.": t(
        "The academic period does not belong to the student's organisation.",
        "Учебный период не относится к организации студента.",
        "Akademik dönem öğrencinin kurumuna ait değil.",
        "Der Studienabschnitt gehört nicht zur Einrichtung der Person.",
    ),
    "Aktiv cari akademik dövr göstərilməlidir.": t(
        "The active current academic period must be given.",
        "Необходимо указать активный текущий учебный период.",
        "Etkin güncel akademik dönem belirtilmelidir.",
        "Der aktive laufende Studienabschnitt muss angegeben werden.",
    ),
    "Qrupdan çıxarma yalnız aktiv cari akademik dövrdə aparılır.": t(
        "Removal from a group is only possible in the active current academic period.",
        "Исключение из группы возможно только в активном текущем учебном периоде.",
        "Gruptan çıkarma yalnızca etkin güncel akademik dönemde yapılır.",
        "Das Entfernen aus einer Gruppe ist nur im aktiven laufenden Studienabschnitt möglich.",
    ),
    "Tələbə onsuz da heç bir qrupda deyil.": t(
        "The student is already not in any group.",
        "Студент и так не состоит ни в одной группе.",
        "Öğrenci zaten hiçbir grupta değil.",
        "Die Person ist bereits in keiner Gruppe.",
    ),
    "Yalnız qeydiyyatlı tələbə qrupdan çıxarılır — məzuniyyətdə / xaric edilmiş deyil.": t(
        "Only an enrolled student can be removed from a group — not one on leave or expelled.",
        "Из группы исключается только зачисленный студент — не находящийся в отпуске или отчисленный.",
        "Yalnızca kayıtlı öğrenci gruptan çıkarılır — izinli veya kaydı silinmiş öğrenci değil.",
        "Nur eingeschriebene Personen können aus einer Gruppe entfernt werden — keine beurlaubten oder "
        "exmatrikulierten.",
    ),
    "Qrupdan çıxarma üçün icraçı tələb olunur.": t(
        "Removal from a group requires an acting user.",
        "Для исключения из группы требуется исполнитель.",
        "Gruptan çıkarma için işlemi yapan kullanıcı gerekir.",
        "Für das Entfernen aus einer Gruppe ist eine handelnde Person erforderlich.",
    ),
    "Bu tələbənin öz qrupudur — əlavə üzv deyil.": t(
        "This is the student's own group — not an additional membership.",
        "Это собственная группа студента — не дополнительное участие.",
        "Bu öğrencinin kendi grubudur — ek üyelik değil.",
        "Das ist die eigene Gruppe der Person — keine zusätzliche Mitgliedschaft.",
    ),
    "Cari akademik dövr yoxdur — jurnal siyahısı dəyişdirilmir.": t(
        "There is no current academic period — gradebook rosters are not changed.",
        "Нет текущего учебного периода — списки журналов не изменяются.",
        "Güncel akademik dönem yok — defter listeleri değiştirilmez.",
        "Es gibt keinen laufenden Studienabschnitt — Klassenbuchlisten werden nicht geändert.",
    ),
    "Tələbə bu qrupun cari jurnallarında yoxdur.": t(
        "The student is not in this group's current gradebooks.",
        "Студента нет в текущих журналах этой группы.",
        "Öğrenci bu grubun güncel defterlerinde yok.",
        "Die Person steht nicht in den aktuellen Klassenbüchern dieser Gruppe.",
    ),
    "Qrup reyestrindən əlavə üzvlük götürüldü": t(
        "Additional membership withdrawn from the group registry",
        "Дополнительное участие снято из реестра групп",
        "Ek üyelik grup kaydından geri alındı",
        "Zusätzliche Mitgliedschaft über das Gruppenregister zurückgenommen",
    ),
    "Heç bir jurnaldan çıxarılmadı.": t(
        "Not removed from any gradebook.",
        "Не исключён ни из одного журнала.",
        "Hiçbir defterden çıkarılmadı.",
        "Aus keinem Klassenbuch entfernt.",
    ),
}

ENTRIES = {"django": {"accounts.groups": GROUPS, "registrar.group_removal": REMOVAL}}


def fill():
    counts = {}
    for domain, contexts in ENTRIES.items():
        for lang in LANGS:
            path = BASE / "locale" / lang / "LC_MESSAGES" / f"{domain}.po"
            existing = {(e.msgctxt or "", e.msgid) for e in polib.pofile(path) if not e.obsolete}
            blocks = []
            for context, messages in contexts.items():
                for msgid, translations in messages.items():
                    if (context, msgid) in existing:
                        continue
                    value = msgid if lang == "az" else translations[lang]
                    lines = ["#, python-format"] if "%(" in msgid else []
                    lines.append("msgctxt " + quote(context))
                    lines += ["msgid " + quote(msgid), "msgstr " + quote(value)]
                    blocks.append("\n".join(lines) + "\n")
            if blocks:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("\n" + "\n".join(blocks))
            counts[f"{domain}/{lang}"] = len(blocks)
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    fill()
