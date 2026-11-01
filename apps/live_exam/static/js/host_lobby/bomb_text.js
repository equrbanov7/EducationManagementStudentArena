const TEXT = {
    az: {
        title: "Bomba sualları", label: "Bomba sualı", saved: "Yadda saxlanıldı", error: "Yadda saxlanılmadı. Yenidən yoxlayın.",
        rule: "💣 Bomba sualı: səhv və ya qismən düzgün cavab bu oyundakı xalını sıfırlayır.",
        help: "Səhv və ya qismən düzgün cavab yalnız bu canlı oyundakı xalın hamısını sıfırlayır. Cavabsız qalmaq bomba partlatmır. Oyundan əvvəl seçilir.",
        result: "Bomba partladı — bu oyundakı xalın sıfırlandı.",
    },
    en: {
        title: "Bomb questions", label: "Bomb question", saved: "Saved", error: "Could not save. Please try again.",
        rule: "💣 Bomb question: a wrong or partly correct answer resets your score in this game.",
        help: "A wrong or partly correct answer resets only this live game's score. An unanswered question does not explode. Select before starting.",
        result: "The bomb exploded — your score in this game was reset.",
    },
    ru: {
        title: "Вопросы-бомбы", label: "Вопрос-бомба", saved: "Сохранено", error: "Не удалось сохранить. Повторите попытку.",
        rule: "💣 Вопрос-бомба: неверный или частично верный ответ обнуляет очки в этой игре.",
        help: "Неверный или частично верный ответ обнуляет очки только этой игры. Без ответа бомба не взрывается. Выберите до начала.",
        result: "Бомба взорвалась — очки в этой игре обнулены.",
    },
    tr: {
        title: "Bomba soruları", label: "Bomba sorusu", saved: "Kaydedildi", error: "Kaydedilemedi. Tekrar deneyin.",
        rule: "💣 Bomba sorusu: yanlış veya kısmen doğru yanıt bu oyundaki puanını sıfırlar.",
        help: "Yanlış veya kısmen doğru yanıt yalnızca bu canlı oyunun puanını sıfırlar. Yanıtsız soru patlamaz. Başlamadan önce seçilir.",
        result: "Bomba patladı — bu oyundaki puanın sıfırlandı.",
    },
    de: {
        title: "Bombenfragen", label: "Bombenfrage", saved: "Gespeichert", error: "Speichern fehlgeschlagen. Bitte erneut versuchen.",
        rule: "💣 Bombenfrage: Eine falsche oder teilweise richtige Antwort setzt deine Punkte in diesem Spiel zurück.",
        help: "Eine falsche oder teilweise richtige Antwort setzt nur die Punkte dieses Live-Spiels zurück. Ohne Antwort explodiert nichts. Vor dem Start auswählen.",
        result: "Die Bombe ist explodiert — deine Punkte in diesem Spiel wurden zurückgesetzt.",
    },
};
export function bombText(language) { return TEXT[String(language || "az").toLowerCase().split("-")[0]] || TEXT.az; }
