# Leyla: iki yük sətri, üç mövcud jurnal

Bu əməliyyat yeni qiymət import etmir. Payız2026/2027 üçün dəqiq nəzərdən
keçirilmiş iki yük sətrinin `subject_id` bağı mənbədəki düzgün kataloqa keçirilir:

| Yük sətri | Cari sintetik kod | Mövcud düzgün kataloq | Qrup |
|---|---|---|---|
| `02d98bd9-e176-43a8-a9ed-8f1da41adf07` | QKU-2693 | QKU-2577 | 233 İ az |
| `da34a218-839f-4e76-90b9-dd79f6270772` | QKU-2690 | QKU-2422 | 235 İ-1 az, 235 İ-2 az |

Sintetik2690/2693 kodları MariaDB sətir ID-si sayılmır. Xam mənbədə həmin
rəqəmlər tam başqa fənlərdir. Yalnız kodda dondurulmuş üç source-declaration
keçərlidir; ad oxşarlığı, qlobal kataloq aliası və xaricdən scope qəbul edilmir.

## Dəyişməz qalanlar

Üç dolu jurnalın course ID-si, 550 mövcud xanası (0 bal daxil), QB/üzrlü
qayıb, müəllif və bütün tarixləri, tələbə qeydiyyatları, davamiyyət keşləri,
qiymətləndirmə sxemləri/imtahan balları və təsdiqlənmiş sillabusları saxlanır.
Saatlar45/60/60, təyinatların ID-ləri, M/S bölgüsü, ödəniş, kredit və qrup
bağları dəyişmir. Boş jurnallar silinmir və deaktiv edilmir. Yeni rol/icazə verilmir.

Cədvəlin altı orijinal Named slotu park olunaraq saxlanır; cari müəllim, semestr,
qrup, növ və vaxtı təsdiqlənmiş slotların altı dəqiq surəti dolu jurnallarda
mərkəzi cədvəl servisi ilə yaradılır. Əlavə konflikt, başqa müəllim,
kilidli semestr, çatışmayan növ və ya actual-class əlaqəsi əməliyyatı saxlayır.

## Təzə sübut və qoruyucular

İlkin private mənbə paketi: `existing-content-package.json`, SHA256
`745f28c72ba254b1c535f76c52aca07c5d1ca5345aa44b4e9a001e560ea89df5`.
Bu paket avtomatik tətbiq icazəsi deyil. Named jurnalların təzə tam sillabus,
versiya, share və bütün əlaqə exportu ayrıca nəzərdən keçirilməlidir.
Mənalı/qaralama və ya təsdiqlənmiş Named sillabus, Named imtahan/qiymət0,
başqa cari tədris yükü və fərqli canonical cədvəl explicit-review HOLD yaradır.
Hazırkı versiya belə Named məzmunu qəbul etmir və təsdiqləmir.

Standart `export_wcu_workload_snapshot` şifrəli, `REPEATABLE READ READ ONLY`
ixracında `leyla_reference_graph` altı sabit jurnalın, iki yük sətrinin və
dəqiq müəllim/fənn/semestr sillabuslarının tam reverse closure-unu verir.
Hidden M2M cədvəlləri və modelin bütün elan edilmiş reverse əlaqələri daxildir.
Hər model üçün say və tam-sətir SHA256, hər sətir üçün PK, FK-lər, lifecycle
statusu və SHA256 çıxır; qiymət və sillabus mətni çıxmır. `named_reference_hold`
və `named_enrollment_content_hold` bütün uyğun sətirlərdə birlikdə göstərilir.
`leyla_subject_cohorts` eyni müəllim/semestrin dörd dəqiq fənn üzrə cari jurnal
bağlarını verir. Bu diaqnostika writer qoruyucularını keçmir və yeni tətbiq
icazəsi sayılmır; məlum olmayan əlaqə ayrıca məzmun baxışı tələb edir.

Canlı dry əməliyyat bütün `_base_manager` və hidden M2M reverse əlaqələrini
sərhədli şəkildə kilidləyib hash edir. User/tenant, silinmə/bloklama bayraqları,
mövcud mərkəzi müəllim icazəsi, immutable worker863/source fənn/qrup xəritələri,
saatlar, bütün aktiv roster, 550 xananın cari dəyərləri və mövcud təsdiqlənmiş
sillabusun body hash-i yenidən yoxlanır. Mənbə və canlı cədvəl bir-biri ilə
əvəz olunmur: köhnə clone slotları istehsalata kor-koranə köçürülmür.

## CLI — GHA yolu hələ qoşulmayıb

Əvvəl dry çağırın; stdout yalnız status, say, hash və receipt göstərir:

```sh
python manage.py repair_reviewed_leyla_catalog --actor OPERATOR
```

Təzə Named sübutunu və canlı dry planını nəzərdən keçirəndən sonra həm tam
baseline, həm də altı cari source-slotun tam-sahə hash-i ayrıca tələb olunur:

```sh
python manage.py repair_reviewed_leyla_catalog --actor OPERATOR --apply \
  --expected-baseline BASELINE64 --expected-schedule-sha SCHEDULE64
```

Təkrar eyni tətbiq yeni slot, qiymət və ya receipt yaratmır. Geri qaytarma:

```sh
python manage.py repair_reviewed_leyla_catalog --actor OPERATOR --undo APPLY_RECEIPT
python manage.py repair_reviewed_leyla_catalog --actor OPERATOR --undo APPLY_RECEIPT \
  --apply --expected-baseline FRESH_UNDO_BASELINE64
```

Undo yalnız dəyişməmiş after-state üçün iki `subject_id` bağını və altı orijinal
slotu dəqiq bərpa edir. Yaradılmış altı slot silinmir, park olunur; audit və
WorkloadAmendment reyestri saxlanır. Sonrakı qiymət/sillabus/cədvəl dəyişməsi,
yeni slot əlaqəsi və ya kənar cədvəl konflikti undo-nu dayandırır. Undodan
sonra avtomatik yenidən tətbiq yoxdur; ayrıca təzə baxış tələb olunur.
