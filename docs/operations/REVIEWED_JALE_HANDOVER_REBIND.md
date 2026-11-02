# Jalə: canonical təhvildən sonra bir fənn bağının düzəlişi

MR-000082 üzrə dörd əcnəbi qrup jurnalı artıq mövcud canonical təhvil
axını ilə `NULL → 7730` keçirilib. Tətbiqdən əvvəlki/sonrakı UI sübutunda
55 tələbə qeydiyyatı, 66 dərs və 616 xana saxlanıb. İkinci qrupun dolu
`73d33235-…` jurnalında səhv `1797` fənn kodu ayrıca qalır.

`repair_reviewed_jale_subject` indi həmin **tamamlanmış təhvil vəziyyətini**
tələb edir: dörd jurnalın sahibi `7730`, dörd geri qaytarılmamış təhvilin
əvvəlki sahibi `NULL`, yeni sahibi `7730`, aktoru `8444` olmalıdır. Yeni
təhvil, hesab birləşməsi və ya rol təyinatı yaratmır.

Mənbə provenance-i dəyişmir: legacy worker `949 → 8388`, jurnal `13980`,
öz mənbə sillabusu `7456/2295`. `8388`-in mövcud dörd legacy jurnal payı,
hər iki hesabın profil/üzvlük məlumatları və sillabus müəllifliyi saxlanır.
Bu düzəliş yalnız target kursun `subject_id` sahəsini `1797 → 2295` dəyişir.
`7730` hazırkı səlahiyyətli müəllim olmalıdır; mənbə müəllifliyi ona yazılmır.

## Tətbiqdən əvvəl və sonra

1. Bu kod CI/deploy-dan keçdikdən sonra mövcud standart şifrəli workload
   exportu götürün. Yeni sabit `jale_current_handovers`,
   `jale_current_journal_shares`, `jale_account_memberships` sahələri dörd
   təhvilin tam ID/səbəb/tarixini və iki hesabın mövcud əhatəsini göstərir.
   Şəxsi identifikator, parol, e-poçt və telefon ixrac edilmir.
2. Təzə exportdakı dörd təhvilin ID/səbəb/vaxtını UI əməliyyatına bağlayın;
   səbəb və ya ID təxmin etməyin. Köhnə `NULL` sahibi gözləyən operatorun
   review/manifest-i istifadə edilmir.
3. Yeni operator surətində hazırlanmış review yalnız deploy olunmuş yeni
   HEAD, uğurlu CI və deploy sübutuna bağlanır. Dry-run → bir apply →
   repeat dry-run → RAW082/SYL082/SYL035 və standart POST müqayisəsi.
4. Bütün dörd jurnalın 55/66/616 sayları və tam reverse graph hash-ləri,
   ayrıca target-in 15/15/106 sayları qorunur. Undo yalnız bu fənn FK-sını
   geri qaytarır; tamamlanmış canonical təhvilləri geri almır.

## Sonrakı ayrıca hesab birləşməsi

Sahib iki hesabın eyni şəxs olduğunu ayrıca yoxlayıb və `8388 → 7730`
birləşməsini təsdiqləyib. Əvvəl fənn düzəlişi və onun təkrar/POST yoxlaması
bitməlidir: həmin düzəliş aktiv alias və dəyişməmiş dörd legacy pay tələb edir.

`reviewed-jale-merge.yml` hazırlanıb, işə salınmayıb. Deploy olunmuş HEAD
yoxlaması və production-deploy mutex-i saxlanır. Defolt dry-run bütün reverse-FK
əlaqələrini sayır; üçgünlük private artifact yalnız ID, say, hash, əməl və
bloker kodlarını ehtiva edir. Ad, parol və qiymət çıxarmır. Root `eligible`,
`holds`, hər əməli yoxlayıb təzə `baseline_sha256` ilə `apply=true`,
`confirm=APPLY` verir. Yeni əlaqə və ya vəziyyət dəyişikliyi tətbiqi dayandırır.

Yalnız açıq icazəli cari əlaqələr köçür: jurnal payı (eyni sətir, növ və
tələbə bağları), müəllim yükü və illik profil, bölmə rəhbəri və təşkilat
bildirşlərinin alıcısı. Aktiv rollar mövcud duplicate-account xidməti ilə,
jurnal sahibliyi rəsmi təhvil xidməti ilə keçir. Konfliktli pay/yük profili,
naməlum əlaqə və başqa tenant istinadı bütöv tranzaksiyanı bloklayır.

Sonra mövcud geri qaytarıla bilən soft-delete işləyir. Tarixi müəlliflər və
worker949 körpüsü dəyişmir; hard-delete edilmir. Audit receipt köçürülən
sətirlərin əvvəlki vəziyyətini və son hash-lərini saxlayır. `HOLD` uğurlu
birləşmə sayılmır. Təkrar tətbiq aktiv-alias qapısında yazısız dayanır.
