# MR-000027 bərpası

`recover_mr27_journal` yalnız QKU tenant-ının `567a6fc3-df03-4cac-beca-7f0674ea9137` jurnalını, 2026/2027 payız dövrünü və legacy 902 qrupunu qəbul edir. Aktor aktiv superadmin olmalıdır. Default dry-run eyni əməliyyatları atomik tranzaksiyada yoxlayıb geri alır. Bütün yazılar tenant və aktor RLS əhatəsində qalır.

## Mənbə və yaradılan məlumat

Legacy 10127 və 10128 tələbələri, həmçinin 103 ixtisası ilkin cutover-dən sonra, 14.09.2026-da yaranıb. Master proqramı olmadığı üçün əvvəlki delta hesabları yarada bilməyib. Mənbədəki `Bioekelogiya`, `005566`, `mag`, 2026 və əyani atributlarına cutover-in mövcud `_speciality`, `_group`, `_program_plans` qaydaları tətbiq edilir. Daxili proqram kodu `005566-M`, master siyasətinə uyğun kredit yükü 120 ECTS olur. Bu daxili kod cari dövlət şifri kimi göstərilmir.

Qrupun köhnə `curricula168` istinadı başqa ixtisasa aid olduğuna görə onun dərs planı götürülmür. Canonical intake proqram 103/master və qəbul 2026 üçün boş curriculum yaradır. İki legacy kimliyi `legacy_accounts.create_legacy_student` ilə yaradılır: aktiv student üzvlüyü və SAR, `.invalid` yer-tutucu email, istifadəsiz parol, `email_verified=false`. Rəsmi email və parol uydurulmur, bildiriş göndərilmir. Adaş hesaba ad əsasında birləşdirmə aparılmır. Dəqiq identifikator və ya tam kimlik toqquşması tətbiqi saxlayır. İbrahim 2510-un əsas qrupu və SAR-ı dəyişmir.

Tarixi hissə yalnız 21 dəqiq source point ID və 7 günü qəbul edir. Mövcud 6 xana saxlanır; iki tələbənin 14 xanası və İbrahimin 05.10 qayıbı əlavə olunur. Çatışmayan 05.10 saat 20:10 mühazirəsi yaradılır. Mövcud fərqli dəyərin üzərinə yazılmır. Mənbədə tarixi müəllif metadatası olmadığı üçün `entered_by` və `instructor` boş saxlanır.

`--include-teacher-assertion` ayrıca açıq bayraqdır. 22.10 seminarına 10/10/9 balları müəllimin MR27-də 28.10 saat 12:14 cavabından yazılır. Saat 20:10 istifadəçinin rutin jurnal saatını seçməyə açıq icazəsidir; rəsmi cədvəldən alınmış saat kimi təqdim edilmir. İki akademik saat mövcud Lesson default siyasətidir. Dərs müəllimi Ramiz, inzibati yazının müəllifi həqiqi aktordur. Audit bu əsasları tarixi 21 source pointdən ayrı saxlayır. Saxta source point ID yaradılmır.

## İcra

1. `scripts/build_mr27_recovery_plan.py --out <private/new-file.json>` Docker mənbəyini READ ONLY oxuyur, 0600 JSON yaradır. Stdout yalnız say və SHA256 göstərir. Plan şəxsi məlumat daşıyır və açıq release-ə yüklənmir.
2. ProdDataOps-da `recover_mr27_journal`, `roster_tag=mr27-recovery-…`, şifrəli `mr27-recovery.json.enc` asset-i seçilir. `batch` plaintext SHA256 olmalıdır. `create_missing=true` yalnız ayrıca 22.10 bəyanatını əlavə edir. Default dry-run-dır.
3. Dry-run nəticəsi: 2 Enrollment, 1 tarixi Lesson, 15 tarixi Mark. Müəllim bayrağı ilə ümumi 2 Lesson və 18 Mark. Kimlik/struktur: 2 User/Profile/Membership/SAR, 1 Specialty/Program/Curriculum. İlk 6 xana saxlanmalıdır.
4. Workflow backup və açıq APPLY təsdiqindən sonra tətbiq edilir. Təkrar dry-run-da domain create/update sayları 0, tarixi 21 və müəllim 3 xanası `already_present` olmalıdır. Ledger hər qaçışda run/observation sübutu saxlayır.

```sh
python manage.py recover_mr27_journal --org qku --actor superadmin --file <plan.json> --sha256 <64hex> --include-teacher-assertion
# Faktiki yazmaq üçün eyni əmrə --apply əlavə edilir.
```

## Kompensasiya

Apply `batch=mr27-YYYYMMDD-HHMMSS-xxxx` qaytarır. ProdDataOps-da həmin batch və APPLY ilə undo edilir; asset tələb olunmur. CLI: `--org qku --actor superadmin --undo <batch> --apply`.

Undo dəqiq after-fingerprint və əlaqəli istifadə yoxlamasından sonra yalnız paketin yaratdığı xanaları və dərsləri silir. Global AuthUser üçün yalnız manifestdəki ən çox iki yeni istifadəçinin reverse FK və forward M2M əlaqələrinə məhdud boolean-only read probe `bypass_rls()` ilə baxır. Bu, başqa tenant-da sonradan yaranmış istifadəni görmək üçündür. Xarici ID və məlumat çıxarılmır; context hər hansı yazıdan əvvəl bağlanır. Yeni parol, auth qrupu, əlaqəli istifadə və ya sonrakı dəyişiklik varsa əməl bütövlükdə dayanır.

Yeni yazılışlar dropped, SAR/curriculum/program/specialty passiv olur; hesablar canonical `block_account` ilə bloklanır. Immutable kimlik və ledger sətirləri saxlanır. Bu, auditli kompensasiyadır, fiziki DB rollback deyil. Bundan sonra yenidən apply ayrıca review tələb edir. İbrahimin əvvəlki qayıb sayğacı bərpa olunur. Yalnız sayğac düzəldən qaçış da ayrıca batch və undo auditinə malikdir.
