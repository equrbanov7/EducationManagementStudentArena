"""Şəxsi kabinet, tələbə işləri, paylaşımlar və bildirişlər."""

CABINET = {
    "faq": (
        "Etdiyim əməliyyatın təlimatını kabinetdə necə tapım?",
        (
            "Axtarışa düymənin adını və ya etmək istədiyiniz işi yazın. Məsələn, «qayıb» yazanda davamiyyətlə "
            "bağlı suallar süzülür.",
            "Uyğun sualı açıb addımları oxuyun. «Videoya bax» keçidi olan sualda həmin əməliyyatın ekran yazısını "
            "izləyə bilərsiniz.",
        ),
        "kömək təlimat axtarış FAQ tez-tez verilən suallar",
        "",
        0,
    ),
    "dashboard": (
        "Bu gün hansı dərsim var və cari ballarımı harada görə bilərəm?",
        (
            "Tələbə kabinetinin ana səhifəsində bugünkü və növbəti dərslərə baxın.",
            "Fənnin kartında giriş balını və qayıb saatını oxuyun. Qayıb saatının yanında həmin fənn üzrə icazə "
            "verilən limit göstərilir.",
        ),
        "ana səhifə xülasə bugünkü dərs davamiyyət giriş balı",
        "T00-01-telebe-icmal",
        11,
    ),
    "profile-info": (
        "Təşkilatdan gələn üzvlük dəvətinə necə cavab verim?",
        (
            "Profil məlumatlarınızda «Təşkilat dəvətləri» hissəsini tapın. Təşkilatı, sizi dəvət edən şəxsi və "
            "təklif olunan rolu yoxlayın.",
            "Qoşulmaq üçün «Qəbul et», dəvəti geri çevirmək üçün «Rədd et» seçin. Mövcud təşkilatdan çıxmaq tələb "
            "olunursa, kabinet bunu dəvətin yanında göstərir.",
        ),
        "üzvlük dəvəti rol qəbul təşkilat profil dəvət edən",
        "",
        0,
    ),
    "notifications": (
        "Oxumadığım bildirişi necə tapım və oxunmuş işarələyim?",
        (
            "«Oxunmamış» süzgəcini seçin. Mesaj çoxdursa, açar söz yazın və ya bildiriş növünü seçin.",
            "Bildirişi açıb mətnini və varsa keçidini oxuyun. Siyahının hamısını işlədikdən sonra «Hamısını "
            "oxunmuş işarələ» düyməsindən istifadə edin.",
        ),
        "zəng bildiriş oxunmamış bildirişlər mesaj axtar",
        "",
        0,
    ),
    "publish-notification": (
        "Qrupuma dərs dəyişikliyi haqqında bildiriş necə göndərim?",
        (
            "Alıcı qrupları seçin və başlıq yazın. Mətndə fənni, dərsin tarixini və dəyişən məlumatı göstərin.",
            "Lazım olsa keçid və ya fayl əlavə edin. Göndərməzdən əvvəl qrup siyahısını yoxlayıb bildirişi "
            "göndərin.",
        ),
        "müəllim qrup mesaj xəbər elan auditoriya dəyişməsi",
        "M00-00-muellim-icmal",
        236,
    ),
    "create-post": (
        "Məqaləni hazırlayıb müəllim təsdiqinə necə göndərim?",
        (
            "Başlığı və kateqoriyanı seçin. Qısa məzmunu xülasə sahəsinə, məqalənin tam mətnini isə «Məzmun» "
            "sahəsinə yazın.",
            "Lazımdırsa şəkil əlavə edin və «Məqaləni yayımla» düyməsini basın. Təsdiq tələb olunan paylaşım "
            "avtomatik baxış növbəsinə göndərilir.",
        ),
        "məqalə post paylaşım yazı müəllim təsdiqi kateqoriya",
        "",
        0,
    ),
    "posts": (
        "Yazıma düzəliş istənilib. Rəyi haradan oxuyub yazını necə yeniləyim?",
        (
            "Paylaşımlarınızda «Düzəliş tələb olunur» statuslu yazını tapın və müəllimin rəyini oxuyun.",
            "Həmin yazıda «Redaktə et» düyməsini basın. Göstərilən yerləri düzəldib yadda saxlayın və siyahıda "
            "yazının yeni vəziyyətini yoxlayın.",
        ),
        "yazılarım postlarım paylaşım redaktə müəllim rəyi düzəliş",
        "",
        0,
    ),
    "my-exams": (
        "Müəllim kimi yeni quiz yaratmağa haradan başlayım?",
        (
            "«İmtahanlarım»da «Yeni imtahan» düyməsini basın. İmtahanın növünü və quiz üçün uyğun parametrləri "
            "seçin.",
            "Sualları və imtahanın təyin ediləcəyi qrupu yoxlayın. Sonradan imtahanı ada və statusa görə öz "
            "siyahınızda tapa bilərsiniz.",
        ),
        "quiz yarat müəllim test yeni imtahan imtahanlarım",
        "04-01-quiz-yarat",
        0,
    ),
    "my-courses": (
        "Kursu hazırlayıb tələbələrə necə göstərim?",
        (
            "«İlk kursu yarat» düyməsi ilə kursun adını və qısa təsvirini daxil edin. Mövzular üçün bağlı "
            "sillabusun həftəlik planından istifadə edə bilərsiniz.",
            "Kursa qrupları əlavə edin, kurs kartında mövzu və tapşırıq sayını yoxlayın və «Yayımla» düyməsini "
            "basın.",
        ),
        "kurs yarat dərs mövzuları kurslarım müəllim yayımla sillabus",
        "",
        0,
    ),
    "courses": (
        "Kurs kartından dərs materiallarına necə keçim?",
        (
            "Kurslar siyahısında sizə təyin edilmiş kursun adını və kateqoriyasını tutuşdurun.",
            "Kartdakı «Kursa daxil ol» keçidini açın. Siyahı boşdursa, həmin hesab üçün təyin olunmuş kursun "
            "olmadığı barədə məlumat görünür.",
        ),
        "kurs kataloqu tələbə kurs material kursa daxil ol",
        "",
        0,
    ),
    "assigned-exams": (
        "Təyin edilmiş açıq quizi necə başladım?",
        (
            "«Təyin olunmuş tapşırıqlar»da «İmtahanlar»ı seçin. Quizin başlanma vaxtına, son tarixinə və "
            "göstərilən müddətə baxın.",
            "Müvafiq sətirdə «Tapşırığı aç» düyməsini basın. Quizin giriş səhifəsində şərtləri oxuyub başlama "
            "düyməsini seçin və ilk sualı açın.",
        ),
        "tələbə quiz başla qiymətləndirmə test tapşırıq aç vaxt",
        "T01-03-quiz-basla",
        0,
    ),
    "assigned-courses": (
        "Mənə təyin olunmuş kursu adı ilə necə tapım?",
        (
            "«Kurs axtar» sahəsinə kursun adından bir söz yazın. Göstərilən kursun adını və kateqoriyasını "
            "yoxlayın.",
            "«Kursa daxil ol» düyməsini basın. Nəticə tapılmadıqda axtarış sözünü silib sizə təyin edilmiş bütün "
            "kursları yoxlayın.",
        ),
        "təyin edilmiş kurslar kurs axtarışı tələbə dərs kursum",
        "",
        0,
    ),
    "my-results": (
        "Fənn üzrə qiymətlərimi digər tapşırıq nəticələrindən necə ayırım?",
        (
            "«Nəticələrim»də nəticə növünü «Akademik» seçin. Tədris ili, semestr və fənn üzrə siyahını daraldın.",
            "Fənnin sətrində bal hissələrini tutuşdurun. Ayrı imtahanı və ya tapşırığı axtarırsınızsa, nəticə "
            "növünü uyğun kateqoriyaya dəyişin.",
        ),
        "qiymət qiymətlərim bal nəticə imtahan laboratoriya akademik",
        "T03-01-qiymet-jurnal",
        0,
    ),
    "my-subjects": (
        "Hansı fəndə qayıb limitinə yaxınlaşdığımı necə görüm?",
        (
            "«Fənlərim»də semestri seçin və qeydiyyatda olduğunuz fənnin sətrini tapın.",
            "Fənnin qayıb göstəricisini və status nişanını oxuyun. Sarı nişan limitə yaxınlaşdığınızı, qırmızı "
            "nişan isə limitin keçildiyini bildirir.",
        ),
        "semestr fənlərim buraxılış qayıb sarı qırmızı limit kredit",
        "T00-01-telebe-icmal",
        24,
    ),
    "my-transcript": (
        "Transkriptdə hansı fənlər və kreditlər göstərilir?",
        (
            "Hazırkı kabinetdə rəsmi transkript üçün «Nəticələrim»dən müraciət formasına keçin. Transkripti aldıqda tələbə nömrənizi və ixtisasınızı yoxlayın.",
            "Yekunlaşmış fənn qeydiyyatlarında balı, krediti və ümumi göstəriciləri oxuyun. Hələ yekunlaşmış qeyd "
            "olmadıqda sistem bunu ayrıca bildirir.",
        ),
        "akademik transkript kredit ECTS qiymət ortalama yekun",
        "",
        0,
    ),
    "overall-academic": (
        "Əvvəlki semestrlərdə kəsildiyim fənləri necə tapım?",
        (
            "«Ümumi tədris məlumatı»nda tədris ili və semestri seçin. Bütün dövrlər lazımdırsa, il süzgəcində "
            "«Hamısı» saxlayın.",
            "Nəticə süzgəcində kəsildiyiniz fənləri seçin. Cədvəldə fənnin balını və kreditini, yuxarıda isə "
            "ümumi ÜOMG-ni yoxlayın.",
        ),
        "ümumi orta müvəffəqiyyət göstəricisi ÜOMG kəsr əvvəlki semestr kredit",
        "T00-01-telebe-icmal",
        89,
    ),
    "pending-answers": (
        "Təqdim etdiyim yazılı cavabın hələ yoxlanıldığını necə bilim?",
        (
            "Gözləmədə olan cavablarda işin növünü seçin və adla axtarın. Sətirdə təhvil vaxtını və yoxlama "
            "statusunu oxuyun.",
            "«Yoxlanılır» müəllimin işə baxdığını göstərir. Nəticə açıldıqdan sonra «Nəticələrimə keç» vasitəsilə "
            "verilmiş balı görün.",
        ),
        "yazılı cavab tələbə gözləyir yoxlanılır nəticə nə vaxt",
        "",
        0,
    ),
    "pending-post-approvals": (
        "Tələbənin məqaləsinə necə rəy verim və düzəliş istəyim?",
        (
            "«Təsdiq gözləyən» siyahısında məqaləni tələbə, qrup və ya başlığa görə tapın. Məzmunu oxuyun.",
            "Rəy sahəsinə dəyişməli olan hissəni yazıb düzəliş istəyi göndərin. Yenidən baxarkən «Düzəliş tələb "
            "olunan» süzgəcindən istifadə edin.",
        ),
        "post təsdiqi müəllim tələbə yazı rəy məqalə moderasiya",
        "",
        0,
    ),
    "pending-review": (
        "Təqdim edilmiş işi yoxlama növbəsində necə tapım?",
        (
            "«Yoxlanılacaq» bölməsində növü, qrupu və statusu seçin. Ən erkən göndərilənlərdən başlamaq üçün "
            "sıralamanı dəyişin.",
            "Sətirdə «Yoxla» düyməsini açın və təqdim edilmiş cavabı oxuyun. Yoxlanmış işi «Dəyərləndirilmiş "
            "nəticələr»dən izləyə bilərsiniz.",
        ),
        "yoxlama növbəsi müəllim açıq sual yazılı cavab təqdim",
        "M00-00-muellim-icmal",
        210,
    ),
    "review-results": (
        "Yoxlanmış işi və qiyməti kimin verdiyini necə yoxlayım?",
        (
            "«Dəyərləndirilmiş nəticələr»də tələbəyə, qrupa və ya tapşırığa uyğun süzgəcləri tətbiq edin.",
            "Sətirdə «Nəticə», «Yoxlayan» və «Tarix» sütunlarını müqayisə edin. Həmin işin təfərrüatları üçün "
            "«Bax» düyməsini basın.",
        ),
        "qiymətləndirilmiş nəticələr yoxlayan bal müəllim nəticə tarixi",
        "M00-00-muellim-icmal",
        217,
    ),
    "edit-profile": (
        "Profilimdə telefon nömrəsini və şəklimi necə dəyişdirim?",
        (
            "Profilin redaktəsində əsas telefonun ölkə kodunu seçib nömrəni yazın. İkinci nömrəniz varsa «Əlavə "
            "telefon» sahəsindən istifadə edin.",
            "Avatar hissəsində «Şəkli dəyiş» və ya «Şəkil yüklə» düyməsi ilə şəkli seçin. Şəxsi məlumatları "
            "saxlayıb profilinizdə nömrəni və şəkli yoxlayın.",
        ),
        "profil telefon nömrəsi avatar şəkil e-poçt şəxsi məlumat",
        "",
        0,
    ),
    "change-password": (
        "Kabinetdən şifrəmi mövcud şifrə və ya e-poçt kodu ilə necə dəyişdirim?",
        (
            "«Şifrəni dəyiş» bölməsində «Mövcud şifrə ilə» və ya «Email kodu ilə» üsulunu seçin. E-poçt üsulunda "
            "«Kodu göndər» düyməsini basıb gələn kodu daxil edin.",
            "Mövcud şifrə üsulundasınızsa, əvvəl indiki şifrənizi daxil edin. Yeni şifrəni iki sahədə eyni yazın. "
            "Uyğunluq göstəricisini yoxlayıb «Şifrəni yenilə» düyməsini basın.",
        ),
        "şifrə parol dəyiş OTP kod email giriş",
        "H00-01-giris-parol",
        72,
    ),
    "my-appeals": (
        "İmtahanda konkret suala görə apellyasiyanı necə göndərim?",
        (
            "«Apellyasiyalarım»da «Yeni apellyasiya müraciəti» seçin. Son tarixi yoxlayıb uyğun imtahanın "
            "qarşısında «Apellyasiyaya ver» düyməsini basın.",
            "Sualı seçin, səbəb göstərin və ən azı 30 simvolla əsaslandırın. «Apellyasiyanı göndər» seçin və "
            "açılan pəncərədə təsdiqləyin.",
            "Siyahıda müraciətin «Gözləyir» statusunu yoxlayın. Sonrakı qərarı da həmin müraciətdə oxuyun.",
        ),
        "apellyasiya etiraz tələbə sual bal qərar",
        "T01-01-apellyasiya",
        0,
    ),
    "evaluation-survey": (
        "Müəllim qiymətləndirməsini tamamladığımı necə yoxlayım?",
        (
            "Gözləyən qiymətləndirmədə «Sorğunu doldur» düyməsini seçin. Aid olduğu müəllim və fənn üzrə suallara "
            "cavab verib formanı tamamlayın.",
            "Bölməyə qayıdıb tamamlanan qiymətləndirmələrin sayına baxın. «Sorğunu tam doldurmusunuz» məlumatı "
            "cavabların anonim qeydə alındığını göstərir.",
        ),
        "müəllim qiymətləndirməsi tələbə anonim sorğu iştirak",
        "",
        0,
    ),
    "surveys-inbox": (
        "Yarımçıq qalan sorğuya necə davam edim?",
        (
            "«Sorğular»da «Gözləyən» hissəsinə baxın. Sorğunun anonim və ya adla, məcburi və ya könüllü olduğunu "
            "kartdan oxuyun.",
            "Başlanmış sorğu üçün «Davam et», yeni sorğu üçün «Doldur» seçin. Bitirdikdən sonra «Tamamlanmış» "
            "hissəsində vəziyyəti yoxlayın.",
        ),
        "sorğularım davam et sorğunu doldur məcburi könüllü tələbə",
        "T00-01-telebe-icmal",
        163,
    ),
    "my-subject-folders": (
        "Ev tapşırığını necə təqdim edim və müəllim qaytarsa necə yeniləyim?",
        (
            "«Dərs materiallarım»da fənni açın. Ev tapşırığının yanında «Cavab ver» seçin, şərti və son tarixi "
            "oxuyun. Cavabınızı yazıb «Göndər» düyməsini basın və təsdiqləyin.",
            "Müəllim işi qaytarıbsa, həmin tapşırıqda «Göndərişlərim»i açıb rəyini oxuyun. «Düzəldilmiş cavab» "
            "hissəsinə yenilənmiş cavabı yazıb göndərin. Hər iki cəhd siyahıda qalır.",
        ),
        "tələbə ev tapşırığı göndər rəy oxu yenidən təqdim dərs materialları fənn qovluğu",
        "T02-01-ev-tapsirigi",
        0,
    ),
    "announcements": (
        "Məcburi elanla tanış olduğumu necə təsdiqləyim?",
        (
            "«Elanlar»da «Təsdiq gözləyənlər»i seçin. Elanı açıb mətnini, son tarixini və varsa sənədlərini " "oxuyun.",
            "«Elanı oxudum və tanış oldum» seçimini işarələyib «Təsdiq edirəm» düyməsini basın. Uğurlu "
            "əməliyyatda «Təsdiq edildi» görünür.",
        ),
        "elan məcburi bildiriş tanış oldum təsdiq gözləyir tələbə",
        "",
        0,
    ),
    "my-group": (
        "Qrup nümayəndəsi birləşmiş dərsləri və yaxın imtahanları harada görür?",
        (
            "«Starosta» bölməsində təyin edildiyiniz qrupun adını yoxlayın. «Birləşmiş dərslər»də birgə dərs keçilən "
            "qruplara və fənlərə baxın.",
            "«İmtahanlar» vərəqində yaxın 90 gün üçün qrupa təyin edilmiş imtahanları yoxlayın. Qrup nümayəndəsi "
            "rolu qrupa bağlanmayıbsa, bu barədə dekanlığa müraciət edin.",
        ),
        "starosta qrup nümayəndəsi birləşmiş dərs patok yaxın imtahan",
        "",
        0,
    ),
    "my-retakes": (
        "Kəsildiyim fənn üçün 25 faiz imtahanına necə müraciət edim?",
        (
            "«25% və alt qrup»da fənnin sətrini açın, qayıb vəziyyətini və müraciət pəncərəsinin son tarixini "
            "yoxlayın.",
            "25 faiz imtahanına uyğun fənn üçün müraciəti açın və tələb olunan ödəniş qəbzini yükləyin. Qayıb "
            "həddi keçilibsə həmin fənn üçün alt qrup variantına baxın.",
        ),
        "kəsr 25 faiz təkrar imtahan qəbz ödəniş alt qrup tələbə",
        "T00-01-telebe-icmal",
        142,
    ),
    "my-contracts": (
        "Yeni əmək müqaviləmlə tanış olduğumu kabinetdə necə təsdiqləyim?",
        (
            "Müqavilələrimdə yeni müqavilənin «Müqaviləyə sistemdə bax» keçidini açın. Nömrəni, vəzifəni, "
            "müddəti, ştat vahidini və faylı nəzərdən keçirin.",
            "Lazım gəlsə qeyd yazın və «Tanış oldum, təsdiqləyirəm» düyməsini basın. Cari müqavilənin yanında "
            "«Təsdiqləmisiniz» məlumatını yoxlayın.",
        ),
        "əməkdaş müqaviləm işçi tanış oldum təsdiq e-poçt",
        "",
        0,
    ),
}
