#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-08: sillabusun TƏKRAR İSTİFADƏSİ (bağla / kopyala / hamısına tətbiq et).

Yeni mətnlər: «Bu fənnin bu semestr üçün artıq sillabusu var» dialoqu və redaktor
banneri, «Eyni sillabusu istifadə et (bağla)», «Kopyala və uyğunlaşdır», «Hamısına
tətbiq et», «Ayır», «Mənbədən yenilə», «Bağlı sillabuslara tətbiq et», səbəb kodlarının
(`reuse.*`) mətnləri, «Təsdiq: <qrup> sillabusundan (eyni məzmun, eyni saatlar)»
damğası və model seçimləri (`ApprovalSource.REUSE`, `ChangeKind.REUSED`).

Kontekstlər: `accounts.syllabus`, `syllabus.document`, `syllabus.model`.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları `msgfmt` ilə yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_08_syllabus_reuse.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

#: Bu kontekstlərdə mövcud (boş olmayan) tərcümə də yenilənir.
FORCE = ()

# (kontekst, az) → (en, ru, tr)
ROWS = {
    "syllabus.model": {
        "Bağlı sillabusdan (eyni məzmun)": (
            "From a linked syllabus (same content)",
            "Из связанного силлабуса (то же содержание)",
            "Bağlı izlenceden (aynı içerik)",
        ),
        "Başqa qrupun sillabusuna bağlanıb": (
            "Linked to another group's syllabus",
            "Связан с силлабусом другой группы",
            "Başka bir grubun izlencesine bağlandı",
        ),
    },
    "syllabus.document": {
        "Təsdiq: %(group)s sillabusundan (eyni məzmun, eyni saatlar)": (
            "Approval: from the %(group)s syllabus (same content, same hours)",
            "Утверждение: из силлабуса группы %(group)s (то же содержание, те же часы)",
            "Onay: %(group)s izlencesinden (aynı içerik, aynı saatler)",
        ),
        "Təsdiq: bağlı sillabusdan (eyni məzmun, eyni saatlar)": (
            "Approval: from a linked syllabus (same content, same hours)",
            "Утверждение: из связанного силлабуса (то же содержание, те же часы)",
            "Onay: bağlı izlenceden (aynı içerik, aynı saatler)",
        ),
    },
    "accounts.syllabus": {
        "%(count)s bağlı sillabus hələ köhnə versiyadadır. Yeni versiya təsdiqlənəndə onlar özbaşına dəyişmir — "
        "«Bağlı sillabuslara tətbiq et» ilə yeniləyin.": (
            "%(count)s linked syllabi are still on an older version. They do not change on their own when a new "
            "version is approved — update them with “Apply to linked syllabi”.",
            "%(count)s связанных силлабусов ещё на старой версии. При утверждении новой версии они не меняются "
            "сами — обновите их кнопкой «Применить к связанным силлабусам».",
            "%(count)s bağlı izlence hâlâ eski sürümde. Yeni sürüm onaylandığında kendiliğinden değişmez — "
            "“Bağlı izlencelere uygula” ile güncelleyin.",
        ),
        "%(count)s bağlı sillabus köhnə versiyadadır": (
            "%(count)s linked syllabi are on an older version",
            "Связанных силлабусов на старой версии: %(count)s",
            "%(count)s bağlı izlence eski sürümde",
        ),
        "%(count)s qrup bu sillabusa bağlıdır": (
            "%(count)s groups are linked to this syllabus",
            "Групп, связанных с этим силлабусом: %(count)s",
            "%(count)s grup bu izlenceye bağlı",
        ),
        "Ayır": ("Unlink", "Отвязать", "Bağı kaldır"),
        "Ayır və qaralama aç": ("Unlink and open a draft", "Отвязать и открыть черновик", "Bağı kaldır ve taslak aç"),
        "Bağ ayrıldı — redaktə üçün müstəqil qaralama açıldı. Təsdiqlənmiş nüsxə qüvvədə qalır.": (
            "Unlinked — an independent draft is open for editing. The approved copy stays in force.",
            "Связь снята — открыт независимый черновик для редактирования. Утверждённая копия остаётся в силе.",
            "Bağ kaldırıldı — düzenleme için bağımsız bir taslak açıldı. Onaylı kopya yürürlükte kalır.",
        ),
        "Bağ ayrılsın?": ("Unlink this syllabus?", "Снять связь?", "Bağ kaldırılsın mı?"),
        "Bağlamaq yalnız öz sillabusunuza mümkündür — başqasının sillabusunu kopyalaya bilərsiniz.": (
            "You can only link to your own syllabus — you can copy someone else's.",
            "Связать можно только со своим силлабусом — чужой можно скопировать.",
            "Yalnızca kendi izlencenize bağlanabilirsiniz — başkasının izlencesini kopyalayabilirsiniz.",
        ),
        "Bağlandı: %(linked)s · kopyalandı: %(copied)s · ötürüldü: %(skipped)s.": (
            "Linked: %(linked)s · copied: %(copied)s · skipped: %(skipped)s.",
            "Связано: %(linked)s · скопировано: %(copied)s · пропущено: %(skipped)s.",
            "Bağlandı: %(linked)s · kopyalandı: %(copied)s · atlandı: %(skipped)s.",
        ),
        "Bağlı qruplar bu sillabusun son təsdiqlənmiş versiyasını görür. Yeni versiya təsdiqlənəndə onlar özbaşına "
        "dəyişmir — tətbiq etmək sizin qərarınızdır.": (
            "Linked groups see the latest approved version of this syllabus. They do not change on their own when a "
            "new version is approved — applying it is your decision.",
            "Связанные группы видят последнюю утверждённую версию этого силлабуса. При утверждении новой версии они "
            "не меняются сами — применять её решаете вы.",
            "Bağlı gruplar bu izlencenin son onaylı sürümünü görür. Yeni sürüm onaylandığında kendiliğinden "
            "değişmez — uygulamak sizin kararınızdır.",
        ),
        "Bağlı sillabus artıq mənbənin son təsdiqlənmiş versiyasındadır.": (
            "The linked syllabus is already on the source's latest approved version.",
            "Связанный силлабус уже соответствует последней утверждённой версии источника.",
            "Bağlı izlence zaten kaynağın son onaylı sürümünde.",
        ),
        "Bağlı sillabuslara tətbiq edilsin?": (
            "Apply to linked syllabi?",
            "Применить к связанным силлабусам?",
            "Bağlı izlencelere uygulansın mı?",
        ),
        "Bağlı sillabuslara tətbiq et": (
            "Apply to linked syllabi",
            "Применить к связанным силлабусам",
            "Bağlı izlencelere uygula",
        ),
        "Bağlıdır: %(group)s sillabusu": (
            "Linked: %(group)s syllabus",
            "Связан: силлабус группы %(group)s",
            "Bağlı: %(group)s izlencesi",
        ),
        "Boş qaralama yarat": ("Create a blank draft", "Создать пустой черновик", "Boş taslak oluştur"),
        "Bu fənn üzrə digər qruplarınız": (
            "Your other groups for this subject",
            "Другие ваши группы по этой дисциплине",
            "Bu ders için diğer gruplarınız",
        ),
        "Bu fənnin bu semestr üçün artıq sillabusu var": (
            "This subject already has a syllabus for this semester",
            "У этой дисциплины уже есть силлабус на этот семестр",
            "Bu dersin bu dönem için zaten bir izlencesi var",
        ),
        "Bu fənnin bu semestr üçün artıq sillabusu var — bağlaya və ya kopyalaya bilərsiniz": (
            "This subject already has a syllabus for this semester — you can link or copy it",
            "У этой дисциплины уже есть силлабус на этот семестр — его можно связать или скопировать",
            "Bu dersin bu dönem için zaten bir izlencesi var — bağlayabilir veya kopyalayabilirsiniz",
        ),
        "Bu qrupun mövcud qaralamasının məzmunu mənbənin məzmunu ilə əvəzlənəcək (əvvəlki mətn audit izində "
        "saxlanılır).": (
            "This group's current draft will be replaced with the source content (the previous text is kept in "
            "the audit trail).",
            "Содержимое текущего черновика этой группы будет заменено содержимым источника (прежний текст "
            "сохраняется в журнале аудита).",
            "Bu grubun mevcut taslağının içeriği kaynağın içeriğiyle değiştirilecek (önceki metin denetim izinde "
            "saklanır).",
        ),
        "Bu qrupun saat bölgüsü məlum deyil — bağlamaq üçün saatlar eyni olmalıdır.": (
            "This group's hour split is unknown — linking requires identical hours.",
            "Распределение часов этой группы неизвестно — для связывания часы должны совпадать.",
            "Bu grubun saat dağılımı bilinmiyor — bağlamak için saatler aynı olmalıdır.",
        ),
        "Bu qrupun sillabusu artıq bağlıdır.": (
            "This group's syllabus is already linked.",
            "Силлабус этой группы уже связан.",
            "Bu grubun izlencesi zaten bağlı.",
        ),
        "Bu qrupun sillabusu artıq göndərilib və ya təsdiqlənib — üstünə yazmaq olmaz.": (
            "This group's syllabus has already been submitted or approved — it cannot be overwritten.",
            "Силлабус этой группы уже отправлен или утверждён — перезаписать его нельзя.",
            "Bu grubun izlencesi zaten gönderildi veya onaylandı — üzerine yazılamaz.",
        ),
        "Bu sillabus %(group)s sillabusuna bağlıdır": (
            "This syllabus is linked to the %(group)s syllabus",
            "Этот силлабус связан с силлабусом группы %(group)s",
            "Bu izlence %(group)s izlencesine bağlı",
        ),
        "Bu sillabus başqa qrupun sillabusuna bağlıdır — dəyişiklik üçün əvvəlcə «Ayır» düyməsini basın.": (
            "This syllabus is linked to another group's syllabus — to change it, first press “Unlink”.",
            "Этот силлабус связан с силлабусом другой группы — чтобы изменить его, сначала нажмите «Отвязать».",
            "Bu izlence başka bir grubun izlencesine bağlı — değiştirmek için önce “Bağı kaldır”a basın.",
        ),
        "Bu sillabus heç bir sillabusa bağlı deyil.": (
            "This syllabus is not linked to any syllabus.",
            "Этот силлабус ни с чем не связан.",
            "Bu izlence hiçbir izlenceye bağlı değil.",
        ),
        "Bu sillabusa bağlı qrup sayı: %(count)s": (
            "Groups linked to this syllabus: %(count)s",
            "Групп, связанных с этим силлабусом: %(count)s",
            "Bu izlenceye bağlı grup sayısı: %(count)s",
        ),
        "Bu sillabusu kopyalamaq üçün icazəniz yoxdur.": (
            "You do not have permission to copy this syllabus.",
            "У вас нет прав на копирование этого силлабуса.",
            "Bu izlenceyi kopyalama izniniz yok.",
        ),
        "Bu sillabusun son təsdiqlənmiş versiyası ona bağlı bütün qruplara tətbiq olunacaq. Saatı dəyişmiş və ya "
        "öz qaralaması açıq olan qrup ötürülür.": (
            "The latest approved version of this syllabus will be applied to all linked groups. Groups whose hours "
            "changed or that have their own open draft are skipped.",
            "Последняя утверждённая версия этого силлабуса будет применена ко всем связанным группам. Группы с "
            "изменёнными часами или с открытым собственным черновиком пропускаются.",
            "Bu izlencenin son onaylı sürümü bağlı tüm gruplara uygulanacak. Saati değişmiş veya kendi taslağı açık "
            "olan grup atlanır.",
        ),
        "Eyni sillabusu istifadə et (bağla)": (
            "Use the same syllabus (link)",
            "Использовать тот же силлабус (связать)",
            "Aynı izlenceyi kullan (bağla)",
        ),
        "Hamısına tətbiq et": ("Apply to all", "Применить ко всем", "Tümüne uygula"),
        "Hazırdır": ("Done", "Готово", "Tamam"),
        "Kopyala və uyğunlaşdır": ("Copy and adjust", "Скопировать и адаптировать", "Kopyala ve uyarla"),
        "Mövcud sillabusdan istifadə et": (
            "Use an existing syllabus",
            "Использовать существующий силлабус",
            "Mevcut izlenceyi kullan",
        ),
        "Mənbə eyni fənnin eyni semestrinə aid deyil.": (
            "The source does not belong to the same subject and semester.",
            "Источник не относится к той же дисциплине и семестру.",
            "Kaynak aynı derse ve döneme ait değil.",
        ),
        "Mənbə sillabus": ("Source syllabus", "Исходный силлабус", "Kaynak izlence"),
        "Mənbə sillabus hələ təsdiqlənməyib — bağlamaq təsdiqdən sonra mümkündür, indi kopyalaya bilərsiniz.": (
            "The source syllabus is not approved yet — linking is possible after approval; you can copy it now.",
            "Исходный силлабус ещё не утверждён — связать можно после утверждения, сейчас его можно скопировать.",
            "Kaynak izlence henüz onaylanmadı — bağlama onaydan sonra mümkün; şimdi kopyalayabilirsiniz.",
        ),
        "Mənbədə yeni təsdiqlənmiş versiya var": (
            "The source has a newer approved version",
            "У источника есть новая утверждённая версия",
            "Kaynağın daha yeni onaylı sürümü var",
        ),
        "Mənbədə yeni təsdiqlənmiş versiya var.": (
            "The source has a newer approved version.",
            "У источника есть новая утверждённая версия.",
            "Kaynağın daha yeni onaylı sürümü var.",
        ),
        "Mənbədə yeni təsdiqlənmiş versiya var. Saatlar eyni qaldığı üçün eyni məzmun bu qrupa da tətbiq olunacaq; "
        "əvvəlki nüsxə arxivlənir.": (
            "The source has a newer approved version. Since the hours are still the same, the same content will be "
            "applied to this group; the previous copy is archived.",
            "У источника есть новая утверждённая версия. Поскольку часы не изменились, то же содержание будет "
            "применено к этой группе; прежняя копия архивируется.",
            "Kaynağın daha yeni onaylı sürümü var. Saatler aynı kaldığı için aynı içerik bu gruba da uygulanacak; "
            "önceki kopya arşivlenir.",
        ),
        "Mənbədən yenilə": ("Update from source", "Обновить из источника", "Kaynaktan güncelle"),
        "Mənbənin son təsdiqlənmiş versiyası bu sillabusa tətbiq olundu.": (
            "The source's latest approved version has been applied to this syllabus.",
            "Последняя утверждённая версия источника применена к этому силлабусу.",
            "Kaynağın son onaylı sürümü bu izlenceye uygulandı.",
        ),
        "Mənbənin təsdiqi kafedra qərarı deyil (köçürmə və ya bağlama) — yalnız kopyalamaq olar.": (
            "The source's approval is not a department decision (migration or link) — it can only be copied.",
            "Утверждение источника не является решением кафедры (перенос или связь) — его можно только скопировать.",
            "Kaynağın onayı bölüm kararı değil (aktarım veya bağlama) — yalnızca kopyalanabilir.",
        ),
        "Mənbənin yeni versiyası tətbiq olunsun?": (
            "Apply the source's new version?",
            "Применить новую версию источника?",
            "Kaynağın yeni sürümü uygulansın mı?",
        ),
        "Məzmun kopyalandı və saatlara uyğunlaşdırıldı — qaralamanı yoxlayıb təsdiqə göndərin.": (
            "Content copied and adjusted to the hours — review the draft and submit it for approval.",
            "Содержание скопировано и адаптировано к часам — проверьте черновик и отправьте на утверждение.",
            "İçerik kopyalandı ve saatlere uyarlandı — taslağı kontrol edip onaya gönderin.",
        ),
        "Məzmun qaralama kimi kopyalanır, həftəlik plan bu qrupun saatına uyğunlaşdırılır, sonra adi qaydada "
        "təsdiqə göndərilir.": (
            "The content is copied as a draft, the weekly plan is adjusted to this group's hours, then it goes "
            "through the usual approval.",
            "Содержание копируется как черновик, недельный план адаптируется к часам этой группы, затем проходит "
            "обычное утверждение.",
            "İçerik taslak olarak kopyalanır, haftalık plan bu grubun saatlerine uyarlanır, sonra olağan onaya "
            "gönderilir.",
        ),
        "Məzmun və saatlar mənbə ilə eynidir; təsdiq mənbənin kafedra təsdiqindən gəlir. Dəyişiklik etmək üçün bağı "
        "ayırın — müstəqil qaralama açılacaq.": (
            "Content and hours are identical to the source; approval comes from the source's department approval. "
            "To make changes, unlink it — an independent draft will open.",
            "Содержание и часы совпадают с источником; утверждение взято из утверждения кафедры для источника. "
            "Чтобы внести изменения, снимите связь — откроется независимый черновик.",
            "İçerik ve saatler kaynakla aynı; onay, kaynağın bölüm onayından gelir. Değişiklik yapmak için bağı "
            "kaldırın — bağımsız bir taslak açılır.",
        ),
        "Saatlar eynidir": ("Same hours", "Часы совпадают", "Saatler aynı"),
        "Saatlar eynidir — eyni təsdiqlənmiş məzmun bu qrup üçün də qüvvəyə minir, ayrıca təsdiq lazım deyil.": (
            "Same hours — the same approved content takes effect for this group too; no separate approval is needed.",
            "Часы совпадают — то же утверждённое содержание вступает в силу и для этой группы, отдельное "
            "утверждение не нужно.",
            "Saatler aynı — aynı onaylı içerik bu grup için de yürürlüğe girer, ayrı onay gerekmez.",
        ),
        "Saatlar fərqlidir": ("Different hours", "Часы различаются", "Saatler farklı"),
        "Saatlar fərqlidir — kopyalayıb həftəlik planı uyğunlaşdırın.": (
            "The hours differ — copy it and adjust the weekly plan.",
            "Часы различаются — скопируйте и адаптируйте недельный план.",
            "Saatler farklı — kopyalayıp haftalık planı uyarlayın.",
        ),
        "Semestr dosyesi": ("Semester file", "Досье семестра", "Dönem dosyası"),
        "Seçilmiş qruplara eyni mənbə tətbiq olunur: saatlar eynidirsə bağlanır, fərqlidirsə kopyalanıb "
        "uyğunlaşdırılır. Sillabusu olan qrup dəyişdirilmir.": (
            "The same source is applied to the selected groups: linked if the hours match, otherwise copied and "
            "adjusted. Groups that already have a syllabus are not changed.",
            "К выбранным группам применяется тот же источник: при совпадении часов — связывание, иначе — копия с "
            "адаптацией. Группы, у которых уже есть силлабус, не изменяются.",
            "Seçilen gruplara aynı kaynak uygulanır: saatler aynıysa bağlanır, farklıysa kopyalanıp uyarlanır. "
            "İzlencesi olan grup değiştirilmez.",
        ),
        "Sillabus bağlandı — %(group)s qrupunun təsdiqlənmiş sillabusu ilə eyni məzmun qüvvəyə mindi.": (
            "Syllabus linked — the same content as the approved %(group)s syllabus is now in force.",
            "Силлабус связан — вступило в силу то же содержание, что и в утверждённом силлабусе группы %(group)s.",
            "İzlence bağlandı — %(group)s grubunun onaylı izlencesiyle aynı içerik yürürlüğe girdi.",
        ),
        "Sillabuslar fərqli kafedraların təsdiqinə düşür — kopyalayıb ayrıca təsdiqə göndərin.": (
            "The syllabi fall under different departments' approval — copy it and submit it separately.",
            "Силлабусы утверждают разные кафедры — скопируйте и отправьте на отдельное утверждение.",
            "İzlenceler farklı bölümlerin onayına tabi — kopyalayıp ayrıca onaya gönderin.",
        ),
        "Müəllif: siz": ("Author: you", "Автор: вы", "Yazar: siz"),
        "Sizin üçün uyğun mənbə sillabus tapılmadı.": (
            "No suitable source syllabus was found for you.",
            "Подходящий исходный силлабус для вас не найден.",
            "Sizin için uygun kaynak izlence bulunamadı.",
        ),
        "Sıfırdan yazmaq lazım deyil: saatlar eynidirsə təsdiqlənmiş sillabusa bağlayın, fərqlidirsə kopyalayıb bu "
        "qrupun saatına uyğunlaşdırın.": (
            "No need to start from scratch: link to the approved syllabus if the hours match, otherwise copy it and "
            "adjust it to this group's hours.",
            "Не нужно писать с нуля: если часы совпадают — свяжите с утверждённым силлабусом, если нет — "
            "скопируйте и адаптируйте к часам этой группы.",
            "Sıfırdan yazmaya gerek yok: saatler aynıysa onaylı izlenceye bağlayın, farklıysa kopyalayıp bu grubun "
            "saatlerine uyarlayın.",
        ),
        "Təsdiqlənmiş nüsxə tələbələr üçün qüvvədə qalır. Redaktə üçün müstəqil qaralama açılır və o, adi qaydada "
        "kafedra təsdiqinə göndərilir. Mənbədəki sonrakı dəyişikliklər bu qrupa artıq tətbiq olunmayacaq.": (
            "The approved copy stays in force for students. An independent draft opens for editing and goes "
            "through the usual department approval. Later changes to the source will no longer apply to this group.",
            "Утверждённая копия остаётся в силе для студентов. Для редактирования открывается независимый "
            "черновик, который проходит обычное утверждение кафедры. Последующие изменения источника к этой группе "
            "больше не применяются.",
            "Onaylı kopya öğrenciler için yürürlükte kalır. Düzenleme için bağımsız bir taslak açılır ve olağan "
            "bölüm onayından geçer. Kaynaktaki sonraki değişiklikler bu gruba artık uygulanmaz.",
        ),
        "Tətbiq et": ("Apply", "Применить", "Uygula"),
        "Yeniləndi: %(synced)s · artıq son versiyada: %(already)s · ötürüldü: %(skipped)s.": (
            "Updated: %(synced)s · already up to date: %(already)s · skipped: %(skipped)s.",
            "Обновлено: %(synced)s · уже актуальны: %(already)s · пропущено: %(skipped)s.",
            "Güncellendi: %(synced)s · zaten güncel: %(already)s · atlandı: %(skipped)s.",
        ),
        "artıq bağlı idi": ("was already linked", "уже был связан", "zaten bağlıydı"),
        "artıq bağlıdır": ("already linked", "уже связан", "zaten bağlı"),
        "bağlanacaq": ("will be linked", "будет связан", "bağlanacak"),
        "bağlandı": ("linked", "связан", "bağlantı kuruldu"),
        "bağlı qrup: {count}": ("linked groups: {count}", "связанных групп: {count}", "bağlı grup: {count}"),
        "kopyalanacaq": ("will be copied", "будет скопирован", "kopyalanacak"),
        "kopyalandı": ("copied", "скопирован", "kopyası alındı"),
        "saat məlum deyil": ("hours unknown", "часы неизвестны", "saat bilinmiyor"),
        "sillabus yoxdur": ("no syllabus", "нет силлабуса", "izlence yok"),
        "yeniləndi": ("updated", "обновлён", "güncellendi"),
        "ötürüldü": ("skipped", "пропущен", "atlandı"),
        "öz sillabusu var": ("has its own syllabus", "есть собственный силлабус", "kendi izlencesi var"),
        "öz sillabusu var — dəyişdirilmədi": (
            "has its own syllabus — not changed",
            "есть собственный силлабус — не изменён",
            "kendi izlencesi var — değiştirilmedi",
        ),
    },
}

PLURALS: dict = {}


def _value(lang, az, row):
    return az if lang == "az" else row[LANGS.index(lang) - 1]


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ROWS.items():
        for msgid, row in items.items():
            want = _value(lang, msgid, row)
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=want))
                added += 1
            elif entry.msgstr != want and (
                not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete or ctx in FORCE
            ):
                entry.msgstr, entry.obsolete = want, False
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
