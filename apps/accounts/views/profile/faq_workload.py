"""Fəaliyyət üzrə ayrıca saat, müəllim bölgüsü və qrup təlimatları."""

GUIDE_ROWS = (
    (
        "lab-group-create",
        "Lab-1 və Lab-2 qruplarını necə yaradım və tələbələri necə yerləşdirim?",
        "Laboratoriya qrupları",
        "lab-groups",
        "Lab qruplarını aç",
        "lab-group-placement",
        (
            "«Lab qrupları»nda fənni və əsas akademik qrupu seçin. Tələbələri böləcəyiniz fənn açılışını yoxlayın.",
            "Laboratoriya qruplarını yaradın. Lab-1 və Lab-2 siyahılarında hər tələbənin hansı qrupa gedəcəyini seçib yerləşdirməni saxlayın.",
            "Eyni fənni yenidən açıb hər iki qrupun tərkibini yoxlayın.",
        ),
        "lab qrupu yarat laborant laboratoriya Lab-1 Lab-2 tələbə yerləşdir",
        (),
    ),
    (
        "load-lab-hours",
        "Laboratoriya iki qrupa bölünürsə, fənnin saatı və müəllim yükü necə hesablanır?",
        "Laboratoriya saatları",
        "workload-distribution",
        "Yük bölgüsünü aç",
        "workload-lab-row-edit",
        (
            "Nümunədə hər tələbənin planı 30 saat mühazirə və 30 saat laboratoriyadır. Tələbə yalnız öz lab qrupunun dərsinə gedir və fənn üzrə 60 saat keçir.",
            "Birgə mühazirə 30 saatdır. Lab-1 və Lab-2-nin hərəsinə ayrı vaxtda tam 30 saat keçirilirsə, laboratoriyanın cəmi 60 saat, kafedranın bu fənn üzrə yükü isə 90 saatdır.",
            "Bir laboratoriya qrupunun eyni 30 saatını iki müəllim 15 + 15 bölürsə, laboratoriyanın cəmi 30 saat qalır. Formada yarımqrup sayı və «cəmi» sahələrini ayrıca yoxlayın.",
        ),
        "laboratoriya 30 60 90 lab yarımqrup 1 2 saat fərqi sillabus",
        ("can_manage_workload",),
    ),
    (
        "load-lab-edit",
        "Laboratoriyalı yük sətrini necə yaradım, sonra mövcud sətrin saatını necə dəyişdirim?",
        "Yük sətrinin redaktəsi",
        "workload-distribution",
        "Yük bölgüsünü aç",
        "workload-lab-row-edit",
        (
            "Kafedranı və tədris ilini seçin. «Sətir əlavə et»i açın, fənni, semestri və qrup reyestrindən aid olan qrupları seçin.",
            "Laboratoriya üçün bir tələbəyə düşən plan saatını, qrup/yarımqrup sayını və ayrıca keçiriləcək laboratoriyaların ümumi saatını yazın. Mühazirə varsa onun axın və saatlarını ayrıca göstərin. «Yadda saxla»nı basın.",
            "Mövcud sətri dəyişdirmək üçün fənnin kartından «Sətirlər»i açıb «Redaktə»ni seçin. Dəyişən qrup sayını və ya saatı yazın, nəticədə plan və cəmi yenidən tutuşdurun.",
            "«Yadda saxla»dan sonra sətri təkrar açın. Təsdiqlənmiş bölgü üçün sistem səbəb və qeyd istəyirsə, dəyişiklik əsasını yazın.",
        ),
        "yeni sətir əlavə etmək mövcud sətir dəyişmək redaktə laboratoriya sayı cəmi saxlamaq",
        ("can_manage_workload",),
    ),
    (
        "language-group-create",
        "Yeni xarici dil səviyyə qrupunu sıfırdan necə yaradım?",
        "Xarici dil səviyyə qrupları",
        "",
        "Səviyyə qruplarını aç",
        "language-group-create",
        (
            "Kabinetdə «Xarici dil səviyyə qrupları»na keçib «Yeni səviyyə qrupu yarat»ı açın. Qrupun adını yazın, əhatənizdəki kafedranı və cari semestri seçin.",
            "«Səviyyə fənni»ni və müəllimi seçin. Səviyyə fənnin adından götürülür. Mühazirə, seminar / praktiki məşğələ və laboratoriya saatlarını ayrıca yazın. Keçirilməyən dərs növünə sıfır yazın.",
            "Qiymətləndirmə mənbəyi kimi eyni fənn, semestr və müəllimin jurnalını seçə bilərsiniz. Mənbə seçmirsinizsə, formadakı bal hədlərini yoxlayın. Həmin müəllimin bu fəndən eyni semestrdə jurnalı artıq varsa, ayrıca qrup yaratmaq üçün təsdiq xanasını işarələyin.",
            "«Qrupu yarat»ı basın. Açılan səhifədə yeni qrupun adını və səviyyəsini yoxlayın. Reyestrə qayıdanda həmin kartdakı «İdarə et»i basın. Tələbəni adı və ya əsas qrupu ilə axtarıb seçin, yerləşdirmə səbəbini yazın və səviyyəyə əlavə edin.",
        ),
        "xarici dil level səviyyə qrupu yarat ingilis dili A1 A2 B1 B2 yeni qrup",
        ("can_manage_language_cohorts",),
    ),
    (
        "practice-assign",
        "Elmi-tədqiqat və ya istehsalat təcrübəsini müəllimə necə yazım?",
        "Təcrübə yükü",
        "workload-distribution",
        "Yük bölgüsünü aç",
        "workload-practice-distribute",
        (
            "Kafedranı və tədris ilini seçin. Dekanlığın təsdiqlədiyi tapşırıqda təcrübə sətrini açın.",
            "Elmi-tədqiqat və ya istehsalat təcrübəsinin yanındakı «Bölüşdür» düyməsini basın. Müəllimi seçin, ayrılan saatı yazın və təyinatı saxlayın.",
            "Təcrübə sətrinin ayrılmış və qalan saatını yoxlayın. Kafedranın bölgüsü hazırdırsa, yekun təsdiqi verin.",
        ),
        "təcrübə praktika internship elmi tədqiqat istehsalat praktiki məşğələ paylama saat",
        ("can_distribute_workload",),
    ),
    (
        "practice-personal",
        "Mənə verilmiş təcrübə saatlarını müəllim kabinetində harada görüm?",
        "Dərs yüküm",
        "my-workload",
        "Dərs yükümü aç",
        "practice-personal",
        (
            "Şəxsi kabinetdə «Dərs yüküm»ü açın. Tədris ilini və təsdiqlənmiş bölgünü yoxlayın.",
            "Uyğun sətrə baxın. Elmi-tədqiqat təcrübəsi və istehsalat təcrübəsi ayrıca göstərilir. Sizə verilən saatı həmin sətrin fəaliyyəti ilə tutuşdurun.",
            "Uyğunsuzluq görsəniz, «Etiraz bildir»i açın. «Fənn/iş»i və səbəbi seçin, ən azı 20 simvolla hansı saatın dəyişməli olduğunu izah edib göndərin. Bütün illik təyinatlar düzgündürsə, «Yükü təsdiqlə»ni seçin və təsdiq bildirişini yoxlayın.",
        ),
        "müəllim təcrübə harada görünür şəxsi yüküm istehsalat rəhbərlik",
        (),
    ),
)

OTHER_HOURS = (
    (
        "load-consult",
        "Məsləhət",
        "Məsləhət saatlarını müəllimə necə ayırım?",
        "Məsləhət üçün təsdiqlənmiş saatı «Məsləhət» sahəsinə yazın. Videodakı nümunədə 2 saat göstərilir.",
    ),
    (
        "load-exam",
        "İmtahan",
        "İmtahan saatlarını müəllimin yükünə necə əlavə edim?",
        "«İmtahan» sahəsinə həmin iş üzrə ayrılmış saatı yazın. Nümunədə 4 saat seçilir. Bu sahə tələbənin imtahan balından ayrıdır.",
    ),
    (
        "load-thesis",
        "Buraxılış işinə rəhbərlik",
        "Buraxılış işinə rəhbərlik saatlarını harada qeyd edim?",
        "Sətir formasında «Buraxılış işi» sahəsinə tapşırıqda göstərilən saatı yazın. Nümunədə buraxılış işinə 6 saat ayrılır.",
    ),
    (
        "load-postgrad",
        "Dissertant rəhbərliyi",
        "Dissertant rəhbərliyini buraxılış işindən ayrı necə qeyd edim?",
        "«Dissertant rəhbərliyi» sahəsinə bu fəaliyyət üçün ayrılmış saatı yazın. Nümunədə 8 saat ayrılır. Buraxılış işi üzrə təyinat öz sahəsində saxlanır.",
    ),
)
GUIDE_ROWS += tuple(
    (
        key,
        question,
        "Yük bölgüsü",
        "workload-distribution",
        "Yük bölgüsünü aç",
        "workload-activities-staff",
        (
            "Kafedranın və tədris ilinin düzgün olduğunu yoxlayın. Fənn kartında «Sətirlər»i açıb qrup və semestrə uyğun sətrin «Redaktə» düyməsini basın.",
            instruction
            + " «Yadda saxla»nı basın. Təsdiqlənmiş bölgüyə düzəliş edilirsə, göstərilən səbəb və qeyd sahələrini doldurun.",
            f"«{activity}» sətrində «Bölüşdür»ü seçin. Müəllimi seçib ona ayrılan saatı yazın, «Əlavə et»i basın. Bir neçə müəllim varsa, hərəsinə yalnız öz payını yazın.",
            "Fəaliyyətin ayrılmış və qalan saatlarını tutuşdurun. Müəllim «Dərs yüküm»də tədris ili və fənn üzrə təsdiqlənmiş təyinatı görür.",
        ),
        f"{activity} əlavə fəaliyyət müəllim rəhbər saat plan cəm təyinat bölüşdür",
        ("can_distribute_workload",),
    )
    for key, activity, question, instruction in OTHER_HOURS
)
