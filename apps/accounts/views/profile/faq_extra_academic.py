"""Akademik reyestrlər, xidmətlər, təkrar təhsil və keyfiyyət."""

ACADEMIC = {
    "academic-calendar": (
        "Semestr, imtahan sessiyası və bayram günlərinin tarixlərini necə tapım?",
        (
            "«Akademik təqvim»də lazım olan tədris ilini tapın. Həmin ilin semestr başlanğıcını, bitməsini və "
            "imtahan sessiyasını oxuyun.",
            "Bayram və qeyri-iş günləri siyahısını planlaşdırdığınız tarixlə tutuşdurun. Semestr təyin "
            "edilməyibsə təqvim bunu ayrıca bildirir.",
        ),
        "akademik təqvim bayram qeyri-iş sessiya semestr tarix",
        "T00-01-telebe-icmal",
        101,
    ),
    "student-intake": (
        "Bir tələbə hesabını qrup və qəbul ili ilə necə yaradım?",
        (
            "Yeni hesab formasında «Tələbə» seçin. Tələbənin şəxsiyyət və əlaqə məlumatlarını, qəbul ilini və "
            "akademik qrupunu göstərin.",
            "Təsdiqdən əvvəl tələbəni və qrupu tutuşdurun. Bu hesab növü üçün akademik qeyd də yaradılır.",
        ),
        "tələbə əlavəsi fərdi hesab yarat qəbul ili qrup akademik qeyd",
        "",
        0,
    ),
    "teacher-intake": (
        "Bir neçə müəllim hesabını faylla necə əlavə edim?",
        (
            "«Müəllim əlavəsi (toplu)» bölməsində müəllimlər üçün toplu əlavə formasını açın. Siyahını formanın "
            "qəbul etdiyi sütunlara uyğun hazırlayıb faylı seçin.",
            "İlkin yoxlama nəticəsində adları, kafedraları və xəbərdarlıqları tutuşdurun. Uyğun sətirləri "
            "təsdiqləyib yaradılmış müəllim hesablarının nəticəsinə baxın.",
        ),
        "HR müəllim toplu əlavə Excel işə qəbul kafedra",
        "HR00-00-hr-icmal",
        50,
    ),
    "registrar-catalog": (
        "Registrar kataloqundan yeni rubriki harada yarada bilərəm?",
        (
            "«Registrar (kataloq)» bölməsində «Rubriklər» vərəqini seçin. Mövcud rubrikləri yoxlayıb «Yeni "
            "rubrik» formasını açın.",
            "Formadakı qiymətləndirmə sahələrini doldurun və «Yadda saxla» düyməsini basın. Yeni rubrikin "
            "siyahıda göründüyünü yoxlayın.",
        ),
        "registrar kataloq rubrik qiymətləndirmə meyarları tədris qeydiyyatı",
        "",
        0,
    ),
    "applications": (
        "Müraciətimin hansı şöbəyə gedəcəyini göndərməzdən əvvəl necə bilim?",
        (
            "«Müraciətlərim»də «Yeni müraciət» seçin. Növü seçəndə formanın altında aidiyyəti şöbə görünür.",
            "Mövzunu, fənni, qrupu və dəqiq tarixi yazın, lazım gəlsə sənəd əlavə edin. «Müraciəti göndər» "
            "düyməsindən sonra nömrəni və cavabı «Müraciətlərim»də izləyin.",
        ),
        "ərizə müraciət şikayət RİM texniki problem şöbə yönləndirmə",
        "01-01-muraciet-gonder",
        0,
    ),
    "analytics": (
        "Hansı qrup və fənlərdə kəsilmə göstəricisi yüksəkdir?",
        (
            "«Akademik analitika»da lazım olan semestrin «Proqramlar üzrə» və «Qruplar üzrə» cədvəllərinə baxın. "
            "Qrup sətrində orta balı, keçid və qayıb göstəricilərini müqayisə edin.",
            "«Diqqət tələb edən fənlər» hissəsində kəsilmə faizi yüksək fənn açılışlarını tapın. «Kəsilmə "
            "həddində» sütunu qayıb limitini keçmiş fənn qeydiyyatlarını sayır.",
        ),
        "akademik analitika kəsilmə faizi davamiyyət GPA qrup monitorinq",
        "K00-00-kafedra-icmal",
        245,
    ),
    "academic-records": (
        "Tələbənin kəsri ilə hələ qiymətləndirilməmiş fənnini necə ayırım?",
        (
            "«Akademik qeydlər»də tələbəni və semestri seçib fənn sətirlərinə baxın. «Q/b» imtahana qayıba görə "
            "buraxılmayan qeydiyyatı göstərir.",
            "«Qiymətləndirilməyib» çıxış balının hələ olmadığını bildirir. Şübhəli nəticədə sətrin detalını açıb "
            "mənbə məlumatını, giriş və yekun göstəricilərini tutuşdurun.",
        ),
        "akademik qeyd kəsr qiymətləndirilməyib giriş balı ÜOMG mənbə",
        "MN00-00-monitorinq-icmal",
        61,
    ),
    "people-teachers": (
        "Müəllimin hansı kafedraya aid olduğunu və hesab vəziyyətini necə yoxlayım?",
        (
            "«Müəllimlər» siyahısında adına və ya kafedraya görə şəxsi tapın. Eyniadlı şəxsləri istifadəçi adı "
            "ilə ayırın.",
            "«Kartı aç» düyməsi ilə vəzifəni, ştatı və kafedranı yoxlayın. Səlahiyyətinizə uyğun idarəetmə "
            "əməliyyatlarını həmin şəxsin «İdarə et» menyusunda görün.",
        ),
        "müəllim siyahısı kadr əməkdaş kafedra vəzifə ştat kart",
        "K00-00-kafedra-icmal",
        229,
    ),
    "people-students": (
        "Tələbənin hesabını tapıb hazırkı qrupunu necə dəqiqləşdirim?",
        (
            "«Tələbələr» siyahısında adı və ya istifadəçi adı ilə axtarın, lazım gələrsə qəbul ili və qrupla "
            "nəticələri daraldın.",
            "Uyğun sətirdə «Kartı aç» seçib hesabın vəziyyətini və qrupunu yoxlayın. Qrup təyinatı olmayan tələbə "
            "siyahıda «Qrupsuz» kimi görünür.",
        ),
        "tələbə hesabı qrupsuz qəbul ili profil kartı idarəetmə",
        "",
        0,
    ),
    "org-structure-tree": (
        "Universitetin struktur ağacında yeni alt bölməni necə yerləşdirim?",
        (
            "Struktur ağacında alt bölmənin aid olacağı vahidi seçin. Sağ tərəfdə seçilmiş vahidin adını və "
            "tərkibini yoxlayın.",
            "«Alt bölmə əlavə et» ilə bölmənin adını və tələb olunan məlumatı daxil edin. Saxladıqdan sonra yeni "
            "bölmənin doğru valideyn vahidin altında göründüyünü yoxlayın.",
        ),
        "universitet strukturu ağac şöbə fakültə kafedra alt bölmə",
        "TS00-00-tedris-icmal",
        158,
    ),
    "programs-registry": (
        "Yeni ixtisasın kataloq qeydini haradan yaradım?",
        (
            "«İxtisaslar» reyestrində eyni kod və adla qeyd olub-olmadığını yoxlayın. «Yeni ixtisas» formasını "
            "açın.",
            "İxtisasın məlumatlarını doldurub «Yadda saxla» düyməsini basın. Yeni sətrin «İxtisas haqqında» "
            "pəncərəsində məlumatları tutuşdurun.",
        ),
        "ixtisas reyestri kod kataloq proqram səviyyə",
        "TS00-00-tedris-icmal",
        82,
    ),
    "subject-catalog": (
        "Kataloqda eyni adlı fənlər varsa saxlanılacaq kartı necə müəyyən edim?",
        (
            "«Fənn kataloqu»nda «Eyni adlı fənlər aşkarlandı» hissəsini açın. Eyni adlı kartları kodları və "
            "əlaqəli açılışları ilə müqayisə edin.",
            "«Saxlanılacaq fənn»i və birləşdiriləcək kartları seçib «Önizlə» düyməsini basın. Xəbərdarlıq və "
            "təsirlənəcək əlaqələri yoxlayın. Seçimi dəyişsəniz yenidən önizləyin.",
        ),
        "fənn kataloqu dublikat birləşdirmə kod eyni ad önizləmə",
        "",
        0,
    ),
    "curriculum-editor": (
        "Tədris planına fənn sətri əlavə edib semestr balansını necə yoxlayım?",
        (
            "İxtisasın uyğun qəbul ili və versiyası üzrə qaralama planı seçin. «Sətir əlavə et» ilə fənni və aid "
            "olduğu semestri göstərin.",
            "Kredit və saatları daxil edib saxlayın. «Balans — semestr üzrə» hissəsində kredit, auditoriya və "
            "sərbəst saatları planla müqayisə edin.",
        ),
        "tədris planı ixtisas fənn kredit ECTS semestr balans",
        "TS00-00-tedris-icmal",
        70,
    ),
    "groups-registry": (
        "Qrup nümayəndəsini necə təyin edim və ya dəyişdirim?",
        (
            "«Qruplar» siyahısında qrupu tapıb «Tələbələr» düyməsini basın. Qrupun aktiv tələbə siyahısını "
            "yoxlayın.",
            "«Qrupun starostası» əməlini açıb həmin qrupun tələbəsini seçin və «Təyin et» düyməsini basın. "
            "Nümayəndənin adını qrup məlumatında yoxlayın.",
        ),
        "qrup starosta qrup nümayəndəsi təyin tələbə dekan tyutor",
        "D00-01-qrup-telebeleri",
        43,
    ),
    "semester-opening": (
        "Semestr üzrə fənn açılışlarını tədris planından necə yaradım?",
        (
            "«Semestr açılışı»nda lazım olan tədris dövrünü seçin. «Tədris planından açılış yarat» formasında "
            "uyğun planı və qrupları müəyyən edin.",
            "«Açılışları yarat» əməlindən sonra açılış sətirlərində fənn və qrupları tutuşdurun. Kafedralar üzrə "
            "hazırlıqda müəllim təyinatı və açıq qalan məsələləri yoxlayın.",
        ),
        "semestr açılışı fənn açılışı tədris planı jurnal qeydiyyat",
        "TS00-00-tedris-icmal",
        91,
    ),
    "student-admission": (
        "ATİS siyahısından tələbələri toplu qəbul etməzdən əvvəl nəyi yoxlayım?",
        (
            "«Tələbə qəbulu»nda ATİS şablonunu endirin və məcburi sütunlara uyğun faylı hazırlayın. Faylı "
            "yükləyib yoxlamanı başladın.",
            "Önizləmədə ixtisası, qrup təyinatını, təkrarlanan hesabları və səhv sətirləri yoxlayın. "
            "Düzəlişlərdən sonra «Tətbiq et» ilə qəbulu tamamlayın.",
        ),
        "tələbə xidmətləri ATİS qəbul toplu Excel idxal qrup",
        "TX00-00-xidmet-icmal",
        13,
    ),
    "student-registry": (
        "Tələbənin akademik məzuniyyət və bərpa əmrini harada izləyim?",
        (
            "«Tələbə reyestri»ndə tələbəni tapıb kartını açın. «Hərəkət tarixçəsi»ndə əmr nömrəsini, tarixi və "
            "hərəkət növünü yoxlayın.",
            "Yeni hərəkət rəsmiləşdirilirsə «Hərəkət əmri»ni seçin, əmrin nömrəsini və tarixini yazın. Bərpa "
            "zamanı tələbənin qayıdacağı qrupu da göstərin.",
        ),
        "tələbə reyestri akademik məzuniyyət dondur bərpa əmr tarixçə xidmətlər",
        "TX00-00-xidmet-icmal",
        33,
    ),
    "evaluation-results": (
        "Anonim sorğunun nəticələrini müəllim və dövr üzrə necə müqayisə edim?",
        (
            "«Sorğu nəticələri»ndə fakültə, kafedra, müəllim və ya fənn üzrə süzün. Cavab sayını yoxlayın. Az "
            "cavab olan qrupda nəticə gizlənə bilər.",
            "«Dövrlər üzrə dinamika»da ümumi balı və ya Likert indeksini seçib eyni göstəricini dövrlər üzrə "
            "müqayisə edin.",
        ),
        "keyfiyyət qiymətləndirmə nəticələri anonim Likert sorğu dövr qrafik",
        "KY00-00-keyfiyyet-icmal",
        34,
    ),
    "evaluation-campaigns": (
        "Keyfiyyət şöbəsi semestr qiymətləndirmə kampaniyasını necə açır?",
        (
            "«Sorğu kampaniyaları»nda «Yeni kampaniya — semestr» formasını seçin. Semestri, sual dəstini, "
            "bağlanma tarixini və tələb olunursa məcburi rejimi müəyyən edin.",
            "Hədəf və bağlı jurnal göstəricilərini yoxlayın. Kampaniyanı açdıqdan sonra «Açıq» vəziyyətini və "
            "iştirak sayını həmin sətirdə izləyin.",
        ),
        "keyfiyyət kampaniya sorğu aç semestr hədəf bağlı jurnal",
        "KY00-00-keyfiyyet-icmal",
        19,
    ),
    "surveys-builder": (
        "Sorğu suallarını kampaniya üçün necə hazır edim?",
        (
            "«Sorğu qurucusu»nda uyğun qaralamanı açın. Bölmələri və qiymətləndirmə şkalası və ya açıq mətn tipli "
            "sualları hazırlayın.",
            "Sual sayını və quruluşu yoxlayın. Kampaniya üçün istifadəyə veriləcək sual dəstində «Hazır et» "
            "düyməsini seçib təsdiqləyin.",
        ),
        "keyfiyyət sorğu qurucusu sual dəsti şkala açıq sual hazır",
        "KY00-00-keyfiyyet-icmal",
        11,
    ),
    "retake-desk": (
        "Mühasib 25 faiz imtahan müraciətinin ödənişini necə yoxlayır?",
        (
            "Müraciətlər masasında növbəni və tələbənin müraciətini seçin. «Qəbzə bax» ilə sənəddəki məbləği "
            "gözlənilən ödənişlə müqayisə edin və təkrar qəbz xəbərdarlığını yoxlayın.",
            "Uyğundursa «Ödənişi təsdiqlə» seçin. Uyğunsuzluq varsa «Qəbzi rədd et» seçib konkret səbəbi yazın və "
            "müraciətin yeni statusunu yoxlayın.",
        ),
        "mühasib 25 faiz təkrar imtahan qəbz ödəniş təsdiq rədd",
        "MH00-00-muhasib-icmal",
        37,
    ),
    "retake-windows": (
        "25 faiz təkrar imtahanına müraciət pəncərəsini necə açım?",
        (
            "«25% müraciət pəncərəsi»ndə tədris dövrünü, cari pəncərənin vəziyyətini və ümumi açarı yoxlayın.",
            "Müraciət qəbul etmək üçün tarixləri müəyyən edib «Pəncərəni aç» düyməsini basın. Pəncərəni "
            "bağladıqda tələbə kabinetində yeni müraciət imkanı bağlanır.",
        ),
        "imtahan mərkəzi təkrar 25 faiz pəncərə açılma son tarix",
        "I00-00-imtahan-icmal",
        170,
    ),
    "subgroup-placement": (
        "Kəsri olan tələbəni fənn üzrə başqa qrupun jurnalına necə yerləşdirim?",
        (
            "«Alt qrupa tələbə əlavə et»də tələbəni tapın, fənni və hədəf jurnalı seçin. Kredit həddini və cədvəl "
            "toqquşması barədə nəticəni yoxlayın.",
            "Yerləşdirmənin əsasını və tələb olunan sənədi daxil edin. Təsdiqdən əvvəl tələbəni, fənni və qrupu "
            "tutuşdurun.",
        ),
        "alt qrup yerləşdirmə kəsr kredit həddi cədvəl toqquşması sənəd",
        "R05-01-altqrup-yerlesdir",
        0,
    ),
    "credit-recognition": (
        "Əvvəlki təhsil nəticəsi ilə tələbəni fəndən necə azad edim?",
        (
            "«Fəndən azad etmə»də tələbəni tapıb «Fəndən azad et» düyməsini basın. Bu semestrin fənnini və "
            "tanınma səbəbini seçin.",
            "Mənbə təhsil və ya sertifikat məlumatını, yekun balı və təsdiqedici sənədi daxil edin. «Azad et» "
            "əməlindən sonra tanınmanı tələbənin siyahısında yoxlayın.",
        ),
        "kredit tanınması fəndən azad etmə sertifikat kollec transkript sənəd",
        "D00-03-fenden-azad",
        16,
    ),
    "subgroup-students": (
        "Alt qrupa yerləşdirilən tələbənin hara keçdiyini və sənədini necə tapım?",
        (
            "«Alt qrup tələbələri»ndə tələbəni, fənni və ya qrupu süzün. Öz qrupu ilə alt qrup kimi daxil olduğu "
            "qrupu müqayisə edin.",
            "Yerləşdirmə sətrində səbəb və qeydi oxuyun. «Sənədə bax» keçidi varsa, sərəncamı və ya əlavə olunmuş "
            "faylı açın.",
        ),
        "alt qrup tələbələri mənbə qrup hədəf yerləşdirmə sənəd sərəncam",
        "D00-00-dekanliq-icmal",
        58,
    ),
}
