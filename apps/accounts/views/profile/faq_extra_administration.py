"""Təşkilat, hesablar, icazələr, maliyyə və inzibati nəzarət."""

ADMINISTRATION = {
    "journal-watch": (
        "Jurnalda seçdiyim şəxslə bağlı dəyişiklikləri necə izləyim?",
        (
            "Sistem tənzimləmələrində «Nəzarət»i açın. Bildiriş istəyirsinizsə, e-poçt ünvanını əlavə edin və məktubdakı keçiddə ünvanı təsdiqləyin.",
            "Qeydi yazan şəxsi və ya qeydi izlənilən tələbəni seçin. Adı ilə axtarın, hadisələri və təsdiqlənmiş ünvanları işarələyib qaydanı saxlayın. Fərqli ünvanlara fərqli hadisələr üçün ayrıca qaydalar yaradın.",
            "Aktiv dərsdə ilkin xətdən sonra iştirak, qayıb və ya bal yazılanda seçdiyiniz hadisəni jurnalda tapın. Vaxtı, fənni, qeydi kimin dəyişdiyini, əvvəlki və yeni dəyəri yoxlayın.",
            "İlk bildiriş hadisə saxlananda göndəriş növbəsinə düşür. Sonrakı dəyişikliklər eyni ünvan üçün beş dəqiqəlik xülasəyə yığılır. Nəzarəti dayandırmaq üçün qaydanı redaktə edin.",
        ),
        "nəzarət izləmə iə qb bal e-poçt xəbərdarlıq jurnal dəyişiklik",
        "",
        0,
    ),
    "role-assignment": (
        "Əməkdaşı təşkilata əlavə edəndə rolu necə təyin edim?",
        (
            "Təşkilatı və istifadəçini seçin. Yeni üzvlükdürsə təyin olunacaq rolu, mövcud üzvlükdürsə dəyişəcək "
            "rolu göstərin.",
            "Təsdiq pəncərəsində istifadəçini, təşkilatı və rolu tutuşdurun. Dəyişikliyi təsdiqlədikdə əməliyyat "
            "audit jurnalına yazılır.",
        ),
        "HR rol təyinatı təşkilat üzvlüyü əməkdaş rol dəyiş",
        "HR00-00-hr-icmal",
        56,
    ),
    "student-organization-management": (
        "Təşkilat üzvünün bütün rollarını və bölməsini necə yoxlayım?",
        (
            "Təşkilatın üzvlər siyahısında şəxsi tapıb «Üzv kartı»nı açın. Burada həmin təşkilatdakı rolları, "
            "bölməni və üzvlüyün vəziyyətini yoxlayın.",
            "Üzvlüyü bitirmək səlahiyyətiniz varsa «Təşkilatdan çıxar» seçin. Səbəbi yazıb təsdiqdən əvvəl "
            "seçilmiş şəxsi və təşkilatı yenidən yoxlayın.",
        ),
        "üzv kartı üzvlük idarəetmə təşkilatdan çıxar inzibatçı",
        "",
        0,
    ),
    "permission-editor": (
        "Bir rola konkret icazəni necə əlavə edim?",
        (
            "Redaktə ediləcək rolu seçin. «İcazə axtar» sahəsinə açarı, adı və ya əməliyyatın izahını yazın.",
            "Tapılan sətirdə «Əlavə et» düyməsini basıb vəziyyətin «Aktiv» olduğunu yoxlayın. Bir neçə icazə üçün "
            "sətirləri seçib «Seçilənləri əlavə et» düyməsindən istifadə edin.",
        ),
        "icazə RBAC rol hüquq delegasiya açar admin",
        "",
        0,
    ),
    "manage-roles": (
        "Üzvün digər rollarını saxlayaraq əlavə rolu necə verim və ya geri alım?",
        (
            "Təşkilatı, üzvü və tələb olunan rolu seçib «Rol ver» düyməsini basın. Bu əməl şəxsin mövcud "
            "rollarına yeni rol əlavə edir.",
            "Bir rolu dayandırmaq üçün həmin üzvlüyü seçib «Rolu geri al» düyməsini basın. Təsdiqdə istifadəçini "
            "və geri alınan rolu yoxlayın.",
        ),
        "əlavə rol ver çoxrol kadr rolu geri al üzvlük",
        "HR00-00-hr-icmal",
        65,
    ),
    "category-management": (
        "Mövcud alt kateqoriyanın adını necə dəyişdirim?",
        (
            "Kateqoriyanı adı ilə axtarın və əsas kateqoriyanın altında «Alt kateqoriyaları göstər» düyməsini "
            "basın.",
            "Lazım olan sətirdə redaktəni açın, dil üzrə adı düzəldib «Yadda saxla» düyməsini basın. Alt "
            "kateqoriyanın doğru əsas kateqoriya altında qaldığını yoxlayın.",
        ),
        "bloq kateqoriya redaktə alt kateqoriya AZ EN RU TR",
        "",
        0,
    ),
    "create-category": (
        "Yeni alt kateqoriyanı əsas kateqoriyaya necə bağlayım?",
        (
            "Yeni kateqoriya formasında ad sahələrini doldurun. Alt kateqoriya yaradırsınızsa, aid olduğu üst "
            "kateqoriyanı seçin.",
            "«Kateqoriya yarat» düyməsini basın. «Kateqoriyaları idarə et» siyahısında seçdiyiniz əsas "
            "kateqoriyanın altını açıb yeni adı yoxlayın.",
        ),
        "kateqoriya yarat əsas üst alt kateqoriya paylaşım",
        "",
        0,
    ),
    "superadmin-org-features": (
        "Bir təşkilat üçün kabinet modulunu necə açım və ya bağlayım?",
        (
            "«Təşkilat xüsusiyyətləri»ndə təşkilatın adını və kodunu yoxlayın. Həmin təşkilatın «Kabinet "
            "modulları» hissəsinə keçin.",
            "Dəyişəcək modulu tapıb vəziyyətini yeniləyin. Bağlı modul həmin təşkilatın istifadəçilərinin "
            "kabinetində gizlədilir.",
        ),
        "superadmin modul xüsusiyyət təşkilat kabinet görünürlük bayraq",
        "",
        0,
    ),
    "superadmin-organizations": (
        "Təşkilatın vəziyyətini və aktiv üzvlərini haradan yoxlayım?",
        (
            "«Bütün təşkilatlar» cədvəlində adı, tipi və sahibi ilə doğru təşkilatı müəyyənləşdirin.",
            "Status və aktiv üzv sayını yoxlayın. Təşkilat haqqında əlavə məlumat üçün «Detallar», sizin "
            "girişiniz olan təşkilatın üzvlük siyahısı üçün «Üzvlər» keçidini açın.",
        ),
        "təşkilatlar sahib üzv sayı superadmin tenant status",
        "",
        0,
    ),
    "superadmin-users": (
        "Bloklanmış hesabı idarəetmə siyahısında necə tapım?",
        (
            "İstifadəçi idarəetməsində adı, istifadəçi adını və ya e-poçt ünvanını yazın. Təşkilat və bloklanmış "
            "vəziyyət üzrə nəticələri daraldın.",
            "Uyğun şəxsin hesabını açıb statusunu və təşkilatını tutuşdurun. Filtrlənmiş nəticə sayını ümumi "
            "istifadəçi sayından ayrıca oxuyun.",
        ),
        "superadmin bloklanmış hesab istifadəçi axtar silinmiş təşkilat",
        "",
        0,
    ),
    "rim-center": (
        "RİM mərkəzində eyniadlı hesabları necə ayırım?",
        (
            "Axtarışa şəxsin adını və soyadını, dəqiq istifadəçi adını və ya e-poçtunu yazın. Hesab növünü "
            "«Tələbələr», «Müəllimlər» və ya «Heyət» kimi daraldın.",
            "Nəticədə təşkilat, hesab növü və vəziyyəti tutuşdurub uyğun kartı açın. Görə biləcəyiniz "
            "əməliyyatları «Sizin səlahiyyətləriniz» hissəsindən yoxlayın.",
        ),
        "RİM mərkəzi hesab axtar istifadəçi bloklanmış heyət dəstək",
        "R00-00-rim-icmal",
        16,
    ),
    "account-password-reset": (
        "İstifadəçiyə müvəqqəti parolu necə verim?",
        (
            "«Parol və istifadəçi adı» bölməsində təşkilatı yoxlayın, istifadəçini dəqiq adı və ya ad-soyadı ilə "
            "tapın. Hesab sahibinin kimliyini dəqiqləşdirin.",
            "Doğru hesabın parolunu sıfırlamağı təsdiqləyin. Göstərilən müvəqqəti parolu birbaşa həmin "
            "istifadəçiyə çatdırın.",
        ),
        "parol sıfırla şifrəni unutdum müvəqqəti parol RİM",
        "R10-01-parol-sifirlama",
        0,
    ),
    "superadmin-ai": (
        "Süni intellekt funksiyalarının istifadə həddini necə təyin edim?",
        (
            "«AI Tənzimləmələri»ndə ümumi aktivlik vəziyyətini yoxlayıb «Limit və Büdcə» hissəsinə keçin.",
            "İstifadəçi limitini say və müddət kimi daxil edin. Məsələn, 100/1h saatda 100 sorğudur. Aylıq büdcə "
            "sahəsinin məlumat məqsədli olduğunu nəzərə alıb ayarı saxlayın.",
        ),
        "AI süni intellekt sorğu limiti büdcə model Gemini",
        "",
        0,
    ),
    "superadmin-exam-rooms": (
        "İmtahan zalına kompüterləri toplu necə əlavə edim?",
        (
            "Aktiv təşkilatı və aid olduğu zalı seçin. Kompüterlər üçün «Toplu əlavə (MAC siyahısı)» formasını "
            "açın.",
            "Siyahını formanın göstərdiyi qaydada daxil edib «Toplu əlavə et» düyməsini basın. Səhv sətirlər "
            "atlandıqda bildirişdəki səbəbi oxuyub həmin sətirləri düzəldin.",
        ),
        "imtahan zalı kompüter MAC ünvanı toplu əlavə idarəçi",
        "",
        0,
    ),
    "exam-center-pins": (
        "İmtahan Mərkəzində tələbənin fərdi PIN kodunu necə tapım?",
        (
            "«PIN axtarışı»nda tələbənin adını, soyadını və ya istifadəçi adını yazın. Tapılan şəxsi seçin.",
            "Təyin edilmiş imtahanların içində uyğun imtahanı tapın. «PIN verilib» və «PIN yoxdur» "
            "göstəricilərini yoxlayıb həmin imtahanın giriş məlumatına baxın.",
        ),
        "imtahan mərkəzi PIN unudulub giriş kodu tələbə axtarış",
        "I00-00-imtahan-icmal",
        76,
    ),
    "exam-center-stats": (
        "İmtahan nəticələrini qrup və fənn üzrə necə süzüm?",
        (
            "«İmtahan statistikaları»nda tədris ilini və semestri müəyyən edin. Fənn, qrup və lazım gəldikdə "
            "imtahan növünü seçin.",
            "Nəticələri süzüb uyğun tələbə və nəticə sətirlərini yoxlayın. Hesabata ehtiyac varsa həmin seçimlə "
            "Excel çıxarışını götürün.",
        ),
        "imtahan statistikası nəticə hesabat Excel qrup müəllim semestr",
        "I00-00-imtahan-icmal",
        199,
    ),
    "appeal-stats": (
        "Apellyasiyaların sayından konkret müraciətə necə keçim?",
        (
            "«Apellyasiya statistikası»nda ümumi göstəriciləri və nəticələr üzrə bölgünü nəzərdən keçirin.",
            "Siyahıda tələbə və imtahanı tutuşdurun. «Bax» düyməsi ilə lazım olan apellyasiyanı açıb onun "
            "təfərrüatlarını oxuyun.",
        ),
        "apellyasiya statistika etiraz say monitorinq qərar",
        "I00-00-imtahan-icmal",
        207,
    ),
    "kollokvium-windows": (
        "Müəllimin midterm balını yazması üçün vaxtı necə yoxlayım və uzadım?",
        (
            "Müvafiq dövrün bal yazma aralığını açın. Başlanma və bağlanma tarixlərini, həmçinin «Açıq», "
            "«Bağlanıb» və ya «Açılır» statusunu yoxlayın.",
            "Yalnız bir müəllimə əlavə vaxt lazımdırsa, həmin müəllim üçün «Əlavə gün ver» əmrindən istifadə edib "
            "verilən müddəti yoxlayın.",
        ),
        "midterm kollokvium pəncərə bal yazma müddəti əlavə gün",
        "I00-00-imtahan-icmal",
        157,
    ),
    "exam-score-entry": (
        "Kağız imtahanın ballarını XLSX ilə necə daxil edim?",
        (
            "Tədris ilini, semestri, qrupu, fənni və imtahan növünü seçin. Həmin seçimin şablonunu götürüb "
            "balları daxil edin.",
            "Doldurulmuş XLSX faylını yükləyin. Önizləmədə tələbələri, yeni balları və xəbərdarlıqları yoxlayın. "
            "Uyğun sətirləri təsdiqləyib sistemə yazın.",
        ),
        "kağız bal XLSX Excel yazılı imtahan midterm final köçürmə",
        "I00-02-kagiz-bali-xlsx",
        0,
    ),
    "legacy-grade-review": (
        "Köhnə sistemlə cari sistemdəki bal fərqinə necə baxım?",
        (
            "Tələbə, fənn və ya köhnə qeyd nömrəsi ilə sətri tapın. Xam mənbə balını canlı sistemdəki göstərici "
            "və «Niyə burada» izahı ilə müqayisə edin.",
            "Dəyər doğrudursa təsdiqləyin. Düzəliş əsaslıdırsa «Düzəlt» ilə yeni imtahan balını və səbəbi yazın. "
            "Dəqiqləşdirmə tamamlanmayıbsa «Mübahisəli» seçib səbəbini qeyd edin.",
        ),
        "köhnə sistem miqrasiya qiymət bal fərqi mübahisəli reyestr",
        "",
        0,
    ),
    "system-settings": (
        "Dəyişdirilmiş sistem ayarını ilkin qiymətinə necə qaytarım?",
        (
            "Tənzimləmələrdə ad, izah və ya açarla axtarın. Müvafiq qrupda cari və standart dəyəri müqayisə edin.",
            "Lazım olan ayar üçün «Standarta qaytar» seçin. «Yadda saxla» düyməsini basıb təsdiq pəncərəsində "
            "dəyişəcək dəyəri yoxlayın.",
        ),
        "sistem ayarları standart dəyər limit konfiqurasiya admin",
        "",
        0,
    ),
    "journal-hygiene": (
        "Jurnalda qalan uyğunsuz sətri qərardan əvvəl necə yoxlayım?",
        (
            "«Ayrılmış tələbələr», «Boş fənlər» və ya «Keçirilməyən fənlər» görünüşünü seçin. Qrup və semestr "
            "üzrə süzüb «Niyə burada» səbəbini oxuyun.",
            "Müvafiq sətirləri seçin və göstərilən əməliyyatın önizləməsində tələbəni, fənni və jurnalı "
            "tutuşdurun. Təsdiq edəcəksinizsə, ən azı 20 simvolla qərarın səbəbini yazın.",
        ),
        "jurnal təmizliyi boş fənn ayrılmış tələbə dondur bərpa qərar",
        "",
        0,
    ),
    "superadmin-contact-messages": (
        "Saytdan göndərilən əlaqə mesajına necə cavab verim?",
        (
            "Superadmin gələnlər qutusunda göndərənin adı, e-poçtu və ya mətnlə axtarış aparın. Mesajı açıb "
            "müraciət və əlavələrlə tanış olun.",
            "«Cavab» sahəsinə mətni yazıb «Cavabı göndər» düyməsini basın. Son cavab cəhdində çatdırılmanın "
            "«Göndərildi» olduğunu yoxlayın.",
        ),
        "müştəri mesajı əlaqə forması gələnlər e-poçt çatdırılma superadmin",
        "",
        0,
    ),
    "system-monitoring": (
        "Problemin serverdə, bazada və ya tətbiqdə olduğunu necə araşdırım?",
        (
            "«Ümumi vəziyyət»də xəbərdarlıq və problem olan göstəricini müəyyənləşdirin. Son yenilənmə vaxtını "
            "yoxlayın.",
            "Uyğun «Server», «Konteynerlər», «Tətbiq» və ya «Baza» bölməsinə keçib «Ətraflı» məlumatı oxuyun. "
            "Vaxtı uyğun gələn hadisələri «Alertlər» və «İnsidentlər»də tutuşdurun.",
        ),
        "monitorinq server konteyner baza xəbərdarlıq log insident",
        "",
        0,
    ),
    "statistics": (
        "Roluma aid statistikanın hansı dövrü və təşkilatı əhatə etdiyini necə bilim?",
        (
            "Statistika başlığındakı əhatəni yoxlayın. Təşkilat seçimi sizə açıqdırsa lazımi təşkilatı seçin və "
            "dövr süzgəcini tətbiq edin.",
            "Göstəriciləri seçilən əhatə üzrə oxuyun. «Xülasə yarat» düyməsi görünürsə, ekrandakı göstəricilər "
            "əsasında xülasəni açın.",
        ),
        "statistika rol üzrə hesabat təşkilat dövr cəhd xülasə",
        "",
        0,
    ),
    "org-structure": (
        "Yeni kafedranı düzgün fakültənin altında necə yaradım?",
        (
            "«Fakültə və kafedralar»da əvvəlcə aid olduğu fakültəni yoxlayın. Fakültə hələ yoxdursa, «Yeni "
            "fakültə yarat» forması ilə əlavə edin.",
            "«Yeni kafedra yarat» hissəsində fakültəni seçin, kafedranın adını yazıb «Kafedra yarat» düyməsini "
            "basın. Cədvəldə fakültə ilə əlaqəni yoxlayın.",
        ),
        "universitet strukturu fakültə kafedra yarat aidiyyət",
        "",
        0,
    ),
    "org-faculties": (
        "Fakültəyə dekanı necə təyin edim?",
        (
            "Fakültələr siyahısından doğru fakültəni seçin və «Dekan təyin et» pəncərəsini açın.",
            "Təyin ediləcək şəxsi seçib fakültənin adını yenidən tutuşdurun. «Təyin et» düyməsindən sonra "
            "fakültənin rəhbərini yoxlayın.",
        ),
        "fakültə dekan təyinatı rəhbər heyət struktur",
        "",
        0,
    ),
    "org-kafedras": (
        "Kafedra müdirini və kafedra müəllimini haradan təyin edim?",
        (
            "Kafedralar siyahısında fakültəni və kafedranı müəyyənləşdirin. Rəhbər üçün «Kafedra müdiri təyin et» "
            "seçib şəxsi təsdiqləyin.",
            "Müəllim heyətinə əlavə edirsinizsə, həmin kafedrada «Kafedraya müəllim əlavə et» düyməsindən "
            "istifadə edin və nəticəni «Heyət»də yoxlayın.",
        ),
        "kafedra müdir təyinat müəllim heyəti struktur",
        "",
        0,
    ),
    "org-overview": (
        "Təşkilata son qoşulanları və rol dəyişikliklərini necə izləyim?",
        (
            "Təşkilatın icmalında cari akademik dövrü və göstərilən əhatəni yoxlayın. «Rol paylanması» üzvlərin "
            "rollar üzrə sayını göstərir.",
            "«Son qoşulanlar»da yeni üzvlərə baxın. Konkret dəyişikliyi dəqiqləşdirmək üçün «Son "
            "dəyişikliklər»dən «Audit jurnalı»na keçin.",
        ),
        "təşkilat icmal son qoşulan üzv rol paylanması audit",
        "",
        0,
    ),
    "org-members": (
        "Təşkilatın üzvlər siyahısında konkret şəxsin kartını necə tapım?",
        (
            "Üzvlər siyahısında ad və ya istifadəçi adı ilə axtarıb rol və bölmə üzrə uyğun nəticəni seçin.",
            "Həmin şəxsin «Üzv kartı»nı açın. Təşkilatını, bölməsini və aktiv üzvlüyünü kartdakı məlumatlarla "
            "tutuşdurun.",
        ),
        "üzv siyahısı əməkdaş təşkilat struktur üzv kartı",
        "",
        0,
    ),
    "org-roles": (
        "Rolun kimlərə və hansı icazələrə aid olduğunu necə yoxlayım?",
        (
            "Təşkilatın rol kataloqunda sistem və ya xüsusi rolu tapın. Sətirdə üzv sayına və icazə göstəricisinə "
            "baxın.",
            "«Ətraflı» ilə rol məlumatını, «Üzvlər» ilə həmin roldakı şəxsləri açın. Dəyişiklik səlahiyyətiniz "
            "varsa «İcazələri redaktə et» keçidi görünür.",
        ),
        "rol kataloqu xüsusi sistem rolu üzvlər icazələr",
        "",
        0,
    ),
    "audit-log": (
        "Mübahisəli dəyişikliyi kimin və nə vaxt etdiyini necə tapım?",
        (
            "Audit jurnalında hadisəyə uyğun əməliyyat və tarix süzgəclərini tətbiq edin. Eyni əməliyyat çoxdursa "
            "hədəf və istifadəçi məlumatını tutuşdurun.",
            "Uyğun sətrin «Hadisə qeydi»ni açın. İcraçını, vaxtı və həmin hadisə üçün qeydə alınmış məlumatı "
            "yoxlayın.",
        ),
        "audit tarixçə əməliyyat kim dəyişib tarix izləmə",
        "R00-00-rim-icmal",
        130,
    ),
    "unit-exams": (
        "Fakültə və ya kafedranın imtahan cədvəli və nəticə xülasəsi haradadır?",
        (
            "Bölmənizə aid imtahanları süzüb uyğun fənn və qrupu tapın. Əhatəniz təyin edilməyibsə sistem bu "
            "barədə məlumat göstərir.",
            "İmtahanın detalını açın. «İmtahan haqqında» pəncərəsində cədvəli, qrupları, sualları və nəticə "
            "xülasəsini oxuya bilərsiniz.",
        ),
        "fakültə kafedra imtahanları qrup cədvəl baxış nəticə",
        "",
        0,
    ),
    "superadmin-org-inspector": (
        "Superadmin seçilmiş təşkilatın imtahan və nəticələrini necə yoxlayır?",
        (
            "Təşkilatı adı və ya qısa sistem adı ilə axtarıb açılan siyahıda seçin.",
            "«İmtahanlar», «Nəticələr» və ya «Sual bankları» vərəqinə keçin. Tapdığınız sətrin «Bax» düyməsi ilə "
            "müvafiq detalları yoxlayın.",
        ),
        "təşkilat inspektoru superadmin baxış imtahan nəticə bank",
        "",
        0,
    ),
    "hr-analytics": (
        "Ştat və kafedra üzrə müəllimlərin siyahısını necə çıxarım?",
        (
            "«Kadr analitikası»nda tədris ilini və kafedranı seçin. Ştat və ya əvəzçilik göstəricisinin kartına "
            "basanda siyahı həmin vəziyyətə görə süzülür.",
            "Süzülmüş siyahıdakı müəllimləri və «Fakültə və kafedralar üzrə ştat vahidləri» cədvəlini müqayisə "
            "edin.",
        ),
        "HR kadr analitikası ştat əvəzçilik elmi dərəcə vəzifə",
        "HR00-00-hr-icmal",
        21,
    ),
    "accounting": (
        "Mühasibatlıqda müəllimin aylıq plan və fakt hesabatını necə çıxarım?",
        (
            "Semestri, sonra hesabat ayını seçin. Müəllimə və ya kafedraya görə süzüb həmin dövrün plan, fakt və "
            "fərq sütunlarını müqayisə edin.",
            "Müəllimin sətrini açın, mühazirə, seminar və laboratoriya saatlarını yoxlayın. Excel çıxarışı "
            "seçdiyiniz dövr və süzgəclərə əsaslanır.",
        ),
        "maliyyə mühasib aylıq hesabat əməkhaqqı dərs saatı plan fakt Excel",
        "MH00-00-muhasib-icmal",
        12,
    ),
    "remote-journal-access": (
        "Əməkdaşa kənardan jurnal girişi necə verilir və geri alınır?",
        (
            "«Hesab əlavə et» hissəsində şəxsi adı, soyadı və ya istifadəçi adı ilə tapın. Hesabı və lazım olsa "
            "qeydi yoxlayıb «Əlavə et» əməlini təsdiqləyin.",
            "Verilmiş giriş siyahısında şəxsi, bölməni və icazəni kimin verdiyini yoxlayın. İcazə bitəndə həmin "
            "şəxsin sətrində «Geri al» seçib təsdiqləyin.",
        ),
        "kənardan jurnal evdən giriş RİM icazə əməkdaş uzaq giriş",
        "",
        0,
    ),
    "hr-contracts": (
        "HR əməkdaşın müqaviləsini necə qeydə alıb təsdiqə göndərir?",
        (
            "«Əmək müqavilələri»ndə «Müqavilə əlavə et» düyməsini seçin. Əməkdaşı, vəzifəni, ştatı və "
            "başlama-bitmə məlumatını daxil edib müqaviləni saxlayın.",
            "İşçiyə göndərmə əməlini yerinə yetirin. Müqavilənin sətrində göndərilmə və təsdiq vəziyyətini, "
            "əvvəlki əməliyyatları isə «Tarixçə»də yoxlayın.",
        ),
        "HR əmək müqaviləsi kadr ştat əməkdaş təsdiq tarixçə",
        "HR00-00-hr-icmal",
        12,
    ),
}
