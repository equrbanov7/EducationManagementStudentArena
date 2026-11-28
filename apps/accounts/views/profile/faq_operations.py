"""Bir neçə kabinet bölməsinə və ya ayrıca iş sahəsinə aid əməliyyatlar."""

# key, question, area, section (if any), action label, video, steps, aliases, capability flags.
OPERATIONS = (
    (
        "schedule-excel-personal",
        "Öz dərs cədvəlimi Excel faylı kimi necə yükləyim?",
        "Dərs cədvəli",
        "my-schedule",
        "Dərs cədvəlini aç",
        "schedule-excel-personal",
        (
            "«Dərs cədvəli»ndə tədris dövrünü və baxdığınız həftəni yoxlayın.",
            "«Excel yüklə (.xlsx)» düyməsini basın. Endirilən faylda seçilmiş həftənin tarix və saatlarını açın.",
            "Semestr planı vərəqində dərsin Üst, Alt və ya Hər həftə keçirildiyini yoxlayın.",
        ),
        "Excel xlsx export endir yüklə çap fərdi cədvəl",
        (),
    ),
    (
        "schedule-excel-admin",
        "Fakültə, kafedra, qrup və ya müəllim üzrə cədvəli Excel-ə necə çıxarım?",
        "Cədvəl idarəetməsi",
        "schedule-manage",
        "Cədvəl idarəetməsini aç",
        "schedule-excel-admin",
        (
            "«Cədvəl idarəetməsi»ndə dövrü və həftəni seçin. Ekranda açıq olan qrup və ya müəllim üçün birbaşa Excel keçidindən istifadə edə bilərsiniz.",
            "Daha geniş seçim üçün «Filtrlə Excel-ə ixrac et»i açın. Əvvəl qrupun fakültəsini seçin. Kafedra həmin fənn, semestr və qrupun rəsmi dərs yükündən götürülür. Yarımqrup üçün ana qrupun yükü də nəzərə alınır. Uyğun yük yoxdursa, fənn kartındakı kafedra göstərilir. Lazım gəldikdə qrupu və müəllimi seçin.",
            "Faylı endirin. Seçilmiş həftəyə aid dərslərin tarixini, saatını və auditoriyasını, ayrıca vərəqdə isə bütün semestrin həftə növünü yoxlayın.",
        ),
        "xlsx excel export ixrac endir auditoriya fakültə kafedra qrup müəllim",
        (),
    ),
    (
        "sealed-register",
        "Verdiyimiz sənədi kodla reyestrdə necə tapım?",
        "Sənəd yoxlaması",
        "",
        "Sənəd yoxlamasını aç",
        "document",
        (
            "Sol menyuda «Sənəd yoxlaması»nı açın. Arayış və ya transkript üzərindəki yoxlama kodunu axtarışa yazın.",
            "Uyğun sətrin sənəd növünü və verilmə tarixini tutuşdurun. Kodu basanda açıq yoxlama səhifəsi açılır.",
            "«Faylı müqayisə et» ilə əlinizdəki PDF-in universitetin verdiyi nüsxəyə uyğunluğunu yoxlayın.",
        ),
        "reyestr sənəd möhür kod yoxlama QR",
        ("can_manage_document_seals",),
    ),
    (
        "language-cohort",
        "Xarici dil səviyyə qrupunun siyahısına necə baxım?",
        "Xarici dil səviyyə qrupları",
        "",
        "Səviyyə qruplarını aç",
        "language-cohort-read",
        (
            "Sol menyudan «Xarici dil səviyyə qrupları»nı açın. Kafedra və qrupu seçərkən dil üzrə səviyyəni də tutuşdurun.",
            "Müəllim özünə aid və ya onunla paylaşılmış aktiv səviyyə jurnalının siyahısına baxır. Tələbənin əsas akademik qrupu ilə dil səviyyə qrupunu ayrı yoxlayın.",
            "Siyahı üzrə dəyişiklik lazımdırsa, tələbənin cari və aid olduğu səviyyə qrupunu dəqiqləşdirin. Qrup tərkibi üzrə əməliyyatı həmin əhatəyə səlahiyyəti olan əməkdaş aparır.",
        ),
        "xarici dil səviyyə qrup roster siyahı",
        ("can_view_language_cohorts",),
    ),
    (
        "room-monitor",
        "İmtahan zalında mənə aid oturumu və gedişatı necə izləyim?",
        "İmtahan zalları",
        "",
        "İmtahan zallarını aç",
        "room-monitor",
        (
            "Sol menyudan «İmtahan zalları»nı açın. Tarixə və zala baxıb sizə aid oturumu tapın.",
            "Zala keçib sessiyanın vəziyyətini və iştirak məlumatlarını yoxlayın. Nəzarətçi öz təyin edildiyi növbəni və zalı izləyir.",
            "Oturum görünmürsə, növbənin tarixini və təyinatınızı İmtahan Mərkəzi ilə dəqiqləşdirin.",
        ),
        "imtahan zalı monitor nəzarətçi sessiya oturum növbə",
        ("faq_supervise_rooms",),
    ),
)

EXTERNAL_ROUTES = {
    "laborant-journal": "registrar:journal_list",
    "laborant-components": "registrar:journal_list",
    "faq-video-editor": "accounts:faq_video_editor",
    "sealed-register": "verification:staff_list",
    "language-cohort": "registrar:language_cohorts",
    "room-monitor": "exams:exam_center_room_list",
}

WORKLOAD = (
    (
        "workload-hours",
        "Fənn 60 saatdırsa, yük bölgüsündə niyə 90 saat görünə bilər?",
        (
            "Fənnin plan saatı bir tələbənin həmin fənn üzrə keçəcəyi saatdır. 15 həftədə həftəlik 2 saat mühazirə və 2 saat seminar varsa, sillabusda 30 saat mühazirə + 30 saat seminar = 60 saat alınır.",
            "Mühazirəni hamı bir axında dinləyirsə, müəllimlər üçün 30 saat mühazirə yazılır. Seminar iki yarımqrupa ayrı vaxtlarda tam keçirilirsə, 30 + 30 = 60 saat seminar yükü yaranır. Kafedranın cəmi 30 + 60 = 90 saatdır.",
            "Bu nümunədə hər tələbə yalnız öz yarımqrupunun 30 saat seminarında iştirak edir. Bir qrupun eyni 30 saatını iki müəllim 15 + 15 kimi paylaşırsa, seminar cəmi yenə 30 saatdır.",
            "Sətir formasında planla fəaliyyətin cəmini ayrı yoxlayın. Əllə daxil edilən sətirdə təkcə yarımqrup sayını «2» etmək cəm sahəsinə yeni dəyər yazmır.",
        ),
        "60 90 15 həftə 2/2 30+30 sillabus fənnin saatı dərs yükü cəm plan müəllim",
    ),
    (
        "workload-groups",
        "Yük bölgüsündə qrup adları haradan gəlir və hansı qrupu seçməliyəm?",
        (
            "Yük sətirində qrup adları universitetin qrup reyestrindən seçilir. Əvvəl tədris dövrünü və kafedranı yoxlayın.",
            "Fənnin kartında «Sətirlər»i açın. Həmin sətirdəki əsas qrup adlarını, mühazirə axınını və seminar yarımqruplarını tutuşdurun.",
            "Lazım olan qrup reyestrdə görünmürsə, kodu, ixtisası və dövrü dəqiqləşdirin. Mövcud qrupun fərqli yazılışla ikinci nüsxəsini yaratmaq əvəzinə reyestr qeydini yoxlatdırın.",
        ),
        "qrup adları hardan gəlir reyestr axın patok yarımqrup semestr",
    ),
    (
        "workload-new-row",
        "Kafedranın dərs yükünə yeni fənn sətrini necə əlavə edim?",
        (
            "Tədris dövrünü və kafedranı seçin. Sətir əlavə etmək səlahiyyətiniz varsa, «Sətir əlavə et»i açın.",
            "Fənni, semestri, aid olan qrupları və fənnin plan saatlarını tutuşdurun. Axın və yarımqrup sayını dərsin ayrı keçirilməsinə uyğun seçin.",
            "Mühazirə, seminar və digər fəaliyyətlərin cəmini yoxlayıb saxlayın. Fənn kartında «Sətirlər»i yenidən açıb yeni sətrin qrupunu və saatını yoxlayın.",
        ),
        "yeni sətir əlavə et plan fənn semestr dərs yükü yarat",
    ),
    (
        "workload-split",
        "Niyə seminarın yanında «Bölüşdür» var? 1, 2 və «Bütün qrup» nədir?",
        (
            "Kartdakı 1, 2 və 3 görünən fəaliyyətlərin sıra nömrələridir. Məsələn, seminar keçirilmirsə, laboratoriya ikinci yerdə görünə bilər. Sətir formasındakı axın və yarımqrup sayı dərsin neçə dəfə ayrıca keçirildiyini göstərir.",
            "Birgə mühazirədə axına dərs deyən müəllim seçilir. Seminar və laboratoriya qrup və ya yarımqrup üzrə ayrı keçiriləndə «Bölüşdür» pəncərəsində hər təyinata müəllim və saat yazılır.",
            "«Bütün qrup» ümumi təyinatdır. Seçimdə nömrəli alt qruplar varsa, uyğun olanı seçin. Təyinatdakı rəqəmi müəllimə ayrılan saatla qarışdırmamaq üçün hər ikisini ayrıca yoxlayın.",
            "«Bölünməyib» bu fəaliyyət üçün hələ müəllimə verilməyən saatdır. Təyinatları saxladıqdan sonra verilən saatları və qalığı müqayisə edin.",
        ),
        "bölüşdür bölüşdürmək seminar mühazirə laboratoriya 1 2 3 bütün qrup bölünməyib vakant",
    ),
    (
        "workload-transfer",
        "Yük sətrini başqa kafedraya necə göndərim?",
        (
            "Yük bölgüsündə mənbə kafedranı seçin. Yuxarıdakı «Başqa kafedraya göndər» düyməsini basın.",
            "Açılan pəncərədə göndəriləcək sətri tapın. Eyniadlı fənlər arasında qrup və semestri tutuşdurun, qəbul edən kafedranı seçin.",
            "Ekrandakı məlumatı yoxlayıb göndərişi təsdiqləyin. Eyni əməliyyata fənnin sətir detallarından da keçə bilərsiniz.",
        ),
        "başqa kafedraya göndər köçür təhvil ötür fənn sətir transfer",
    ),
)
OPERATIONS += tuple(
    (
        key,
        title,
        "Yük bölgüsü",
        "workload-distribution",
        "Yük bölgüsünü aç",
        "workload-explained" if key in {"workload-transfer", "workload-split"} else "workload-row-basics",
        steps,
        aliases,
        (
            ("can_manage_workload", "can_distribute_workload")
            if key in {"workload-transfer", "workload-split"}
            else ("can_manage_workload",)
        ),
    )
    for key, title, steps, aliases in WORKLOAD
)

OPERATIONS += (
    (
        "student-journal-correction",
        "Dərsdə olmuşam, amma q/b və ya yanlış bal görünür. Necə bildirim?",
        "Davamiyyət və qiymət",
        "my-journal",
        "Elektron jurnalı aç",
        "grades",
        (
            "Fənnin jurnalını açıb «Dərs tarixçəsi»nə qədər aşağı sürüşdürün. Həmin tarixin sətrini seçin və iştirak qeydi ilə dərsin balını ayrı oxuyun.",
            "Gördüyünüz qeydi öz məlumatınızla tutuşdurun. «Müraciətlərim»də «Yeni müraciət» açıb uyğun növü seçin və göstərişdəki ünvanı yoxlayın.",
            "Fənni, qrupu, tarixi, hazırkı qeydi və hansı düzəlişi istədiyinizi yazın. Əsaslandıran sənəd varsa əlavə edin. Müraciətin nömrəsi ilə cavabı izləyin.",
        ),
        "səhv qayıb qiymət bal dərsdə olmuşam qeyd iştirak düzəliş qb",
        ("is_student", "can_create_support"),
    ),
    (
        "missing-person",
        "Jurnal açılır, amma tələbə siyahıda yoxdur. Nəyi yoxlayım?",
        "Qrup və tələbə siyahısı",
        "my-journal",
        "Elektron jurnalı aç",
        "missing-journal",
        (
            "Açdığınız fənnin qrupunu və semestrini yoxlayın. Tələbələrin siyahısını aşağı sürüşdürüb «Alt qrup» hissəsinə də baxın.",
            "Laboratoriya dərsidirsə, dərs üçün seçilmiş lab qrupunun tərkibini yoxlayın. Tələbənin əsas qrupu ilə bu dərs üçün yerləşdirildiyi qrupu tutuşdurun.",
            "Tələbə yenə görünmürsə, «Müraciətlərim»də fənni, qrupu, tələbəni, tarixi və hansı dərsə təsir etdiyini göstərin. Göndərməzdən əvvəl ünvanlanan şöbəni yoxlayın.",
        ),
        "tələbə siyahısı yoxdur görünmür jurnala düşməyib qrup alt lab",
        ("is_teacher",),
    ),
    (
        "language-place",
        "Tələbəni xarici dil səviyyə qrupuna necə yerləşdirim?",
        "Xarici dil səviyyə qrupları",
        "",
        "Səviyyə qruplarını aç",
        "language-cohort",
        (
            "Kartda fənni, kafedranı və müəllimi yoxlayın, sonra «İdarə et»i açın. Namizədi tələbənin adı və ya əsas qrupu ilə axtarın.",
            "Namizədi seçin. Başqa səviyyədən keçid varsa, əvvəlki səviyyəni də yoxlayın. Ən azı 10 simvolla səbəbi yazıb tələbəni seçilmiş səviyyəyə əlavə edin.",
            "Siyahıda tələbənin əsas qrupunu, tarixçədə isə yerləşdirmə hadisəsini yoxlayın.",
        ),
        "səviyyə qrupuna yerləşdir xarici dil dəyiş əsas qrup tarixçə",
        ("can_manage_language_cohorts",),
    ),
    (
        "student-syllabus",
        "Tələbə kimi fənnin sillabusunu necə oxuyum və PDF-ni necə götürüm?",
        "Sillabus",
        "my-subjects",
        "Fənlərimi aç",
        "student-syllabus",
        (
            "«Fənlərim»də fənnin kartını tapın. Təsdiq edilmiş sillabus varsa, «Sillabus (təsdiqlənmiş)» keçidindən PDF-ni götürə bilərsiniz.",
            "Sillabusu kabinetdə oxumaq üçün «Elektron jurnal»a keçin, fənnin adını seçin və «Sillabusa bax»ı basın.",
            "Açılan paneldə fənnin adını, təsdiq vəziyyətini və versiyanı yoxlayın. Həftəlik mövzuları və qiymətləndirmə qaydalarını oxuyun. Həmin versiyanı saxlamaq üçün elə bu paneldə «PDF yüklə»ni basın.",
        ),
        "sillabus syllabus pdf yüklə plan tələbə mövzu həftə",
        ("is_student",),
    ),
    (
        "published-paper-score",
        "Kağız imtahanının balı yazılıb. Tələbə onu nə vaxt görə bilər?",
        "İmtahan nəticələri",
        "exam-score-entry",
        "İmtahan balının daxil edilməsini aç",
        "paper",
        (
            "İmtahan balının daxil edilməsi ekranında qrupu, fənni və imtahan növünü yoxlayın.",
            "«Siyahını yenilə»ni basın. Tələbənin sətrində balın həqiqətən yazıldığını tutuşdurun.",
            "İmtahan növünün altında təşkilat üçün göstərilən görünmə müddətini oxuyun. Balı sistemə yazmaq və tələbəyə açmaq ayrı vaxtlarda baş verə bilər.",
        ),
        "imtahan nəticə açıqlanma gecikmə final balı kağız nə vaxt",
        (),
    ),
)
EXTERNAL_ROUTES["language-place"] = "registrar:language_cohorts"
EXTERNAL_ROUTES["language-group-create"] = "registrar:language_cohorts"

OPERATIONS += (
    (
        "request-transcript",
        "Rəsmi transkript və ya arayış üçün necə müraciət edim və sənədi haradan götürüm?",
        "Transkript və sənədlər",
        "my-results",
        "Nəticələrimi aç",
        "request-transcript",
        (
            "Transkript üçün «Nəticələrim»də «Transkript sorğusu göndər»i basın. Açılan formada «Transkript sorğusu» əvvəlcədən seçilir.",
            "Təhsil, hərbi və ya bank arayışı üçün «Müraciətlərim»də «Yeni müraciət»i açın və «Arayış sorğusu»nu seçin.",
            "Mövzunu və hansı sənədə ehtiyacınız olduğunu yazın. Formada sorğunun ünvanlandığı şöbəni və cavab müddətini yoxlayıb «Müraciəti göndər»i basın. Açılan kartda müraciətin nömrəsi və statusu görünür.",
            "Cavaba baxmaq üçün «Müraciətlərim»də «Hamısı»nı seçib həmin müraciəti açın. Cavab yazışmada görünür. Şöbə PDF sənədi əlavə edibsə, faylın adını basıb yükləyin.",
        ),
        "transkript tələbə rəsmi arayış sənəd pdf akademik nəticə sifariş",
        ("is_student", "can_create_support"),
    ),
)

OPERATIONS += (
    (
        "teacher-load-hours",
        "Şəxsi dərs yükümdə görünən saatı sillabusun planı ilə necə tutuşdurum?",
        "Dərs yüküm",
        "my-workload",
        "Dərs yükümü aç",
        "teacher-load-read",
        (
            "Şəxsi yükünüzdə fənni, dövrü və sizə ayrılan fəaliyyət saatını tapın. Sillabusdakı həftəlik saat isə bir tələbənin keçəcəyi dərsi göstərir.",
            "Məsələn, 15 həftədə hər həftə 2 saat mühazirə və 2 saat seminar bir tələbəyə 60 saat edir. Bir ümumi mühazirə axını və iki tam ayrı seminar yarımqrupu üçün kafedranın yükü 90 saatdır.",
            "Şəxsi yükünüzdə bu 90 saatdan yalnız sizə təyin olunan hissə göstərilməlidir. Eyni seminarı iki müəllim öz aralarında paylaşırsa, hər müəllimin təyinatını və cəmi ayrıca tutuşdurun.",
        ),
        "60 90 yük bölgüsü 30 mühazirə seminar sillabus plan saatım fərq yarımqrup",
        (),
    ),
)


OPERATIONS += (
    (
        "faq-video-editor",
        "FAQ video dərsini necə əlavə edim, dəyişdirim və ya kataloqdan çıxarım?",
        "Video dərslərin idarə edilməsi",
        "faq",
        "Video dərsləri idarə et",
        "faq-video-editor",
        (
            "«Video dərsləri idarə et» ekranında «Video dərsi əlavə et» düyməsini basın. Sualı, mövzunu və addımları daxil edin. Ən azı bir rol seçin, yaxud «Bütün rollar» seçimini təsdiqləyin. MP4 videonu və varsa ona uyğun WebVTT subtitrini seçin.",
            "«Videoda göstərilən əməliyyatlar» sahəsində dərsin öyrətdiyi əməliyyatları seçin. «Bütün rollar» seçilsə də, dərs yalnız bu əməliyyatların hamısına icazəsi olanlara görünür. Əlavə icazə tələb etməyən dərs üçün «Ümumi təlimat» seçin.",
            "Fəsilləri hər sətirdə başlanğıc vaxtı və adla yazın. Dərsi saxlayın və uyğun rolun kabinetində fəsil keçidini yoxlayın.",
            "Videonu yeniləmək üçün dərsi redaktorda açıb əvəzedici faylı saxlayın. Sistemlə gələn dərsi təşkilatın kataloqundan çıxarıb sonra ilkin formasına bərpa edə bilərsiniz. Əlavə etdiyiniz dərsi siləndə onu yenidən yükləmək lazım gəlir.",
        ),
        "RİM FAQ redaktor video dəyişmək silmək yeni fayl MP4 WebVTT subtitr fəsil rol auditoriya",
        ("can_manage_faq_videos",),
    ),
)
