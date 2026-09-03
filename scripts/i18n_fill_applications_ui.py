#!/usr/bin/env python3
"""EMSArena i18n — «Müraciətlərim» KABİNET PANELİNİN sətirləri (4 dil). İdempotent.

`scripts/i18n_fill_applications.py` modelin/domenin sətirlərini doldurur; bu
skript isə UI qatını: şablon (`_applications*.html`), JS mətn kataloqu
(`_sections/applications_i18n.py`), kontekst zolağı və sidebar bəndi.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
ƏLAVƏ edir və mövcud girişə TOXUNMUR. Yer tutucular (`{n}`, `{unit}`, …)
tərcümədə də EYNİ qalmalıdır (qapı bunu yoxlayır).

İstifadə:  python scripts/i18n_fill_applications_ui.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

# ── Kontekst: "applications" — panelin bütün görünən mətnləri ────────────────
_UI = {
    "Müraciətlər": {"en": "Applications", "ru": "Обращения", "tr": "Başvurular"},
    "Müraciətlərim": {"en": "My applications", "ru": "Мои обращения", "tr": "Başvurularım"},
    "Yeni müraciət": {"en": "New application", "ru": "Новое обращение", "tr": "Yeni başvuru"},
    "Arxiv": {"en": "Archive", "ru": "Архив", "tr": "Arşiv"},
    "Mənə gələnlər": {"en": "Incoming", "ru": "Входящие", "tr": "Bana gelenler"},
    "İzlədiklərim": {"en": "Watching", "ru": "Отслеживаю", "tr": "Takip ettiklerim"},
    "Açıq olanlar": {"en": "Open", "ru": "Открытые", "tr": "Açık olanlar"},
    "Müddəti keçən": {"en": "Overdue", "ru": "Просроченные", "tr": "Süresi geçenler"},
    "Bağlananlar": {"en": "Closed", "ru": "Закрытые", "tr": "Kapananlar"},
    "Hamısı": {"en": "All", "ru": "Все", "tr": "Tümü"},
    "Bütün növlər": {"en": "All kinds", "ru": "Все типы", "tr": "Tüm türler"},
    "Sıfırla": {"en": "Reset", "ru": "Сбросить", "tr": "Temizle"},
    "Müraciət axtar": {"en": "Search applications", "ru": "Поиск обращений", "tr": "Başvuru ara"},
    "Mövzu, nömrə və ya göndərən axtar": {
        "en": "Search by subject, number or sender",
        "ru": "Поиск по теме, номеру или отправителю",
        "tr": "Konu, numara veya gönderene göre ara",
    },
    "Müraciətin detalı": {"en": "Application detail", "ru": "Детали обращения", "tr": "Başvuru ayrıntısı"},
    "Müraciətin növü": {"en": "Application kind", "ru": "Тип обращения", "tr": "Başvuru türü"},
    "Müraciətin mətni": {"en": "Application text", "ru": "Текст обращения", "tr": "Başvuru metni"},
    "Müraciətin gedişi": {"en": "Application history", "ru": "Ход обращения", "tr": "Başvurunun seyri"},
    "Əlavə olunan sənədlər": {"en": "Attached documents", "ru": "Приложенные документы", "tr": "Eklenen belgeler"},
    "Mövzu": {"en": "Subject", "ru": "Тема", "tr": "Konu"},
    "Qeyd": {"en": "Note", "ru": "Заметка", "tr": "Not"},
    "Sənəd əlavə et": {"en": "Attach a document", "ru": "Приложить документ", "tr": "Belge ekle"},
    "Ləğv et": {"en": "Cancel", "ru": "Отмена", "tr": "Vazgeç"},
    "Bağla": {"en": "Close", "ru": "Закрыть", "tr": "Kapat"},
    "Təsdiqlə": {"en": "Confirm", "ru": "Подтвердить", "tr": "Onayla"},
    "Göndər": {"en": "Send", "ru": "Отправить", "tr": "Gönder"},
    "Yönləndir": {"en": "Forward", "ru": "Перенаправить", "tr": "Yönlendir"},
    "Təyin et": {"en": "Assign", "ru": "Назначить", "tr": "Ata"},
    "Rədd et": {"en": "Reject", "ru": "Отклонить", "tr": "Reddet"},
    "Daha çox": {"en": "Load more", "ru": "Показать ещё", "tr": "Daha fazla"},
    "Yüklənir…": {"en": "Loading…", "ru": "Загрузка…", "tr": "Yükleniyor…"},
    "gün": {"en": "days", "ru": "дн.", "tr": "gün"},
    "bağlanıb": {"en": "closed", "ru": "закрыто", "tr": "kapatıldı"},
    "daxili qeyd": {"en": "internal note", "ru": "внутренняя заметка", "tr": "iç not"},
    "cavab müddəti keçir": {
        "en": "response time is running out",
        "ru": "срок ответа истекает",
        "tr": "yanıt süresi geçiyor",
    },
}

_KPI = {
    "Açıq müraciətim": {"en": "My open applications", "ru": "Мои открытые обращения", "tr": "Açık başvurum"},
    "Məlumat gözlənilir": {"en": "Information awaited", "ru": "Ожидается информация", "tr": "Bilgi bekleniyor"},
    "Cavablanıb": {"en": "Answered", "ru": "Отвечено", "tr": "Yanıtlandı"},
    "Orta cavab müddəti": {"en": "Average response time", "ru": "Среднее время ответа", "tr": "Ortalama yanıt süresi"},
    "Mənə gələn açıq": {"en": "Open in my inbox", "ru": "Открытые входящие", "tr": "Bana gelen açık"},
    "Yeni — baxılmayıb": {"en": "New — not reviewed", "ru": "Новые — не просмотрены", "tr": "Yeni — incelenmedi"},
    "Cavab müddəti keçən": {"en": "Overdue for response", "ru": "Просрочен ответ", "tr": "Yanıt süresi geçen"},
    "İzlədiyim": {"en": "Watched by me", "ru": "Отслеживаемые мной", "tr": "Takip ettiğim"},
    "cavab gözləyir": {"en": "awaiting a response", "ru": "ожидают ответа", "tr": "yanıt bekliyor"},
    "sizdən sənəd istənilib": {
        "en": "a document was requested from you",
        "ru": "у вас запросили документ",
        "tr": "sizden belge istendi",
    },
    "bağlanmış müraciət": {"en": "closed applications", "ru": "закрытые обращения", "tr": "kapatılmış başvuru"},
    "son 30 gün üzrə": {"en": "over the last 30 days", "ru": "за последние 30 дней", "tr": "son 30 gün için"},
    "cavab verilməlidir": {"en": "a response is required", "ru": "требуется ответ", "tr": "yanıt verilmeli"},
    "ilk baxış gözlənilir": {
        "en": "first review pending",
        "ru": "ожидается первый просмотр",
        "tr": "ilk inceleme bekleniyor",
    },
    "hamısına baxılıb": {"en": "everything reviewed", "ru": "все просмотрены", "tr": "tümü incelendi"},
    "təcili baxılmalıdır": {"en": "needs urgent attention", "ru": "требуется срочно", "tr": "acilen incelenmeli"},
    "gecikən yoxdur": {"en": "nothing overdue", "ru": "просроченных нет", "tr": "geciken yok"},
    "yönləndirdiyim müraciətlər": {
        "en": "applications I forwarded",
        "ru": "перенаправленные мной обращения",
        "tr": "yönlendirdiğim başvurular",
    },
}

_LONG = {
    "Transkript, arayış, qiymətə etiraz, şikayət — hamısı buradan göndərilir. Göndərdikdən sonra "
    "müraciətin harada olduğunu, kimin baxdığını və cavabı burada görürsən.": {
        "en": "Transcript, certificate, grade appeal, complaint — all of them are submitted here. "
        "After submitting you can see where the application is, who is handling it and the answer.",
        "ru": "Транскрипт, справка, апелляция на оценку, жалоба — всё отправляется отсюда. После "
        "отправки вы видите, где обращение, кто его рассматривает и каков ответ.",
        "tr": "Transkript, belge, not itirazı, şikâyet — hepsi buradan gönderilir. Gönderdikten sonra "
        "başvurunun nerede olduğunu, kimin baktığını ve yanıtı burada görürsünüz.",
    },
    "Şöbənizə gələn müraciətlər. Cavab verə, əlavə məlumat istəyə və ya səlahiyyətinizdə olmayan "
    "məsələni başqa şöbəyə yönləndirə bilərsiniz — yönləndirdikdən sonra da izləməkdə davam edirsiniz.": {
        "en": "Applications addressed to your unit. You can answer, request more information or forward "
        "a matter outside your remit to another unit — you keep watching it after forwarding.",
        "ru": "Обращения, поступившие в ваше подразделение. Вы можете ответить, запросить сведения или "
        "перенаправить вопрос вне вашей компетенции — после перенаправления вы продолжаете наблюдение.",
        "tr": "Biriminize gelen başvurular. Yanıtlayabilir, ek bilgi isteyebilir ya da yetkiniz dışındaki "
        "konuyu başka birime yönlendirebilirsiniz — yönlendirdikten sonra da izlemeye devam edersiniz.",
    },
    "Növü seçin — sistem müraciəti avtomatik aidiyyəti şöbəyə göndərəcək.": {
        "en": "Pick a kind — the system routes the application to the responsible unit automatically.",
        "ru": "Выберите тип — система автоматически направит обращение в ответственное подразделение.",
        "tr": "Türü seçin — sistem başvuruyu otomatik olarak ilgili birime gönderecek.",
    },
    "Növü seçəndə müraciətin hansı şöbəyə gedəcəyi burada görünəcək.": {
        "en": "Once you pick a kind, the destination unit appears here.",
        "ru": "Когда вы выберете тип, здесь появится подразделение-получатель.",
        "tr": "Türü seçtiğinizde başvurunun gideceği birim burada görünecek.",
    },
    "Bir cümlə ilə nə istədiyiniz": {
        "en": "What you need, in one sentence",
        "ru": "Чего вы хотите, одним предложением",
        "tr": "Ne istediğiniz, tek cümleyle",
    },
    "Konkret tarix, fənn və qrup adı yazsanız cavab daha tez gələcək.": {
        "en": "Give the exact date, subject and group name and the answer will come faster.",
        "ru": "Укажите точную дату, предмет и название группы — ответ придёт быстрее.",
        "tr": "Kesin tarih, ders ve grup adını yazarsanız yanıt daha hızlı gelir.",
    },
    "Fayl seç — PDF, JPG və ya DOCX, maks. 10 MB": {
        "en": "Choose a file — PDF, JPG or DOCX, max. 10 MB",
        "ru": "Выберите файл — PDF, JPG или DOCX, макс. 10 МБ",
        "tr": "Dosya seç — PDF, JPG veya DOCX, en fazla 10 MB",
    },
    "Müraciəti göndər": {"en": "Submit the application", "ru": "Отправить обращение", "tr": "Başvuruyu gönder"},
    "Müraciəti yönləndir": {
        "en": "Forward the application",
        "ru": "Перенаправить обращение",
        "tr": "Başvuruyu yönlendir",
    },
    "Hansı şöbəyə?": {"en": "To which unit?", "ru": "В какое подразделение?", "tr": "Hangi birime?"},
    "Yönləndirmə qeydi": {"en": "Forwarding note", "ru": "Примечание к перенаправлению", "tr": "Yönlendirme notu"},
    "Niyə bu şöbəyə göndərilir və nə gözlənilir": {
        "en": "Why it goes to this unit and what is expected",
        "ru": "Почему направляется в это подразделение и что ожидается",
        "tr": "Neden bu birime gönderiliyor ve ne bekleniyor",
    },
    "Müraciəti izləməkdə davam edim — cavab veriləndə mənə də bildiriş gəlsin.": {
        "en": "Keep watching the application — notify me too when it is answered.",
        "ru": "Продолжать наблюдение — уведомить меня, когда будет дан ответ.",
        "tr": "Başvuruyu izlemeye devam edeyim — yanıtlandığında bana da bildirim gelsin.",
    },
    "Müraciət sahibi yönləndirməni öz panelində görəcək — müraciət itmir, sadəcə məsul şöbə dəyişir.": {
        "en": "The applicant sees the forwarding in their own panel — nothing is lost, only the responsible unit changes.",
        "ru": "Заявитель увидит перенаправление в своей панели — обращение не теряется, меняется лишь ответственное подразделение.",
        "tr": "Başvuru sahibi yönlendirmeyi kendi panelinde görecek — başvuru kaybolmaz, yalnızca sorumlu birim değişir.",
    },
    "Məsul şəxsə təyin et": {
        "en": "Assign to a responsible person",
        "ru": "Назначить ответственного",
        "tr": "Sorumlu kişiye ata",
    },
    "Məsul şəxs": {"en": "Responsible person", "ru": "Ответственный", "tr": "Sorumlu kişi"},
    "Məsul şəxs üçün qısa izah": {
        "en": "A short note for the responsible person",
        "ru": "Краткое пояснение для ответственного",
        "tr": "Sorumlu kişi için kısa açıklama",
    },
    "Müraciətlər paneli üçün aktiv təşkilat konteksti tapılmadı.": {
        "en": "No active organization context was found for the applications panel.",
        "ru": "Для панели обращений не найден активный контекст организации.",
        "tr": "Başvurular paneli için etkin kurum bağlamı bulunamadı.",
    },
}

_JS = {
    "Cavab ver": {"en": "Reply", "ru": "Ответить", "tr": "Yanıtla"},
    "Müraciət sahibinin görəcəyi cavab": {
        "en": "The answer the applicant will see",
        "ru": "Ответ, который увидит заявитель",
        "tr": "Başvuru sahibinin göreceği yanıt",
    },
    "Cavab mətni ən azı 10 simvol olmalıdır — müraciət sahibi məhz bu mətni görəcək.": {
        "en": "The reply must be at least 10 characters — the applicant sees exactly this text.",
        "ru": "Ответ должен содержать не менее 10 символов — заявитель увидит именно этот текст.",
        "tr": "Yanıt metni en az 10 karakter olmalı — başvuru sahibi tam olarak bu metni görecek.",
    },
    "Həll olundu — bağla": {"en": "Resolved — close", "ru": "Решено — закрыть", "tr": "Çözüldü — kapat"},
    "Əlavə məlumat istə": {"en": "Request more information", "ru": "Запросить сведения", "tr": "Ek bilgi iste"},
    "Əlavə məlumat göndər": {"en": "Send the information", "ru": "Отправить сведения", "tr": "Ek bilgi gönder"},
    "Başqa şöbəyə yönləndir": {
        "en": "Forward to another unit",
        "ru": "Перенаправить в другое подразделение",
        "tr": "Başka birime yönlendir",
    },
    "Düzəliş üçün qaytar": {"en": "Return for correction", "ru": "Вернуть на доработку", "tr": "Düzeltme için iade et"},
    "Düzəlişdən sonra yenidən göndər": {
        "en": "Resubmit after correction",
        "ru": "Отправить повторно после доработки",
        "tr": "Düzeltmeden sonra yeniden gönder",
    },
    "Qeyd əlavə et": {"en": "Add a note", "ru": "Добавить заметку", "tr": "Not ekle"},
    "Təsdiqləyirəm — bağla": {"en": "I confirm — close", "ru": "Подтверждаю — закрыть", "tr": "Onaylıyorum — kapat"},
    "Müraciəti ləğv et": {"en": "Cancel the application", "ru": "Отменить обращение", "tr": "Başvuruyu iptal et"},
    "Nə düzəldilməlidir?": {"en": "What has to be corrected?", "ru": "Что нужно исправить?", "tr": "Ne düzeltilmeli?"},
    "Ləğv səbəbi": {"en": "Reason for cancelling", "ru": "Причина отмены", "tr": "İptal nedeni"},
    "İstənilən məlumat": {"en": "The requested information", "ru": "Запрошенные сведения", "tr": "İstenen bilgi"},
    "Müraciəti bağlayaq?": {
        "en": "Close the application?",
        "ru": "Закрыть обращение?",
        "tr": "Başvuruyu kapatalım mı?",
    },
    "Cavabı təsdiqləyirsiniz və müraciət bağlanır. Bu əməl geri qaytarılmır.": {
        "en": "You confirm the answer and the application is closed. This cannot be undone.",
        "ru": "Вы подтверждаете ответ, и обращение закрывается. Это действие необратимо.",
        "tr": "Yanıtı onaylıyorsunuz ve başvuru kapanıyor. Bu işlem geri alınamaz.",
    },
    "Müraciət tapılmadı": {"en": "No application found", "ru": "Обращения не найдены", "tr": "Başvuru bulunamadı"},
    "Müddəti keçən müraciət yoxdur": {
        "en": "No overdue applications",
        "ru": "Просроченных обращений нет",
        "tr": "Süresi geçen başvuru yok",
    },
    "İzlədiyiniz müraciət yoxdur": {
        "en": "You are not watching any application",
        "ru": "Вы ничего не отслеживаете",
        "tr": "İzlediğiniz başvuru yok",
    },
    "Başqa şöbəyə yönləndirdiyiniz müraciətlər burada görünəcək.": {
        "en": "Applications you forwarded to another unit appear here.",
        "ru": "Здесь появятся обращения, перенаправленные вами в другое подразделение.",
        "tr": "Başka birime yönlendirdiğiniz başvurular burada görünecek.",
    },
    "Hələ müraciət göndərməmisiniz. «Yeni müraciət» düyməsi ilə başlaya bilərsiniz.": {
        "en": "You have not submitted an application yet. Start with the “New application” button.",
        "ru": "Вы ещё не отправляли обращений. Начните с кнопки «Новое обращение».",
        "tr": "Henüz başvuru göndermediniz. “Yeni başvuru” düğmesiyle başlayabilirsiniz.",
    },
    "Bu filtrə uyğun müraciət yoxdur — filtri dəyişin.": {
        "en": "No application matches this filter — change the filter.",
        "ru": "Под этот фильтр обращений нет — измените фильтр.",
        "tr": "Bu filtreye uyan başvuru yok — filtreyi değiştirin.",
    },
    "Müraciət bağlanıb — yalnız oxuna bilər.": {
        "en": "The application is closed — read-only.",
        "ru": "Обращение закрыто — только чтение.",
        "tr": "Başvuru kapatıldı — yalnızca okunabilir.",
    },
    "Müraciət bağlanıb. Razı deyilsinizsə, eyni mövzuda yeni müraciət göndərə bilərsiniz.": {
        "en": "The application is closed. If you disagree, you can submit a new one on the same topic.",
        "ru": "Обращение закрыто. Если вы не согласны, отправьте новое обращение по той же теме.",
        "tr": "Başvuru kapatıldı. Katılmıyorsanız aynı konuda yeni başvuru gönderebilirsiniz.",
    },
    "Bu şöbədə təyin ediləcək istifadəçi tapılmadı.": {
        "en": "No user to assign was found in this unit.",
        "ru": "В этом подразделении не найден пользователь для назначения.",
        "tr": "Bu birimde atanacak kullanıcı bulunamadı.",
    },
    "Bir əməldə ən çoxu 5 fayl əlavə edilə bilər.": {
        "en": "At most 5 files can be attached per action.",
        "ru": "За одно действие можно приложить не более 5 файлов.",
        "tr": "Bir işlemde en fazla 5 dosya eklenebilir.",
    },
    "Siyahı yüklənmədi, yenidən cəhd edin.": {
        "en": "The list could not be loaded, try again.",
        "ru": "Список не загрузился, попробуйте ещё раз.",
        "tr": "Liste yüklenemedi, tekrar deneyin.",
    },
    "Əməliyyat yerinə yetirilmədi.": {
        "en": "The operation could not be completed.",
        "ru": "Операция не выполнена.",
        "tr": "İşlem gerçekleştirilemedi.",
    },
}

# Yer tutuculu sətirlər — `{n}` / `{m}` / `{unit}` … tərcümədə EYNİ qalır.
_PLACEHOLDERS = {
    "{n} iş günü": {"en": "{n} working days", "ru": "{n} раб. дн.", "tr": "{n} iş günü"},
    "{n} iş günü müddət": {"en": "{n} working days allowed", "ru": "срок {n} раб. дн.", "tr": "{n} iş günü süre"},
    "{n} simvol": {"en": "{n} characters", "ru": "{n} символов", "tr": "{n} karakter"},
    "Ən azı {min} simvol — hazırda {n}": {
        "en": "At least {min} characters — currently {n}",
        "ru": "Не менее {min} символов — сейчас {n}",
        "tr": "En az {min} karakter — şu anda {n}",
    },
    "Cavab müddətinə {n} iş günü qalıb (norma {m} iş günü)": {
        "en": "{n} working days left to respond (norm {m} working days)",
        "ru": "До ответа осталось {n} раб. дн. (норма {m} раб. дн.)",
        "tr": "Yanıt süresine {n} iş günü kaldı (norm {m} iş günü)",
    },
    "Cavab müddəti {n} gün keçib (norma {m} iş günü)": {
        "en": "The response is {n} days overdue (norm {m} working days)",
        "ru": "Срок ответа просрочен на {n} дн. (норма {m} раб. дн.)",
        "tr": "Yanıt süresi {n} gün geçti (norm {m} iş günü)",
    },
    "Müraciət bağlanıb — {status}": {
        "en": "The application is closed — {status}",
        "ru": "Обращение закрыто — {status}",
        "tr": "Başvuru kapatıldı — {status}",
    },
    "Müraciətiniz hazırda {unit}-dədir. Cavab veriləndə bildiriş gələcək və mətn burada görünəcək.": {
        "en": "Your application is currently at {unit}. You will be notified when it is answered and the text will appear here.",
        "ru": "Ваше обращение сейчас в {unit}. Вы получите уведомление, когда будет дан ответ, и текст появится здесь.",
        "tr": "Başvurunuz şu anda {unit} biriminde. Yanıtlandığında bildirim gelecek ve metin burada görünecek.",
    },
    "Müraciət hazırda {unit}-dədir. Siz yönləndirdiyiniz üçün gedişini izləyirsiniz, amma cavabı həmin şöbə verəcək.": {
        "en": "The application is currently at {unit}. You watch it because you forwarded it, but that unit answers.",
        "ru": "Обращение сейчас в {unit}. Вы наблюдаете за ним как отправитель перенаправления, но отвечает это подразделение.",
        "tr": "Başvuru şu anda {unit} biriminde. Yönlendiren siz olduğunuz için izliyorsunuz, ancak yanıtı o birim verecek.",
    },
    "Müraciət {unit}-nə göndərildi — gedişini buradan izləyə bilərsiniz.": {
        "en": "The application was sent to {unit} — you can follow it from here.",
        "ru": "Обращение отправлено в {unit} — вы можете следить за ним отсюда.",
        "tr": "Başvuru {unit} birimine gönderildi — buradan takip edebilirsiniz.",
    },
    "{no} — {unit}-nə yönləndirildi · izləməkdə davam edirsiniz.": {
        "en": "{no} — forwarded to {unit} · you keep watching it.",
        "ru": "{no} — перенаправлено в {unit} · вы продолжаете наблюдение.",
        "tr": "{no} — {unit} birimine yönlendirildi · izlemeye devam ediyorsunuz.",
    },
    "{no} — {unit}-nə yönləndirildi.": {
        "en": "{no} — forwarded to {unit}.",
        "ru": "{no} — перенаправлено в {unit}.",
        "tr": "{no} — {unit} birimine yönlendirildi.",
    },
    "{no} — {status}. Müraciət sahibinə bildiriş göndərildi.": {
        "en": "{no} — {status}. The applicant has been notified.",
        "ru": "{no} — {status}. Заявителю отправлено уведомление.",
        "tr": "{no} — {status}. Başvuru sahibine bildirim gönderildi.",
    },
    "{no} — yeniləndi.": {"en": "{no} — updated.", "ru": "{no} — обновлено.", "tr": "{no} — güncellendi."},
    "«{name}» 10 MB-dan böyükdür.": {
        "en": "“{name}” is larger than 10 MB.",
        "ru": "«{name}» больше 10 МБ.",
        "tr": "“{name}” 10 MB’den büyük.",
    },
    "«{name}» dəstəklənmir — PDF, JPG, PNG və ya DOCX olmalıdır.": {
        "en": "“{name}” is not supported — it must be PDF, JPG, PNG or DOCX.",
        "ru": "«{name}» не поддерживается — нужен PDF, JPG, PNG или DOCX.",
        "tr": "“{name}” desteklenmiyor — PDF, JPG, PNG veya DOCX olmalı.",
    },
}

# ── Kontekst: "accounts.applications" — kontekst zolağı ─────────────────────
_CONTEXT_BAR = {
    "Tələbə kabineti": {"en": "Student cabinet", "ru": "Кабинет студента", "tr": "Öğrenci kabini"},
    "Müəllim kabineti": {"en": "Teacher cabinet", "ru": "Кабинет преподавателя", "tr": "Öğretmen kabini"},
    "Əməkdaş kabineti": {"en": "Staff cabinet", "ru": "Кабинет сотрудника", "tr": "Personel kabini"},
    "Kabinet": {"en": "Cabinet", "ru": "Кабинет", "tr": "Kabin"},
    "Şöbə": {"en": "Unit", "ru": "Подразделение", "tr": "Birim"},
    "şöbəyə gələn müraciətlər": {
        "en": "applications addressed to the unit",
        "ru": "обращения, поступившие в подразделение",
        "tr": "birime gelen başvurular",
    },
    "öz müraciətlərim": {"en": "my own applications", "ru": "мои собственные обращения", "tr": "kendi başvurularım"},
}

# ── Kontekst: "profile.sidebar" — menyu bəndi ───────────────────────────────
_SIDEBAR = {
    "Müraciətlərim": {"en": "My applications", "ru": "Мои обращения", "tr": "Başvurularım"},
}

ENTRIES = {
    "applications": {**_UI, **_KPI, **_LONG, **_JS, **_PLACEHOLDERS},
    "accounts.applications": _CONTEXT_BAR,
    "profile.sidebar": _SIDEBAR,
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n'
            if probe in text:
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
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
