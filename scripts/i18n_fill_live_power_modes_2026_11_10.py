#!/usr/bin/env python3
"""i18n — canlı oyunun güc rejimləri: 💣 Bomba rejimi, ×2 Xal rejimi, final rəqs şousu (sahib 2026-11-10).

Yeni mətnlər: aparıcının sürətli düymələri, sol panel bloku, tənzimləmə çekməcəsi qrupu, host JS
bildirişləri (``_host_i18n.html``) və telefon nişanları (``player_screen.html``) — hamısı
``live_exam.power_modes`` kontekstində.

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`. ⚠️ `makemessages` İŞLƏDİLMİR.
İstifadə:  python scripts/i18n_fill_live_power_modes_2026_11_10.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]
CTX = "live_exam.power_modes"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    CTX: {
        "Bomba rejimi": t("Bomb mode", "Режим бомбы", "Bomba modu", "Bombenmodus"),
        "×2 Xal rejimi": t("×2 Points mode", "Режим ×2 очков", "×2 Puan modu", "×2-Punkte-Modus"),
        "Oyun effektləri": t("Game effects", "Игровые эффекты", "Oyun efektleri", "Spieleffekte"),
        "Hər sual bombadır: səhv cavab bu oyundakı xalı sıfırlayır.": t(
            "Every question is a bomb: a wrong answer resets the score in this game.",
            "Каждый вопрос — бомба: неверный ответ обнуляет очки в этой игре.",
            "Her soru bombadır: yanlış cevap bu oyundaki puanı sıfırlar.",
            "Jede Frage ist eine Bombe: Eine falsche Antwort setzt die Punkte in diesem Spiel zurück.",
        ),
        "Düzgün cavab ikiqat xal gətirir.": t(
            "A correct answer earns double points.",
            "Правильный ответ даёт двойные очки.",
            "Doğru cevap iki kat puan kazandırır.",
            "Eine richtige Antwort bringt doppelte Punkte.",
        ),
        "Final rəqs şousu": t("Final dance show", "Финальное танцевальное шоу", "Final dans şovu", "Finale Tanzshow"),
        "Final səhnəsində avatarlar viral və özünəməxsus rəqslər edir.": t(
            "On the final stage the avatars perform viral and signature dances.",
            "В финальной сцене аватары исполняют вирусные и фирменные танцы.",
            "Final sahnesinde avatarlar viral ve kendilerine özgü danslar yapar.",
            "Auf der Finalbühne tanzen die Avatare virale und charaktereigene Tänze.",
        ),
        "Açıq olanda nəşr olunan hər sual bomba sualıdır: səhv və ya qismən düzgün cavab oyunçunun bu "
        "oyundakı xalını sıfırlayır. Cavabsız qalmaq partlatmır. Oyun gedərkən də dəyişir — cari suala hələ "
        "cavab yoxdursa dərhal, əks halda növbəti sualdan.": t(
            "When on, every published question is a bomb question: a wrong or partly correct answer resets the "
            "player's score in this game. Not answering does not explode. Can be changed during the game — "
            "applies to the current question at once if nobody has answered yet, otherwise from the next question.",
            "Когда включено, каждый опубликованный вопрос — вопрос-бомба: неверный или частично верный ответ "
            "обнуляет очки игрока в этой игре. Отсутствие ответа не взрывает бомбу. Можно менять во время игры — "
            "к текущему вопросу применяется сразу, если ещё никто не ответил, иначе со следующего вопроса.",
            "Açıkken yayınlanan her soru bomba sorusudur: yanlış veya kısmen doğru cevap oyuncunun bu oyundaki "
            "puanını sıfırlar. Cevapsız kalmak patlatmaz. Oyun sırasında da değiştirilebilir — mevcut soruya henüz "
            "cevap yoksa hemen, aksi halde sonraki sorudan itibaren uygulanır.",
            "Wenn aktiv, ist jede veröffentlichte Frage eine Bombenfrage: Eine falsche oder teilweise richtige "
            "Antwort setzt die Punkte des Spielers in diesem Spiel zurück. Keine Antwort lässt nichts explodieren. "
            "Auch während des Spiels änderbar — gilt sofort für die aktuelle Frage, wenn noch niemand geantwortet "
            "hat, sonst ab der nächsten Frage.",
        ),
        "Açıq olanda düzgün cavab ikiqat xal gətirir (sürət əmsalı saxlanılır). Bomba ilə birlikdə işləyir: "
        "düzgün → ×2, səhv → sıfırlanma. Oyun gedərkən də dəyişir.": t(
            "When on, a correct answer earns double points (the speed factor is kept). Works together with the "
            "bomb: correct → ×2, wrong → reset. Can be changed during the game.",
            "Когда включено, правильный ответ даёт двойные очки (коэффициент скорости сохраняется). Работает вместе "
            "с бомбой: верно → ×2, неверно → обнуление. Можно менять во время игры.",
            "Açıkken doğru cevap iki kat puan kazandırır (hız katsayısı korunur). Bomba ile birlikte çalışır: "
            "doğru → ×2, yanlış → sıfırlama. Oyun sırasında da değiştirilebilir.",
            "Wenn aktiv, bringt eine richtige Antwort doppelte Punkte (der Tempofaktor bleibt). Funktioniert mit der "
            "Bombe zusammen: richtig → ×2, falsch → Zurücksetzen. Auch während des Spiels änderbar.",
        ),
        "Final səhnəsində podium və tamaşaçı avatarları viral rəqslər və hər personajın özünəməxsus hərəkətini "
        "edir (telefonlarda da). Söndürüləndə avatarlar sakit dayanır.": t(
            "On the final stage the podium and audience avatars perform viral dances and each character's "
            "signature move (on phones too). When off, the avatars stand still.",
            "В финальной сцене аватары на подиуме и в зале исполняют вирусные танцы и фирменное движение каждого "
            "персонажа (и на телефонах). Когда выключено, аватары стоят спокойно.",
            "Final sahnesinde podyum ve seyirci avatarları viral danslar ve her karakterin kendine özgü hareketini "
            "yapar (telefonlarda da). Kapalıyken avatarlar sakin durur.",
            "Auf der Finalbühne tanzen Podiums- und Publikumsavatare virale Tänze und die charaktereigene Bewegung "
            "jeder Figur (auch auf den Handys). Ausgeschaltet stehen die Avatare ruhig.",
        ),
        "Bomba sualı": t("Bomb question", "Вопрос-бомба", "Bomba sorusu", "Bombenfrage"),
        "×2 xal": t("×2 points", "×2 очков", "×2 puan", "×2 Punkte"),
        "×2 xal!": t("×2 points!", "×2 очков!", "×2 puan!", "×2 Punkte!"),
        "Səhv cavab bu oyundakı xalı sıfırlayır": t(
            "A wrong answer resets the score in this game",
            "Неверный ответ обнуляет очки в этой игре",
            "Yanlış cevap bu oyundaki puanı sıfırlar",
            "Eine falsche Antwort setzt die Punkte in diesem Spiel zurück",
        ),
        "Düzgün cavab ikiqat xal gətirir": t(
            "A correct answer earns double points",
            "Правильный ответ даёт двойные очки",
            "Doğru cevap iki kat puan kazandırır",
            "Eine richtige Antwort bringt doppelte Punkte",
        ),
        "Bomba partladı!": t("The bomb exploded!", "Бомба взорвалась!", "Bomba patladı!", "Die Bombe ist explodiert!"),
        "{count} bomba partladı!": t(
            "{count} bombs exploded!",
            "Взорвалось бомб: {count}!",
            "{count} bomba patladı!",
            "{count} Bomben sind explodiert!",
        ),
        "cari suala tətbiq olundu": t(
            "applied to the current question",
            "применено к текущему вопросу",
            "mevcut soruya uygulandı",
            "auf die aktuelle Frage angewendet",
        ),
        "cari sualdan götürüldü": t(
            "removed from the current question",
            "снято с текущего вопроса",
            "mevcut sorudan kaldırıldı",
            "von der aktuellen Frage entfernt",
        ),
        "Bu suala artıq cavab var — dəyişiklik növbəti sualdan keçərlidir": t(
            "This question already has answers — the change applies from the next question",
            "На этот вопрос уже есть ответы — изменение действует со следующего вопроса",
            "Bu soruya zaten cevap var — değişiklik sonraki sorudan itibaren geçerli",
            "Zu dieser Frage gibt es schon Antworten — die Änderung gilt ab der nächsten Frage",
        ),
        "Növbəti sualdan keçərlidir": t(
            "Applies from the next question",
            "Действует со следующего вопроса",
            "Sonraki sorudan itibaren geçerli",
            "Gilt ab der nächsten Frage",
        ),
        "Rejimlər söndürülüb": t("Modes are off", "Режимы выключены", "Modlar kapalı", "Modi sind aus"),
        "Növbəti sualdan: {modes}": t(
            "From the next question: {modes}",
            "Со следующего вопроса: {modes}",
            "Sonraki sorudan: {modes}",
            "Ab der nächsten Frage: {modes}",
        ),
        "Cari sual: {modes}": t(
            "Current question: {modes}", "Текущий вопрос: {modes}", "Mevcut soru: {modes}", "Aktuelle Frage: {modes}"
        ),
        "Cari sual: rejim yoxdur": t(
            "Current question: no mode",
            "Текущий вопрос: без режима",
            "Mevcut soru: mod yok",
            "Aktuelle Frage: kein Modus",
        ),
        "açıq": t("on", "вкл", "açık", "an"),
        # 2026-11-10 (axşam): bir-sual semantikası — hər sual üçün ikona yenidən basılır.
        "Növbəti sual bomba olur: səhv cavab bu oyundakı xalı sıfırlayır. Hər sual üçün yenidən basılır.": t(
            "The next question becomes a bomb: a wrong answer resets the score in this game. Press again for each question.",
            "Следующий вопрос станет бомбой: неверный ответ обнуляет очки в этой игре. Нажимайте заново для каждого вопроса.",
            "Sonraki soru bomba olur: yanlış cevap bu oyundaki puanı sıfırlar. Her soru için yeniden basılır.",
            "Die nächste Frage wird zur Bombe: Eine falsche Antwort setzt die Punkte in diesem Spiel zurück. Für jede Frage erneut drücken.",
        ),
        "Növbəti sualda düzgün cavab ikiqat xal gətirir. Hər sual üçün yenidən basılır.": t(
            "In the next question a correct answer earns double points. Press again for each question.",
            "В следующем вопросе правильный ответ даёт двойные очки. Нажимайте заново для каждого вопроса.",
            "Sonraki soruda doğru cevap iki kat puan kazandırır. Her soru için yeniden basılır.",
            "In der nächsten Frage bringt eine richtige Antwort doppelte Punkte. Für jede Frage erneut drücken.",
        ),
        "Bir sual üçün aktivləşir: növbəti sual bomba sualı olur — səhv və ya qismən düzgün cavab oyunçunun bu "
        "oyundakı xalını sıfırlayır, cavabsız qalmaq partlatmır. Sual nəşr olunanda özü sönür — hər sual üçün "
        "səhnədəki ikona (və ya bu keçidə) yenidən basılır. Sual gedərkən basılsa və hələ cavab yoxdursa, elə "
        "həmin suala tətbiq olunur.": t(
            "Arms for one question: the next question becomes a bomb question — a wrong or partly correct answer "
            "resets the player's score in this game, not answering does not explode. It switches itself off when "
            "the question is published — press the stage icon (or this switch) again for every question. Pressed "
            "during a question with no answers yet, it applies to that very question.",
            "Включается на один вопрос: следующий вопрос становится вопросом-бомбой — неверный или частично верный "
            "ответ обнуляет очки игрока в этой игре, отсутствие ответа не взрывает. При публикации вопроса "
            "выключается само — нажимайте значок на сцене (или этот переключатель) заново для каждого вопроса. "
            "Если нажать во время вопроса, на который ещё никто не ответил, применится к этому же вопросу.",
            "Tek soru için etkinleşir: sonraki soru bomba sorusu olur — yanlış veya kısmen doğru cevap oyuncunun bu "
            "oyundaki puanını sıfırlar, cevapsız kalmak patlatmaz. Soru yayınlanınca kendiliğinden kapanır — her "
            "soru için sahnedeki simgeye (veya bu anahtara) yeniden basılır. Soru sırasında basılır ve henüz cevap "
            "yoksa, o soruya uygulanır.",
            "Gilt für eine Frage: Die nächste Frage wird zur Bombenfrage — eine falsche oder teilweise richtige "
            "Antwort setzt die Punkte des Spielers in diesem Spiel zurück, keine Antwort explodiert nicht. Beim "
            "Veröffentlichen der Frage schaltet es sich selbst aus — für jede Frage das Bühnensymbol (oder diesen "
            "Schalter) erneut drücken. Während einer Frage ohne Antworten gedrückt, gilt es für genau diese Frage.",
        ),
        "Bir sual üçün aktivləşir: növbəti sualda düzgün cavab ikiqat xal gətirir (sürət əmsalı saxlanılır), sonra "
        "özü sönür — hər sual üçün yenidən basılır. Bomba ilə birlikdə işləyir: düzgün → ×2, səhv → sıfırlanma.": t(
            "Arms for one question: in the next question a correct answer earns double points (the speed factor is "
            "kept), then it switches itself off — press again for every question. Works together with the bomb: "
            "correct → ×2, wrong → reset.",
            "Включается на один вопрос: в следующем вопросе правильный ответ даёт двойные очки (коэффициент скорости "
            "сохраняется), затем выключается само — нажимайте заново для каждого вопроса. Работает вместе с бомбой: "
            "верно → ×2, неверно → обнуление.",
            "Tek soru için etkinleşir: sonraki soruda doğru cevap iki kat puan kazandırır (hız katsayısı korunur), "
            "sonra kendiliğinden kapanır — her soru için yeniden basılır. Bomba ile birlikte çalışır: doğru → ×2, "
            "yanlış → sıfırlama.",
            "Gilt für eine Frage: In der nächsten Frage bringt eine richtige Antwort doppelte Punkte (der Tempofaktor "
            "bleibt), dann schaltet es sich selbst aus — für jede Frage erneut drücken. Funktioniert mit der Bombe "
            "zusammen: richtig → ×2, falsch → Zurücksetzen.",
        ),
        "Bu suala artıq cavab var — növbəti sual üçün aktivləşdi": t(
            "This question already has answers — armed for the next question",
            "На этот вопрос уже есть ответы — включено для следующего вопроса",
            "Bu soruya zaten cevap var — sonraki soru için etkinleştirildi",
            "Zu dieser Frage gibt es schon Antworten — für die nächste Frage aktiviert",
        ),
        "növbəti sual üçün aktivləşdi": t(
            "armed for the next question",
            "включено для следующего вопроса",
            "sonraki soru için etkinleştirildi",
            "für die nächste Frage aktiviert",
        ),
        "növbəti sual üçün söndürüldü": t(
            "switched off for the next question",
            "выключено для следующего вопроса",
            "sonraki soru için kapatıldı",
            "für die nächste Frage ausgeschaltet",
        ),
        "bu sualda": t("this question", "в этом вопросе", "bu soruda", "diese Frage"),
        "növbəti sual": t("next question", "следующий вопрос", "sonraki soru", "nächste Frage"),
        "Rejim seçilməyib — hər sual üçün ikona bas": t(
            "No mode selected — press an icon for each question",
            "Режим не выбран — нажимайте значок для каждого вопроса",
            "Mod seçilmedi — her soru için simgeye basın",
            "Kein Modus gewählt — für jede Frage ein Symbol drücken",
        ),
        "Növbəti sual: {modes}": t(
            "Next question: {modes}", "Следующий вопрос: {modes}", "Sonraki soru: {modes}", "Nächste Frage: {modes}"
        ),
        "bağlı": t("off", "выкл", "kapalı", "aus"),
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
