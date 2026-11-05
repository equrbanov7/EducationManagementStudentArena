# 5 noyabr 2026 — jurnal, sillabus, QB və bal düzəlişlərinin davam qeydi

İstifadəçi auditdə tapılan problemlərin düzəldilməsini və sonda deploy-u tapşırıb.
Claude-un işlədiyi əsas checkout-a və onun CI/CD işlərinə toxunmaq olmaz.
Deploy yalnız paralel işlər bitdikdən və yekun birləşmiş kod yoxlanıldıqdan sonra edilir.
İstifadə limitinin qalan 5%-ə çatdığı görünərsə, yoxlanmış işi commit edib qalanları
bu qeyd və aşağıdakı xüsusi siyahı ilə davam üçün saxlamaq tapşırılıb.

## İş sahəsi və ilkin vəziyyət

- Worktree: `/Users/elvin/.codex/worktrees/journal-syllabus-qb-audit/EMSArena`
- Filial: `codex/audit-remediation-20261105`
- Başlanğıc: `c4ca2c1ff73614d1e60897b66835a87a8f86c63f` (`origin/main`).
- Əvvəlki read-only audit filialı və `959c194df` commit-i ayrıca qorunur.
- Production qiymətləri və QB-lər bu işdə hələ dəyişdirilməyib. Aşağıdakı yalnız
  sillabusun tarixi mənbə əlaqəsi düzəlişi tətbiq olunub.
- Yoxlanmış commitlər: `4cc1f6788` (sillabus scope), `428c3c06b` (şifrəli audit),
  `2ba4e94c0` (qiymət, apellyasiya və purge qoruması), `97e17dddd` (Solmaz host
  diaqnostikası), `c77f1f6d0` (final zalının bağlanmasında deadlock). Deploy hələ edilməyib.
- Draft PR: <https://github.com/equrbanov7/EducationManagementStudentArena/pull/204>.
  İlkin CI-də lint, Docker, secret/security scan və prod-smoke keçib; son commit
  üçün bütün tələb olunan yoxlamalar ayrıca tamamlanmalıdır.

## Hazırlanan proqram düzəlişləri

1. Final və Midterm cəhdlərini eyni fənn adına görə deyil, faktiki yazılacaq jurnal
   xanasına görə müqayisə etmək; başqa semestrdəki cəhd köhnə jurnalın apellyasiyasını
   bloklamamalıdır. Təkrar imtahanın ayrıca xanası da nəzərə alınır.
2. Effektiv bal hesabında xəta yarananda xam balı yazmamaq; daha yeni sənədli əl
   düzəlişini köhnə onlayn cəhdlə əvəzləməmək.
3. Yalnız `completed` təkrar imtahan balını yekuna daxil etmək. Tarixi semestrlərin
   mövcud `max(main, resit)` qaydası saxlanır.
4. Tarixi bal növbəsində legitim kəsilməni səhv saymamaq; təsdiqli 50-ballıq şkalanı,
   tarixi Level istisnasını və naməlum şkalanı ayırmaq. Xam tarixi nəticə dəyişdirilmir.
5. Fənn/semestr dəyişəndən sonra köhnə sillabus əlaqəsinin yanlış məzmun göstərməsini
   dayandırmaq. Köhnəlmiş redaktor səhv fənnə yeni dosye yarada bilməməlidir.
6. Sabit təşkilat üçün şifrəli, yalnız oxuyan audit ixracı. Yeni ixrac FinalGrade,
   ExamScoreEntry, ResitRecord, LegacyGradeFact/Review, rəqəmsal apellyasiya və kredit
   tarixçəsini də əhatə edir. FinalGrade olmadan qalan tarixi resit də ixraca düşür.
7. Aktiv cavab-açarı düzəlişi sonradan bitən cəhdə də tətbiq olunur; fərdi apellyasiya
   ilə ikiqat artım olmur. Kredit, audit və cəhdin bitməsi birlikdə commit olur.
8. Səhv cəhd silinərkən başqa semestrin nəticəsi bərpa mənbəyi seçilmir. Silinən
   rəqəmsal apellyasiyanın mənbə sübutu append-only auditdə saxlanır. Arada daha
   üstün sənədli bal varsa nəticəni boşaltmaq əvəzinə purge bloklanır.
9. Kağız Midterm və sənədli final nəticəsi köhnə rəqəmsal cəhd replay-i ilə əzilmir.
10. Tamamlanmamış resit QB önizləməsində, fast analitikada, tələbə xülasəsində və
    Excel ixracında rəsmi nəticə sayılmır. Tələbə xülasəsi də donmuş tarixi dövrdə
    əsas/təkrar imtahanın maksimumu üzrə canonical qaydanı istifadə edir.

## Yoxlamalar

- Bütün sillabus testləri + offline audit + real read-only ixrac sxemi: 455 test keçib.
- Sillabus lookup/sharing/performance və language cohort/student səthləri: 79 test keçib.
- Tarixi nəticə/retake/analytics: 71 test keçib; əvvəlki kodda 4 regressiya təkrar təsdiqlənib.
- Completion, rəqəmsal sync və kağız Midterm inteqrasiyası: 152 test keçib;
  4 test real PostgreSQL paralel apply/finish/revoke yarışını yoxlayır.
- Purge, manual bərpa sərhədi və reset: 90 test keçib. Son reviewer final-center
  `end_room` xarici lock sırasındakı deadlock-u real PostgreSQL ilə təkrar yaratdı;
  düzəlişdən sonra final-center/completion/yeni yarış üzrə 107 test keçib.
- Solmaz host diaqnostikası və private transport: 61 test keçib.
- Əlavə resit/QB/fast summary uyğunluğu: 22 test; Excel ixracı və tələbə kartı: 26 test keçib.
- Bu dəstlərin bəziləri kəsişir; saylar unikal test cəmi kimi toplanmamalıdır.
- Modul ölçüsü, modul/public API sərhədləri, bütün repo black/isort/flake8,
  `manage.py check` və `makemigrations --check --dry-run` keçib. Son əlavə dəyişikliklərdən
  sonra uyğun yoxlamalar yenidən tamamlanmalıdır.
- Cari `config.settings.test` PostgreSQL tələb edir. SQLite cəhdi konfiqurasiya tərəfindən
  dayandırılıb; real testlər yalnız ayrıca yerli PostgreSQL bazalarında aparılıb.

## Production-da təsdiqlənmiş düzəliş

Aydın draft lineage dövrəsində yalnız əvvəlki versiyanın səhv `source_version_id`
əlaqəsi NULL-a qaytarıldı. Mövzu, status, müəllif, timestamp və akademik qeydlər
native qoruma hash-ləri ilə dəyişməz təsdiqləndi.

- İlkin dry-run: `41954545793`, `dry_run`, `applied=0`.
- Apply: `41955211723`, `applied=1`.
- Qəbz: `2d8e0c0e-f2a1-4fab-b042-e41134de5881`.
- Təkrar dry-run: `41955318047`, `already_applied`, `applied=0`, eyni qəbz.
- Geri qaytarma native `reviewed-aydin-lineage.yml` workflow-da bu qəbzin `undo`
  girişi və təzə undo dry-run baseline-i ilə mümkündür. Bu qeyddə undo icra edilmir.
- Bu düzəliş çatışmayan mövzuları doldurmur və draft-ları təsdiqləmir.

## Canlı məlumatlar üzrə qalan iş

Bu siyahı həll olunmuş məlumatların siyahısı deyil. Kodun düzəlməsi köhnə qeydlərin
avtomatik düzəldiyini sübut etmir.

- Sual 3600: qəbul olunmuş üç apellyasiya və rəsmi mənbə 18 iyun 2001 cavabını təsdiqləyir.
  Əvvəlki canlı auditdə əlavə 33 tələbənin krediti çatışmırdı. Təkrar canlı yoxlama,
  mövcud auditli cavab-açarı düzəlişi və hər təsirlənən jurnalın tutuşdurulması qalır.
  Köhnə 466 cəhdin gözləntisi private JSON-da: 33 artım, 433 dəyişməz; ilkin global
  əməliyyat 36 credit qeydini yaratsa da 3 fərdi apellyasiyaya təkrar bal düşmür.
  Bank sualının cavab açarı ayrıca müqavilədir; global kredit bunu dəyişmir.
- Eyni müəllimin mənbələri üzrə 71 sillabus boşluğu: 34 hədəfdə ilkin flagsız namizəd,
  onlardan 30-da tək məzmun ailəsi var. Fəaliyyət saatı, kafedra, dil, təsdiq, müəllim
  və hədəfin boşluğu təzə məlumatla yenidən təsdiqlənmədən bağlama edilməməlidir.
- Başqa müəllifin 136 mənbəsi öz sillabusunun paylaşılması qaydasına avtomatik daxil edilmir.
- Təzə metadata yalnız 4 hədəfdə müşahidə edilən müəllim/fənn/dövr/sektor/plan
  uyğunluğunu saxlayır. Onların 8 sabit content batch-i read-only yenidən çıxarılır;
  təzə body/chair/approval/program yoxlanmadan share edilməməlidir.
- Aida-nın köhnə planındakı boş sayılan jurnalda indi 11 dərs/241 qiymət var;
  köhnə planın qoruma şərtləri pozulur. Yeni akademik tarixçəni qoruyan plan lazımdır.
- Solmaz dry-run `41954695528` `solmaz_host_refused` ilə rədd olundu. Şifrəli
  faylın lokal hash-i düzgündür; runner mərhələsi üçün məhdud təhlükəsiz diaqnostika
  hazırdır. Deploy-dan sonra native dry-run təkrarlanmalıdır. Mənbə, head, actor
  və baseline qapıları zəiflədilməməlidir.
- Yanlış fənn adları, boş şablon mövzuları və həqiqi sillabussuz fənlər üçün rəsmi
  fənn/yük/sillabus mənbəsi lazımdır; məzmun uydurulmamalıdır.
- Paralel qeydiyyat, 9/10 ziddiyyəti və təkrar QB namizədlərində düzgün saxlanacaq
  jurnal və real davamiyyət mənbəyi təsdiqlənməlidir. Maksimum bal seçmək, QB-ni
  silmək və ya artırmaq şübhədən avtomatik nəticə çıxarmaq deyil.
- İki inactive jurnalın absence cache-i üçün əlavə read-only capture aparılır.
  Birinci qeyd 2 noyabrda 5 real absent xana/10 saat ilə uyğun idi, sonra dərslər
  silinib. Cari raw=0 olması tarixi qayıbın səhv olduğunu sübut etmir; silinmə və
  köçürmə qərarının authority izi tapılmadan counter avtomatik sıfırlanmamalıdır.
- Günel/233KE/Optimallaşdırma və Claude-un MR-159/165/167/203, MR-171/110, MR-183
  işləri təkrar tətbiq edilmir; Claude bitirdikdən sonra nəticə yenidən yoxlanır.

## Xüsusi sübutlar və davam ardıcıllığı

Şəxsi akademik məlumatlar Git-ə qoyulmur. Əsas xüsusi qovluq:
`/Users/elvin/Desktop/RIM/Secret/final-score-audit-20261105/remediation/`

- `01-tracking-checklist.json`: 37 kateqoriya və fərdi tapıntılar.
- `06-workflow-queue.json`: mövcud əmrlər üçün dəqiq dry-run/apply giriş şablonları.
- `07-authoritative-source-pointers.json`: mənbə sənəd/legacy göstəriciləri.
- `08-unflagged-34-revalidation.json`: ilkin 34 hədəfin mənbə seçimi.
- `metadata-refresh-dispatch.json`: təzə read-only ixracın run ID-si və gedişi.
- `metadata-refresh-delta.*`: 02:08:55Z metadata müqayisəsi; raw hüceyrə auditi deyil.
- `lineage-*-dispatch.json`: canlı dry-run/apply/post-check qəbzləri.
- `four-target-syllabus-export-queue.json`: 4 hədəf üçün 8 dəqiq content batch girişi.
- `../question-3600-review/global-correction-readiness.*`: tətbiq və geri alma proseduru.

Son UI yoxlamasında Mac kilidli idi; Claude-un hazırkı idle vəziyyəti görünmədi.
Əsas checkout təmizdir, lakin bu təkbaşına Claude-un işinin bitdiyinin sübutu deyil.
Merge/deploy qabağı Claude və CI/CD-nin sakitliyi yenidən təsdiqlənməlidir.

Növbəti agent əvvəl Git statusunu, CI/CD-ni və Claude-un real iş vəziyyətini oxumalıdır.
Naməlum dispatch nəticəsində təkrar POST göndərməməli, qeydə alınmış run ID-ni yoxlamalıdır.
Təzə snapshot ilə hər konkret tapıntı yenidən müqayisə edilir; icra edilən dəyişikliklərin
before/after qəbzi və geri qaytarma yolu saxlanır. Rəsmi mənbəsi çatışmayan bəndlər
“həll edildi” kimi bağlanmır.
