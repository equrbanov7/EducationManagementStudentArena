"""Kabinetin əməliyyat təlimatları. Mövzular yalnız istifadəçinin bölmələrinə bağlanır."""

import json
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

from django.urls import reverse

from .faq_academic_access import academic_flags
from .faq_extra import EXTRA
from .faq_operational_access import REQUIRED_FLAGS
from .faq_operations import EXTERNAL_ROUTES, OPERATIONS
from .faq_tours import tour_rows
from .faq_workload import GUIDE_ROWS

PUBLIC_LOGIN_GUIDES = frozenset({"login", "recover"})


@lru_cache(maxsize=1)
def media_metadata():
    return json.loads(Path(__file__).with_name("faq_media.json").read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Guide:
    key: str
    title: str
    topic: str
    section: str
    destination: str
    video: str
    steps: tuple[str, ...]
    aliases: str = ""
    flags: tuple[str, ...] = ()

    @property
    def route(self):
        return EXTERNAL_ROUTES.get(self.key)

    @property
    def chapters(self):
        return media_metadata().get(self.video, {}).get("chapters", ())

    @property
    def start(self):
        chapter = {
            "workload-groups": 1,
            "workload-new-row": 1,
            "workload-hours": 2,
            "workload-split": 3,
            "workload-transfer": 6,
            "missing-person": 3,
            "student-material": 1,
            "section-my-journal": 3,
            "journal-limit": 4,
            "student-journal-correction": 5,
            "load-lab-hours": 6,
            "load-consult": 4,
            "load-exam": 5,
            "load-thesis": 6,
            "load-postgrad": 7,
        }.get(self.key)
        if chapter is not None and len(self.chapters) > chapter:
            return self.chapters[chapter]["start"]
        return {
            "locked-mark": 50.7,
            "published-paper-score": 53,
        }.get(self.key, 0)

    @property
    def length(self):
        seconds = round(media_metadata().get(self.video, {}).get("duration", 0))
        return f"{seconds // 60}:{seconds % 60:02d}"

    @property
    def has_subtitles(self):
        return True

    @property
    def video_url(self):
        return reverse("accounts:faq_media", kwargs={"key": self.key, "extension": "mp4"})

    @property
    def subtitle_url(self):
        return reverse("accounts:faq_media", kwargs={"key": self.key, "extension": "vtt"})


CORE_GUIDES = (
    Guide(
        "journal-entry",
        "Jurnala dərsi, iştirakı, qayıbı və balı necə yazım?",
        "Elektron jurnal",
        "my-journal",
        "Elektron jurnalı aç",
        "journal-entry",
        (
            "Elektron jurnalda fənnin və qrupun adını tutuşdurun. Dərsin keçiriləcəyi jurnalı açın.",
            "«Yeni dərs» düyməsini basın. Tarixi, dərsin növünü və mövzunu seçib «Tətbiq et» düyməsini basın.",
            "Həmin tarixdə tələbənin xanasını açın. İştirakı (i/e) və ya qayıbı (q/b) seçin. Qiymət yazılan dərsdə balı da daxil edin.",
            "«Yadda saxla» düyməsini basın. Tarix sütununda tələbənin sətrini yenidən yoxlayın. Redaktə müddəti qeyd növünə görə dəyişir və jurnalda göstərilir.",
        ),
        "jurnali doldur davamiyyət dərs aktivləşdirmək gecikmə qb ie qiymət",
        ("is_teacher",),
    ),
    Guide(
        "locked-mark",
        "Səhv qayıb və ya bal yazmışam. Kilidlənmiş xananı necə düzəltdirim?",
        "Jurnal düzəlişi",
        "my-journal",
        "Elektron jurnalı aç",
        "journal-entry",
        (
            "Fənnin jurnalında dərsin tarixini, qrupunu və tələbənin sətrini yoxlayın. Dərsin özünü redaktə etmək və tələbənin qeydini dəyişmək üçün müddətlər fərqlənə bilər.",
            "Xana redaktəyə açıqdırsa, onu seçin, düzgün davamiyyəti və ya balı daxil edin, yadda saxlayın və nəticəni yenidən oxuyun.",
            "Kilidli xanaya basın. «RİM-ə müraciət yaz» vasitəsilə fənni, qrupu, dəqiq tarixi, cari qeydi və düzgün dəyəri bildirin. Düzəlişi əsaslandıran sənədiniz varsa əlavə edin.",
            "Müraciətin nömrəsini saxlayın və «Müraciətlərim»də cavabı izləyin. Düzəliş təsdiqlənəndə həmin tarixdə xananı yenidən yoxlayın.",
        ),
        "qb ie davamiyyət iştirak üzrlü qayıb səhv qiymət qaib gayib jurnalda duzelis qiymətləndirmə",
        ("is_teacher",),
    ),
    Guide(
        "grades",
        "Fənn üzrə qiymətlərimə və imtahan nəticəmə haradan baxım?",
        "Qiymətlər",
        "my-results",
        "Nəticələrimi aç",
        "grades",
        (
            "Sol menyuda «Nəticələrim»i açın və istədiyiniz fənnin kartını tapın. Eyniadlı fənlər varsa, dövrü də yoxlayın.",
            "Kartda giriş balını, davamiyyəti, fənn üzrə seminar və ya laboratoriya balını, aralıq (midterm) və yekun (final) nəticələrini ayrı-ayrılıqda oxuyun.",
            "Konkret günün balını yoxlamaq üçün «Elektron jurnal»da həmin fənni açın. «Dərs tarixçəsi»nə qədər aşağı sürüşdürüb uyğun tarixi seçin.",
        ),
        "qiymet qiymətlərim nəticə bal ortalama midterm final akademik",
        ("can_view_student_assignments",),
    ),
    Guide(
        "journal-limit",
        "i/e və q/b nə deməkdir? Qayıb limitinə nə qədər qaldığını necə bilim?",
        "Elektron jurnal",
        "my-journal",
        "Elektron jurnalı aç",
        "grades",
        (
            "«Elektron jurnal»da fənni açın. Yuxarıda «Qayıb» göstəricisində cari sayı və həmin fənn üçün göstərilən limiti oxuyun.",
            "Limitdən cari qayıb sayını çıxın. Məsələn, limit 3 Q/b, cari say 1-dirsə, limitə 2 Q/b qalır. Hər fənnin öz limitinə baxın.",
            "Səhifəni «Dərs tarixçəsi»nə qədər aşağı sürüşdürün. «Nəticə» sütununda i/e iştirak etdiyinizi, q/b qayıbı, rəqəm isə dərsdə yazılmış balı göstərir.",
            "Tarix sətrini basıb günün təfərrüatını açın. Fənn üzrə yekun vəziyyəti və nəticəni ayrıca «Nəticələrim»də yoxlayın.",
        ),
        "qb q/b ie i/e qaib gayib qayıb limiti qalan qaldıq kəsr iştirak davamiyyət",
        ("is_student",),
    ),
    Guide(
        "open-application",
        "Fənnim, qrupum və ya dərsim kabinetdə görünmür. Necə müraciət edim?",
        "Müraciətlər",
        "applications",
        "Müraciətlərimi aç",
        "section-applications",
        (
            "Əvvəl seçilmiş semestri, fənni və qrupu yoxlayın. Dərs cədvəlində həftəni, jurnalda isə dərs tarixini də tutuşdurun.",
            "«Müraciətlərim» bölməsində «Yeni müraciət»i açın. Ekranda gördüyünüz problemə uyğun növü seçin.",
            "Mövzuda problemi bir cümlə ilə yazın. Mətndə fənni, qrup və ya alt qrupu, gözlədiyiniz dərsin tarixini və ekranda görünən nəticəni göstərin. Lazım gələrsə aidiyyəti ekran şəklini əlavə edin.",
            "Göndərdikdən sonra müraciəti siyahıda açın. Tarixçə və cavab bölməsində əlavə məlumat istənilibsə, eyni müraciət daxilində cavab verin.",
        ),
        "jurnal açılmır fənn yoxdur sistemə düşməyib siyahı yük dərs saatı texniki problem dəstək bileti",
        ("can_create_support",),
    ),
    Guide(
        "syllabus",
        "Sillabusu necə yaradım, qaralamanı tamamlayım və sonradan redaktə edim?",
        "Sillabus",
        "my-journal",
        "Elektron jurnalı aç",
        "syllabus",
        (
            "«Elektron jurnal»da fənn və qrupun jurnalını açıb «Sillabus yarat»ı seçin. Fənnin məlumatlarını və həftəlik mövzuları doldurun.",
            "«Qaralama saxla» ilə işi saxlayın. Jurnala qayıdanda «Qaralamanı tamamla» ilə qaldığınız yerdən davam edin. Sahələri yoxlayıb təsdiq addımını tamamlayın.",
            "Təsdiqdən sonra jurnalda «Sillabusa bax», sonra «Sillabusu redaktə et» seçin. Avtomatik təsdiq rejimində öz müstəqil versiyanızı redaktə edə bilərsiniz.",
            "Kafedra təsdiqi tələb olunursa, «Yeni versiya yarat» seçib düzəlişləri göndərin. Tələbə yeni versiyanı təsdiqdən sonra görür. Mənbəyə bağlı surət üçün əvvəl «Ayır» əməli tələb oluna bilər.",
        ),
        "sillabus proqram həftəlik mövzu plan syllabus qaralama redaktə təsdiq",
        ("can_edit_syllabus",),
    ),
    Guide(
        "teacher-schedule",
        "Bu həftə və gələn həftə hansı qrupda, saatda və auditoriyada dərsim var?",
        "Dərs cədvəli",
        "my-schedule",
        "Dərs cədvəlini aç",
        "schedule",
        (
            "«Dərs cədvəli»ni açın və yuxarıdakı tarix aralığını yoxlayın.",
            "«Bu həftə» və ya «Gələn həftə»ni seçin. Həftəni dəyişəndə göstərilən tarixlə dərs gününü tutuşdurun.",
            "Dərsin kartını açın. Başlama və bitmə saatını, dərsin növünü, qrupu və auditoriyanı oxuyun. Uyğunsuzluq varsa, bu məlumatları müraciətdə göstərin.",
        ),
        "alt üst həftə dərs yeri korpus otaq saat auditoriya dərs cədvəlim",
        ("is_teacher",),
    ),
    Guide(
        "schedule-admin",
        "Qrupun cədvəlinə dərsi necə yerləşdirim və nəticəni yoxlayım?",
        "Cədvəl idarəetməsi",
        "schedule-manage",
        "Cədvəl idarəetməsini aç",
        "schedule-manage",
        (
            "«Cədvəl idarəetməsi»ndə «Qrup» üzrə baxışı açın. Düzgün dövrü və qrupu seçin.",
            "Həftəlik cədvəldə gün və saatın kəsişməsindəki boş xanada + düyməsini basın. Müəllimi, fənni, dərsin növünü, həftəni və auditoriyanı yoxlayın.",
            "«Cədvələ yaz»ı basın, təsdiq pəncərəsində məlumatları oxuyun və «Təsdiqlə»ni seçin. Toqquşma bildirişi görsəniz, göstərilən resursu və saatı nəzərdən keçirin.",
            "Qrup cədvəlində yeni kartı açın. Həftə, müəllim, saat və auditoriyanın nəzərdə tutduğunuz kimi yazıldığını yoxlayın.",
        ),
        "cədvəl idarəetməsi toqquşma otaq dərs yerləşdirmək alt üst",
        ("can_manage_schedule",),
    ),
    Guide(
        "material",
        "Fənn qovluğuna fayl necə yükləyim ki, tələbələr onu görə bilsin?",
        "Tədris materialları",
        "subject-folders",
        "Fənn qovluqlarını aç",
        "material",
        (
            "«Fənn qovluqları»nda uyğun fənni və qrupu tapıb «Aç»ı seçin. «Material əlavə et» düyməsini basın.",
            "«Növ» siyahısında «Fayl»ı seçin, «Başlıq» yazın, aid olduğu mövzunu və yüklənəcək faylı seçin.",
            "Tələbələrin faylı indi görməsi üçün «Dərhal dərc et (tələbələr görsün)» xanasını işarələyin və «Yadda saxla»nı basın.",
            "Materialın qarşısında «Dərc edilib» yazısını yoxlayın. Qaralama saxlamısınızsa, hazır olanda həmin materialın «Dərc et» düyməsini seçin.",
        ),
        "material yüklə pdf mühazirə fayl resurs qovluq paylaş sillabus mövzu",
    ),
    Guide(
        "exam-pin",
        "Zalda keçirilən midterm və ya final üçün fərdi PIN-i haradan götürüm?",
        "İmtahan girişi",
        "assigned-exams",
        "Təyin olunmuş tapşırıqları aç",
        "pin",
        (
            "«Təyin olunmuş tapşırıqlar»da aralıq və ya yekun imtahanının kartını tapın. Fənni, tarixi və saatı yoxlayın.",
            "Həmin kartda «Tapşırığı aç» düyməsini basın. Açılan pəncərədə «İmtahan PIN-i» hissəsində yalnız bu imtahana aid fərdi kodu oxuyun.",
            "Zalda təyin edilmiş vaxtda həmin imtahanın giriş ekranına bu kodu daxil edin. Midterm və final ayrı kartlardır. Hər dəfə açdığınız kartdakı PIN-i götürün.",
            "PIN hissəsi görünmürsə, seçdiyiniz kartın zal imtahanına aid olduğunu yoxlayın. Təyinat və ya kod çatışmırsa, fənni və imtahan vaxtını İmtahan Mərkəzinə bildirin.",
        ),
        "pin kod pinkod şifrə imtahana giriş zal terminal aralıq midterm final yekun",
        ("can_view_student_assignments",),
    ),
    Guide(
        "quiz-start",
        "Aktiv quizi haradan başladım və cavabımın göndərildiyini necə yoxlayım?",
        "Quiz və tapşırıqlar",
        "assigned-exams",
        "Təyin olunmuş tapşırıqları aç",
        "quiz",
        (
            "«Təyin olunmuş tapşırıqlar»da «Aktiv» olan quizi tapıb «Tapşırığı aç» düyməsini basın.",
            "Müddəti və təlimatı oxuyun. Hazır olanda açılan pəncərədə «İmtahana başla» düyməsini basın.",
            "Sualı oxuyub cavabınızı seçin. Bütün cavabları yoxlayandan sonra «İmtahanı bitir» düyməsini basın.",
            "«Bəli, imtahanı bitir» ilə təhvili təsdiqləyin. Tamamlanma ekranını yoxlayın. Nəticə açıqdırsa, balınız da görünəcək.",
        ),
        "quiz kviz quizi test başlat başlamaq onlayn imtahana başla sual",
        ("can_view_student_assignments",),
    ),
    Guide(
        "appeal",
        "İmtahan nəticəsinə necə apellyasiya verim və cavabı harada izləyim?",
        "Apellyasiya",
        "my-appeals",
        "Apellyasiyalarımı aç",
        "appeal",
        (
            "«Apellyasiyalarım»da «Yeni apellyasiya müraciəti»ni açın. İmtahanın adını və son müraciət tarixini yoxlayın, sonra «Apellyasiyaya ver»i seçin.",
            "Etiraz etdiyiniz sualın yanında «Apellyasiya et» seçimini aktivləşdirin. Səbəbi seçib ən azı 30 simvolla hansı hissəyə və niyə etiraz etdiyinizi yazın.",
            "«Apellyasiyanı göndər»i, sonra «Bəli, göndər»i basın. «Apellyasiyalarım»a qayıdıb statusu yoxlayın.",
            "Müraciəti açaraq müəllimin cavabını və bal dəyişikliyini izləyin. İmtahan siyahıda görünmürsə, nəticəni və onun üçün açıq müraciət müddətini yoxlayın.",
        ),
        "appelyasiya apelyasiya şikayət qiymət yenidən yoxlama etiraz midterm final",
    ),
    Guide(
        "student-material",
        "Müəllimin paylaşdığı dərs materialını haradan açım?",
        "Dərs materiallarım",
        "my-subject-folders",
        "Dərs materiallarımı aç",
        "grades",
        (
            "Sol menyuda «Dərs materiallarım»ı açın. Fənni və müəllimi yoxlayıb istədiyiniz qovluğa keçin.",
            "Artıq «Fənlərim»dəsinizsə, fənnin kartındakı «Dərs materialları» keçidini seçin. Müəllim bir qovluq paylaşıbsa, o birbaşa açılır. Bir neçə qovluq varsa, uyğun qovluğu siyahıdan seçin.",
            "Mövzunu açın və müəllimin əlavə etdiyi faylı seçin. Material görünmürsə, semestri, qrupu və müəllimin həmin qovluğu qrupunuzla paylaşıb-paylaşmadığını dəqiqləşdirin.",
        ),
        "fənn qovluqlarım qovluq kitab pdf dərs materialı mövzu mühazirə haradadır materiallarım",
    ),
    Guide(
        "grade-reconciliation",
        "Köçürülmüş balımda fərq görürəmsə, hara müraciət edim?",
        "Qiymətlər",
        "my-results",
        "Nəticələrimi aç",
        "grades",
        (
            "«Nəticələrim»də fənni və semestri seçin. Kartda giriş balına və hər hissənin qarşısındakı dəyərə baxın. Dərsin növündən asılı olaraq seminar, laboratoriya və ya hər ikisi göstərilir.",
            "Köçürülmüş ballarla bağlı qırmızı qeydi oxuyun. Fərq varsa, fənnin adını, semestri, gördüyünüz balı və hansı qeydlə müqayisə etdiyinizi İmtahan Mərkəzinə bildirin.",
            "Cavab aldıqda həmin semestrin fənn kartını yenidən açın və dəqiqləşdirilmiş balı yoxlayın.",
        ),
        "qiymət səhv bal köçürülmüş əvvəlki sistem seminar laboratoriya uyğunsuzluq",
        ("is_student",),
    ),
    Guide(
        "homework",
        "Ev tapşırığını necə göndərim və müəllim qaytarsa necə düzəldim?",
        "Ev tapşırığı",
        "my-subject-folders",
        "Dərs materiallarımı aç",
        "homework",
        (
            "«Dərs materiallarım»da fənni açın. «Fənlərim» kartındakı «Dərs materialları» keçidindən də müəllimin paylaşdığı qovluğa çata bilərsiniz. Ev tapşırığının qarşısında «Cavab ver»i seçib şərti və son tarixi oxuyun.",
            "Cavabı yazın. Müəllim fayl qəbuluna icazə veribsə, faylı da seçin. «Göndər» və «Bəli, davam et» ilə təsdiqləyin.",
            "«Göndərişlərim»də cəhdin göründüyünü yoxlayın. Tapşırıq qaytarılıbsa, eyni tapşırıqda rəyi oxuyub «Düzəldilmiş cavab» hissəsindən yenidən göndərin.",
        ),
        "tapşırıq homework cavab göndərmək fayl müəllim rəyi",
    ),
    Guide(
        "review-homework",
        "Göndərilmiş ev tapşırığını necə yoxlayım və rəylə qaytarım?",
        "Tapşırıq yoxlaması",
        "subject-folder-review",
        "Tapşırıq yoxlamasını aç",
        "review",
        (
            "«Tapşırıq yoxlaması»nda «Yoxlanılır» siyahısını açın və işin qarşısında «Bax»ı basın.",
            "«Cavab» bölməsində tələbənin yazdığını və əlavə etdiyi faylı yoxlayın. Düzəliş lazımdırsa, «Rəylə qaytar»ı seçin.",
            "Tələbənin konkret nəyi dəyişməli olduğunu yazıb «Qaytar»ı basın. Yeni cəhd gələndə əvvəlki rəyi və düzəlişi müqayisə edin, sonra yekun rəyi və nəticəni saxlayın.",
        ),
        "müəllim ev tapşırığı yoxlanış düzəliş qaytar",
    ),
    Guide(
        "exam-import",
        "Kağız imtahanının ballarını Excel-dən necə yoxlayıb sistemə yazım?",
        "İmtahan Mərkəzi",
        "exam-score-entry",
        "İmtahan balının daxil edilməsini aç",
        "paper",
        (
            "Semestri, qrupu, fənni və imtahan növünü seçin. «Fayldan yüklə»də «XLSX şablon»u endirin.",
            "Şablonda tələbənin sətrində «Bal» sütununu doldurub faylı saxlayın. Qayıdıb faylı seçin və «Yoxla»nı basın.",
            "Önizləmədə cari və yeni balları, maksimum balı və xəta sayını yoxlayın. Hazır olanda «Tətbiq et — balları sistemə yaz»ı basın.",
            "«Siyahını yenilə» ilə yazılmış balı yoxlayın. Nəticənin tələbəyə göstərilmə şərti imtahan növünün altında izah olunur.",
        ),
        "imtahan mərkəzi kağız balı excel xlsx import idxal",
    ),
    Guide(
        "reset",
        "İstifadəçinin parolunu sıfırlayıb təhlükəsiz qaydada necə təhvil verim?",
        "Hesab dəstəyi",
        "account-password-reset",
        "Parol sıfırlama bölməsini aç",
        "reset",
        (
            "Parol sıfırlama bölməsində istifadəçi adı və ya ad-soyadla hesabı axtarın. Kartdakı şəxsiyyəti sənədlə, istifadəçi adını və qrupu tutuşdurun.",
            "«Parolu sıfırla»nı seçin. Təsdiq pəncərəsində hesabı bir də yoxlayıb «Bəli, sıfırla»nı basın.",
            "Bir dəfə göstərilən müvəqqəti parolu şəxsiyyətini təsdiqlədiyiniz istifadəçiyə birbaşa verin. Ardınca «Verdim — parolu gizlət»i basın. İstifadəçi növbəti girişdə öz parolunu qurur.",
        ),
        "parol şifrə reset sıfırla hesab giriş",
    ),
    Guide(
        "document",
        "Elektron arayışın və ya transkriptin həqiqiliyini necə yoxlayım?",
        "Elektron sənədlər",
        "",
        "",
        "document-verify",
        (
            "Sənəddəki QR kodu oxudun və ya sənədin üzərindəki yoxlama ünvanını açın. Kodu sənəddə yazıldığı kimi daxil edib «Yoxla»nı basın.",
            "Nəticədə sənədin qüvvədə olmasını, sənədin növünü və verilmə tarixini əlinizdəki nüsxə ilə tutuşdurun.",
            "PDF nüsxəsinin özünü də yoxlamaq üçün «Faylı müqayisə et» bölməsində həmin PDF-i seçin. «Müqayisə et» düyməsini basıb nəticəni oxuyun.",
        ),
        "arayış sənəd yoxla transkript qr kod pdf həqiqilik",
    ),
)
CORE_GUIDES += (
    Guide(
        "recover",
        "Parolumu unutmuşam. Hesabıma girişi necə bərpa edim?",
        "Hesaba giriş",
        "",
        "",
        "recover",
        (
            "Adi giriş formasında parol xanasının altındakı «Şifrəni unutmusunuz?» keçidini açın.",
            "Hesaba bağlanmış e-poçt ünvanını yazın və «OTP kodu göndər» düyməsini basın. Başqa ünvan yazsanız, bərpa məktubu həmin hesab üçün gəlməyəcək.",
            "E-poçtunuzu və spam qovluğunu yoxlayın. Bərpa məktubunda verilən keçidi açın və həmin məktubdakı birdəfəlik kodu götürün.",
            "Açılan səhifədə birdəfəlik kodu yazın. Yeni parolu iki dəfə daxil edin və təsdiqləyin. Vaxt bitibsə, yeni bərpa məktubu istəyin.",
            "Təsdiq ekranından girişə qayıdın. Öz istifadəçi adınızı və yeni parolunuzu yazın. Hesabdakı e-poçta çıxışınız yoxdursa, universitetin Rəqəmsal İnkişaf Mərkəzinə müraciət edin.",
        ),
        "username password reset login sign in e-poçt istifadəçi kod ilkin parol şifrə OTP",
    ),
)
CORE_GUIDES += (
    Guide(
        "login",
        "İstifadəçi adım və ilkin parolum var. İlk dəfə necə daxil olum?",
        "Hesaba giriş",
        "",
        "",
        "login",
        (
            "Giriş səhifəsində rolunuzu seçin. Tələbəsinizsə «Tələbə girişi», müəllim və ya əməkdaşsınızsa müvafiq əməkdaş girişini açın.",
            "Birinci xanaya sizə verilmiş istifadəçi adını olduğu kimi yazın. Ekrandakı numune.telebe yalnız bu dərsin nümunəsidir. Siz öz istifadəçi adınızı yazmalısınız.",
            "İkinci xanaya sizə verilmiş müvəqqəti parolu yazın və «Daxil ol» düyməsini basın.",
            "İlk girişdə sistem e-poçt təsdiqi istəyərsə, istifadə etdiyiniz ünvanı yazıb birdəfəlik kod göndərin. Məktubu açın. Kodun vaxtı həmin səhifədə göstərilir.",
            "E-poçtunuza gələn kodu daxil edin. Öz yeni parolunuzu iki xanaya eyni yazıb yadda saxlayın. E-poçtunuz artıq təsdiqlənibsə, birbaşa yeni parol ekranı açıla bilər.",
            "Tələb olunan profil sahələri varsa tamamlayın. Kabinet açıldıqdan sonra sol menyudan lazımi bölməni seçin. Növbəti girişdə öz istifadəçi adınızı və yeni parolunuzu yazın.",
        ),
        "username password reset login sign in e-poçt istifadəçi kod ilkin parol şifrə OTP",
    ),
)
CORE_GUIDES += (
    Guide(
        "missing-journal",
        "Fənnim və ya qrupum elektron jurnalda niyə görünmür?",
        "Jurnal və qrup siyahısı",
        "my-journal",
        "Elektron jurnalı aç",
        "missing-journal",
        (
            "Elektron jurnalda cari tədris dövrünü yoxlayın. Qrup və fənn üzrə axtarış aparın, əvvəlki axtarış və süzgəcləri təmizləyin.",
            "Fənnin jurnalını açanda qrupun adını və tələbələrin siyahısını yoxlayın. Əsas qrup, yarımqrup və sonradan yerləşdirilən tələbələr fərqli hallardır.",
            "Axtardığınız qrup, fənn və ya tələbə yenə görünmürsə, «Müraciətlərim»də semestri, fənni, qrupu, alt qrupu və çatışmayan təyinatı dəqiq yazın. Mövcud jurnalın və dərs yükünün tutuşdurulmasını istəyin.",
        ),
        "görünmür fənn yoxdur jurnal açılmır yük bölüşdürmə qrup yarımqrup siyahı",
        ("is_teacher",),
    ),
)
CORE_GUIDES += (
    Guide(
        "teacher-journal-support",
        "Müəllimə təyin olunan jurnal görünmürsə, RİM-ə necə müraciət edim?",
        "Müraciətlər",
        "applications",
        "Müraciətlərimi aç",
        "support",
        (
            "«Müraciətlərim»də «Yeni müraciət»i açın. «Texniki problem» seçib qəbul edən şöbəni yoxlayın.",
            "Semestri, fənni, qrupu və çatışmayan dərs növünü yazıb «Müraciəti göndər»i basın.",
            "Siyahıda müraciətin nömrəsini saxlayın. Cavabı və status tarixçəsini həmin müraciətdən izləyin.",
        ),
        "müəllim seminar jurnalı görünmür texniki problem",
        ("is_teacher", "can_create_support"),
    ),
)
# Tələbələr üçün tarixçə və jurnal, yazan müəllim üçün dərs və düzəliş ayrı suallardır.
_REUSE = {
    "science-room": "science-room",
    "journal-watch": "journal-watch",
    "my-journal": "grades",
    "my-results": "grades",
    "schedule-manage": "schedule-manage",
    "syllabus-editor": "syllabus",
    "subject-folders": "material",
    "assigned-exams": "quiz",
    "my-subject-folders": "homework",
    "account-password-reset": "reset",
    "subject-folder-review": "review",
    "my-appeals": "appeal",
    "exam-score-entry": "paper",
}
_SECTION_FLAGS = {
    "journal-watch": ("faq_manage_journal_watch",),
    "my-journal": ("is_student",),
    "schedule-manage": ("can_manage_schedule",),
    "workload-distribution": ("can_distribute_workload",),
    "syllabus-editor": ("can_edit_syllabus",),
}
_SECTION_LABELS = json.loads(Path(__file__).with_name("faq_labels.json").read_text(encoding="utf-8"))
_SECTION_GUIDES = tuple(
    Guide(
        "section-" + section,
        title,
        _SECTION_LABELS[section],
        section,
        _SECTION_LABELS[section],
        _REUSE.get(section, "section-" + section),
        steps,
        aliases,
        _SECTION_FLAGS.get(section, ()),
    )
    for section, (title, steps, aliases, _source, _start) in EXTRA.items()
)

# Sıra anonim müraciətlərin əsas mövzusuna görədir. Hər istifadəçiyə yalnız öz əhatəsi göstərilir.
_PRIORITY = (
    "missing-journal",
    "journal-entry",
    "locked-mark",
    "journal-limit",
    "student-journal-correction",
    "missing-person",
    "section-groups-registry",
    "section-my-group",
    "section-subgroup-placement",
    "syllabus",
    "grades",
    "grade-reconciliation",
    "workload-hours",
    "workload-groups",
    "workload-split",
    "workload-new-row",
    "workload-transfer",
    "section-workload-distribution",
    "open-application",
    "material",
    "teacher-schedule",
    "schedule-admin",
    "exam-pin",
    "quiz-start",
    "appeal",
    "login",
    "recover",
)
_RANK = {key: index for index, key in enumerate(_PRIORITY)}
_ROWS = (*CORE_GUIDES, *(Guide(*row) for row in (*OPERATIONS, *GUIDE_ROWS, *tour_rows())), *_SECTION_GUIDES)
# Seeking allows every alias to reach every chapter of the shared MP4.
_RECORDING_FLAGS = {}
for _guide in _ROWS:
    _RECORDING_FLAGS.setdefault(_guide.video, set()).update(REQUIRED_FLAGS.get(_guide.key, ()))


def _with_policy(guide):
    flags = (*guide.flags, *academic_flags(guide), *sorted(_RECORDING_FLAGS[guide.video]))
    return replace(guide, flags=tuple(dict.fromkeys(flags)))


GUIDES = tuple(sorted(map(_with_policy, _ROWS), key=lambda guide: _RANK.get(guide.key, len(_RANK))))
BUILTIN_BY_KEY = {guide.key: guide for guide in GUIDES}
