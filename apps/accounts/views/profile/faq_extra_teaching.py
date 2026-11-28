"""Tədris, jurnallar, dərs yükü, imtahanlar və müəllim işləri."""

TEACHING = {
    "question-bank": (
        "Fənnim üçün yeni sual bankını necə yaradım?",
        (
            "«Sual Bankı»nda «Yeni sual bankı» seçib fənni, təyinatı, formatı və dili göstərin. Banka tanınan ad "
            "verin.",
            "«Bank yarat» düyməsini basın. Yaranan banka keçib seçdiyiniz formata uyğun test və ya yazılı "
            "sualları əlavə edin.",
        ),
        "bank sual əlavə et müəllim test yazılı final midterm",
        "M00-00-muellim-icmal",
        170,
    ),
    "question-submissions": (
        "İmtahan sualları geri qaytarılıbsa səbəbi necə öyrənim?",
        (
            "«Sual göndərişləri»ndə fənnin göndərişini tapın. «Göndərişin yolu» hissəsində son hadisəni, baxan "
            "şəxsi və qeydini oxuyun.",
            "Qeyddə istənilən dəyişiklikləri sual dəstinə tətbiq edin və yenidən göndərin. Yeni göndəriş "
            "hadisəsini tarixçədən yoxlayın.",
        ),
        "sual göndərişi müəllim imtahan mərkəzi qaytarılıb tarixçə",
        "M00-00-muellim-icmal",
        181,
    ),
    "manage-appeals": (
        "İmtahan Mərkəzi apellyasiya üzrə qərarı necə verir?",
        (
            "İmtahan və ya tələbə üzrə süzün, müraciəti açıb etiraz edilən sualları, səbəbi və göstərilən "
            "məlumatları yoxlayın.",
            "Hər müraciət üzrə uyğun qərarı seçin, tələbəyə izah yazın və tətbiq edin. Qərarın və varsa yeni "
            "balın müraciətin detalında göründüyünü yoxlayın.",
        ),
        "apellyasiya qərarı qəbul qismən qəbul rədd yeni bal imtahan mərkəzi",
        "I00-00-imtahan-icmal",
        127,
    ),
    "my-schedule": (
        "Şəxsi cədvəldə fənnin hansı həftəyə düşdüyünü necə yoxlayım?",
        (
            "«Dərs cədvəli»ndə tədris ili və yarımili yoxlayın. «Bu həftə» və «Gələn həftə» göstəricilərində ÜST "
            "və ALT həftəni tutuşdurun.",
            "Günün sütununda dərs saatının sətrini tapın. Xanada fənni, dərs növünü və göstərilən qrup və ya "
            "müəllimi yoxlayın.",
        ),
        "şəxsi cədvəl ÜST ALT həftə dərs saat müəllim tələbə",
        "M06-01-sexsi-cedvel",
        0,
    ),
    "my-journal": (
        "Jurnalda i/e, q/b və qalan qayıb saatını necə oxuyum?",
        (
            "«Elektron jurnal»da fənnin adına basın. «Qayıb» kartında yazılan qayıbı və limiti oxuyun. Qalanı "
            "hesablamaq üçün qeyd edilən qayıbı limitdən çıxın.",
            "Aşağı sürüşdürüb «Dərs tarixçəsi»nə keçin. i/e iştirak, q/b isə qayıb deməkdir. Dərsin sətrinə "
            "bassanız, həmin günün iştirak qeydi və balı ayrıca açılır.",
        ),
        "iştirak qayıb ie qb i/e q/b qalıq limit aşağı sürüşdür davamiyyət",
        "T03-01-qiymet-jurnal",
        38,
    ),
    "journal-close": (
        "Semestr jurnallarını bağlamazdan əvvəl əhatəni necə yoxlayım?",
        (
            "Tədris ili və semestri seçin. «Əhatə»də bütün universitet, fakültə və ya kafedranı müəyyənləşdirib "
            "«Önizləməni yenilə» düyməsini basın.",
            "Cəmi, açıq və bağlı jurnalların sayını yoxlayın. Vaxtı əvvəlcədən bildirmək üçün «Bağlanma "
            "xəbərdarlığı», qərarı icra etmək üçün «Bu əhatədə jurnalları bağla» əməlini seçin.",
        ),
        "jurnal bağlanması semestr kilidlə xəbərdarlıq əhatə önizləmə",
        "",
        0,
    ),
    "schedule-manage": (
        "Qrupun həftəlik cədvəlinə yeni dərs saatını necə əlavə edim?",
        (
            "«Cədvəl idarəetməsi»ndə semestri və qrupu seçin. Günün sütununda lazım olan saatın boş xanasına " "basın.",
            "Açılan formada fənni, dərs növünü və həftəni göstərin. Toqquşma xəbərdarlığını yoxlayın və "
            "saxladıqdan sonra dərsin seçdiyiniz xanada göründüyünü təsdiqləyin.",
        ),
        "cədvəl idarəetməsi slot boş xana dərs əlavə et həftə RİM",
        "R01-02-cedvele-ders",
        0,
    ),
    "teaching-handover": (
        "Fənnin jurnalını başqa müəllimə necə təhvil verim?",
        (
            "«Fənn təhvili»ndə hazırkı müəllimi seçin. Təhvil veriləcək fənn və qrupları işarələyib yeni müəllimi "
            "göstərin.",
            "Səbəbi yazıb seçimi yoxlayın və «Təhvil ver» əməlini təsdiqləyin. Əvvəlki qeydlərin müəllifi "
            "tarixçədə saxlanılır.",
        ),
        "fənn təhvili müəllim dəyişmə jurnal sahibliyi tarixçə",
        "R02-01-fenn-tehvili",
        0,
    ),
    "syllabus-list": (
        "Fənnin sillabusunun təsdiq vəziyyətini necə tapım?",
        (
            "«Sillabuslar»da fənnin adını və ya kodunu yazın. Tədris ilini, semestri və lazım gəlsə müəllif və ya "
            "dərs deyən müəllimi seçin.",
            "Fənnin sətrində qaralama, təsdiqdə və ya təsdiqlənmiş vəziyyətini oxuyun. Eyni fənnin bir neçə qeydi "
            "varsa, qrupunu və müəllifini tutuşdurub uyğun sillabusu açın.",
        ),
        "sillabus siyahısı təsdiq fənn müəllif semestr status",
        "M00-00-muellim-icmal",
        154,
    ),
    "syllabus-editor": (
        "Sillabus qaralamasını necə saxlayıb sonra davam edim?",
        (
            "Fənnin jurnalında «Sillabus yarat» düyməsi ilə redaktoru açın. «Təsvir və məqsəd» hissəsini doldurun "
            "və «Qaralama saxla» əməlini seçin.",
            "Saxlanma vəziyyətini yoxlayın. Növbəti dəfə eyni jurnalda «Qaralamanı tamamla» düyməsi sizi həmin "
            "sillabusun redaktoruna qaytarır.",
        ),
        "sillabus redaktoru qaralama davam et məqsəd yadda saxla",
        "M02-02-sillabus-duzelis",
        0,
    ),
    "syllabus-review": (
        "Sillabusu müəllimə konkret bölmə üzrə düzəlişə necə qaytarım?",
        (
            "«Sillabus təsdiqi»ndə «Təsdiq növbəsi»ni açın. Fənn, müəllim və statusla uyğun sillabusu seçin, "
            "bölmələri və dəyişiklikləri yoxlayın.",
            "«Düzəliş üçün geri qaytar»ı seçin. Düzəliş tələb olunan bölmələri və rəyinizi göstərin, sonra "
            "əməliyyatı təsdiqləyin.",
        ),
        "kafedra sillabus təsdiqi rəy düzəliş geri qaytar bölmələr",
        "",
        0,
    ),
    "question-chair-review": (
        "Kafedra müdiri final suallarını necə təsdiqləyir və ya qaytarır?",
        (
            "«Sual təsdiqi»ndə gözləyən göndərişi tapıb «Bax və qərar ver» seçin. Sualları və düzgün cavabları "
            "nəzərdən keçirin.",
            "Uyğundursa «Təsdiqlə» seçin. Dəst İmtahan Mərkəzinə gedir. Düzəliş lazımdırsa səbəbi yazıb müəllimə "
            "qaytarın.",
        ),
        "sual təsdiqi kafedra müdiri sual dəsti final qərar",
        "I00-01-sual-yolu",
        104,
    ),
    "workload-distribution": (
        "Kafedra müəllimə mühazirə və seminar saatlarını necə bölür?",
        (
            "Fənnin kartında qrup və semestri yoxlayın. Mühazirə, seminar və laboratoriya üzrə plan, bölünmüş "
            "saat və qalıq göstəricilərini müqayisə edin.",
            "Fəaliyyət növü üçün müəllimi və ayrılan saatı seçin. Müəllimin norması ilə cəmi tutuşdurub qalıq "
            "saatlara yenidən baxın. Bölgü hazırdırsa onu təsdiqləyin.",
        ),
        "kafedra yük bölgüsü müəllim saat vakant qalıq norma",
        "K00-01-yuk-bolgusu",
        0,
    ),
    "my-workload": (
        "Müəllim kimi illik yükümə necə etiraz bildirim?",
        (
            "«Dərs yüküm»də ili seçin. Fənn və qrup sətirlərində mühazirə, seminar və laboratoriya saatlarını "
            "illik cəm və norma ilə müqayisə edin.",
            "Uyğunsuzluq varsa «Etiraz bildir» düyməsi ilə fənni, səhv saatı və gözlədiyiniz düzəlişi yazıb "
            "göndərin. Cavabı «Etirazlarım»da izləyin.",
        ),
        "dərs yüküm müəllim etiraz norma saat kafedra",
        "M00-00-muellim-icmal",
        131,
    ),
    "workload-center": (
        "Tədris şöbəsi illik yükü Excel faylından necə gətirir?",
        (
            "«Dərs yükü mərkəzi»ndə düzgün tədris ilinin tapşırığını seçin. Fayl görünüşündə Excel faylını "
            "yükləyib «Faylı oxu» düyməsini basın.",
            "Önizləmədə sətir və cəmi saat sayını, uyğunlaşdırılan və mətn kimi qalan adları yoxlayın. "
            "Gözlədiyiniz nəticə alındıqda «İdxal et» əməlini seçin.",
        ),
        "tədris şöbəsi yük faylı Excel idxal tapşırıq önizləmə",
        "TS00-00-tedris-icmal",
        27,
    ),
    "workload-visa": (
        "Tyutor yük sətrinə iradını necə göndərir?",
        (
            "«Yük vizası»nda seçilən ili və sizə təqdim edilmiş fənn sətrini yoxlayın. Keçmiş ilin arxiv görünüşü "
            "yalnız oxunur.",
            "«İrad bildir» düyməsini basıb şərhdə fənni və dəqiqləşdiriləcək yükü göstərin. «İradı göndər» "
            "düyməsindən sonra «Mənim hərəkətlərim»də qərarı və tarixi yoxlayın.",
        ),
        "tyutor viza yük irad şərh tarixçə",
        "TY00-00-tyutor-icmal",
        85,
    ),
    "workload-approval": (
        "Dekanlıq səhv saat göstərilən yük sətrini necə qaytarır?",
        (
            "«Yük təsdiqi»ndə fakültəyə düşən sətirləri açın. Kafedra, ixtisas, saat və kreditləri yoxlayıb geri "
            "göndəriləcək sətirləri seçin.",
            "«Seçilmiş sətirləri qaytar» əməliyyatında qaytarma səbəbini yazıb təsdiqləyin. Qərar tarixçəsini "
            "«Hərəkət jurnalı»ndan yoxlayın.",
        ),
        "dekan dekanlıq yük təsdiqi qaytarma səbəbi fakültə",
        "D00-00-dekanliq-icmal",
        97,
    ),
    "workload-overview": (
        "Vakant saat və normadan artıq yük hansı kafedradadır?",
        (
            "«Yük — ümumi baxış»da lazım olan dövrü seçin. Fakültə və kafedra üzrə planı, bölünmüş yükü və vakant "
            "saatları tutuşdurun.",
            "«Diqqət tələb edən kafedralar» və «Təsdiq axını» hissələrində bölgünün vəziyyətini yoxlayın. "
            "Qaytarılmış və ya hələ göndərilməmiş bölgüləri buradan ayırd edə bilərsiniz.",
        ),
        "yük icmal vakant saat norma aşımı monitorinq təsdiq",
        "K00-00-kafedra-icmal",
        85,
    ),
    "chair-profile": (
        "Kafedranın müəllimlərinə düşən illik yükü harada müqayisə edim?",
        (
            "«Kafedra profili»ndə seçilmiş kafedranın adını və müdirini yoxlayın. Müəllim siyahısında ştat növü, "
            "ştat payı və vəzifəyə baxın.",
            "«İllik saat», «Norma» və «Yük vəziyyəti» sütunlarını eyni müəllimin sətrində müqayisə edin. Həmin "
            "kafedrada və kənar kafedradan dərs deyənləri ayırd edin.",
        ),
        "kafedra profili müəllim norma illik yük ştat payı",
        "K00-00-kafedra-icmal",
        197,
    ),
    "lessons-log": (
        "Cədvəldə olub jurnala yazılmayan dərsləri necə tapım?",
        (
            "«Keçilmiş dərslər»də tarix aralığını və əhatənizdəki müəllimi seçin. Keçilmiş saatları və dərs "
            "növlərini yoxlayın.",
            "Sarı xəbərdarlıqda cədvəldə olan, jurnala düşməyən dərsləri görəcəksiniz. Qrup və tarixi tutuşdurun. "
            "Cari seçim üçün «Hesabatı yüklə» əməlindən istifadə edə bilərsiniz.",
        ),
        "monitorinq keçilmiş dərslər aylıq dərs hesabatı CSV jurnal yazılmayıb",
        "MN00-00-monitorinq-icmal",
        13,
    ),
    "subject-folders": (
        "Fənn qovluğunda dərs materialını uyğun mövzuya necə əlavə edim?",
        (
            "«Fənn qovluqları»nda fənnin qovluğunu açıb «Material əlavə et» düyməsini basın. «Fayl» növünü seçin, "
            "başlığı yazın və aid olduğu mövzunu göstərin.",
            "Faylı seçin. Tələbələr onu dərhal görməlidirsə «Dərhal dərc et» seçimini işarələyib saxlayın. "
            "Mövzunun altında «Dərc edilib» statusunu yoxlayın.",
        ),
        "fənn qovluğu müəllim mühazirə materialı sənəd mövzu",
        "M07-01-qovluqa-material",
        0,
    ),
    "subject-folder-review": (
        "Müəllim ev tapşırığını tələbəyə qeydlə necə qaytarır?",
        (
            "«Tapşırıq yoxlaması»nda fənn, qrup və ya göndəriş statusu ilə işi tapıb «Bax» düyməsini basın. "
            "Göndərilən faylı və ya cavabı oxuyun.",
            "«Rəylə qaytar» seçin və tələbənin nəyi dəyişməli olduğunu yazın. Qaytarma rəyi ən azı 5 simvol "
            "olmalıdır. Göndərişin yeni vəziyyətini siyahıda yoxlayın.",
        ),
        "ev tapşırığı yoxlama müəllim rəylə qaytar sərbəst iş təqdim",
        "M05-01-ev-tapsirigi-yoxlama",
        0,
    ),
    "teaching-appeals": (
        "Fənnim üzrə verilmiş apellyasiyanın qərarını müəllim kimi harada izləyim?",
        (
            "«Fənnimə aid apellyasiyalar»da fənnə və vəziyyətə görə siyahını daraldın. Müvafiq imtahan və "
            "müraciət sətrini açın.",
            "Etiraz olunan sualları, cari statusu və verilmiş qərarı oxuyun. Yekun qərarı İmtahan Mərkəzi verir.",
        ),
        "müəllim fənnimə aid apellyasiya status qərar etiraz",
        "M00-00-muellim-icmal",
        222,
    ),
    "unit-subject-folders": (
        "Monitorinq və ya kafedra əməkdaşı fənn materiallarını necə yoxlayır?",
        (
            "Strukturunuza aid fənn qovluqlarında uyğun kafedranı və fənni tapıb «Tam baxış»a keçin.",
            "Mövzuların altında yerləşdirilmiş materialları açıb məzmunu yoxlayın. Bu görünüş oxumaq üçündür, "
            "qaralama və əhatənizdən kənar qovluqlar burada görünmür.",
        ),
        "monitorinq kafedra materialları laborant fənn qovluqları baxış",
        "L00-00-laborant-icmal",
        105,
    ),
    "journal-removals": (
        "Tələbənin jurnaldan çıxarılma səbəbini və sonradan bərpa olunmasını necə yoxlayım?",
        (
            "Jurnaldan çıxarılmalar siyahısında tələbə, fənn və ya səbəb üzrə süzgəcləri tətbiq edin. Tarixlə "
            "müəllimin və jurnalın uyğunluğunu yoxlayın.",
            "«Səbəb», «Qeyd», «Çıxaran» və «Bərpa olunub» sütunlarını oxuyun. Süzülmüş siyahının surəti "
            "lazımdırsa «Excel-ə ixrac» əməlini seçin.",
        ),
        "jurnaldan çıxarılma bərpa tarixçə səbəb tələbə hesabat",
        "",
        0,
    ),
    "lab-groups": (
        "Laboratoriya jurnalında tələbələri Lab-1 və Lab-2 qruplarına necə bölüm?",
        (
            "«Lab qrupları»nda laboratoriya saatı olan fənnin jurnalını seçin. Mövcud qrupları və hələ bölünməmiş "
            "tələbələri yoxlayın.",
            "Laboratoriya qruplarını yaradın, tələbələri seçib uyğun qrupa köçürün. Hər qrupdakı tələbə sayını "
            "yoxlayın.",
        ),
        "laborant lab qrupları laboratoriya yarımqrup tələbə bölünməsi",
        "R07-01-lab-qruplari",
        0,
    ),
}
