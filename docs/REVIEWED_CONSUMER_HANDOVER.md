# 534 MRK: İstehlakçı davranışı üzrə cari müəllim təhvili

Bu paket yalnız bir fənnə aiddir: açılış27b96834-6c7d-4747-8bf6-b739624340f1,
QKU1478,534MRKaz, cari2026/2027payız. Cari8103AydınRəfiyevdən
8218ÜlviyyəXudaverdiliyə təhvil və mövcud30mühazirə+30seminar təyinatının
müəllim dəyişikliyi tək tranzaksiyada aparılır. Yeni saat/yük sətri yaranmır.

## Bir-birini təsdiqləyən dəqiq mənbə

Marketinq blank19:5 və22:5də Ülviyyə534MRK “İstehlakçı davranışları” jurnalının
olmadığını bildirir. Maliyyə blank24:6da Aydın534MRK “İstehlakçı davranışı”nı
tədris etmədiyini bildirir. Bu iki qarşılıqlı müəllim ifadəsi user/root tərəfindən
cari təhvilin səlahiyyəti kimi qəbul edilib. Rəsmi Marketinq yükExcelinin mövcud
olduğu iddia edilmir.30+30 rəqəmi dəyişməyən mövcud, releasedAMENDED sətirdəndir.
Üç original workbookSHA və dəqiq sətirlər compiledspec-də sabitdir.

Native `TeachingHandover.created_at` faktiki icra vaxtıdır.28oktyabr Consumer
üçün mənbədə yazılmayıb və uydurulmur. 28oktyabr yalnız ayrı533İMarketinq
şikayətindədir. Aydının tarixi dərsləri və qiymət müəllifliyi dəyişmir.

Typed source identity: worker613→8103,774→8218,group657→534MRKaz,
subject1478→dəqiq cari subject. Altı canonical mapping-in state/target/sourcehash/
transform sahəsi runtime-də dəqiq yoxlanır. Legacyjournal13976 hələ613 sahibini
saxlayır; bu, keçmiş mənbədir, cari təhvilin effective-date sübutu sayılmır.

1noyabr18:48:22Z authenticatedstandard/run41338272616 cariowner8103,
row07b63e53-3193-44f3-880e-bd97b1f003e9 üzrə iki30saat təyinatını və9dərs/
126xana/15qeydiyyatı təsdiqləyir. MövcudRAWchair-cells-014 eyni akademik
qrafı göstərir. Privatecase planSHA:
`82587a424581e664266387aeda75ab04a79adf343625705a7569e97d5e53870f`.
Təzə productionPRE yenə tətbiqdən əvvəl məcburidir.

## Dəyişiklik və qoruma

`repair_reviewed_consumer_handover` defaultdry-dir. Dəqiq aktor/tenant,
kanonik workload.distribute və journal.reassign qapıları, müsbət releasedsətir,
aktiv iki müəllim, təzə baseline tələb olunur. Başqa müsbət allocation, aktiv
journalshare, naməlumhandover, bağlı jurnal, dəyişmiş count və sourcebridge HOLDdur.

İki mövcud assignmentID eyni qalır. `assign_teacher(...assignment=existing,
sync_offerings=False)` saatı/note/groups/paidstatus-u saxlayaraq müəllimi dəyişir.
Daha sonra kanonik `handover_actions.reassign` sahibi dəyişir. Bir hissə xətası
hamısını rollback edir. Currenthandover timestamp auditlidir, backdateinput yoxdur.

Tam reversegraph/SQL hash dərslər, bütün qiymətlər (0daxil), enrollment/SAR,
transfer, imtahan/korreksiya əlaqələri və bütün sillabus gövdələrini qoruyur.
Yalnız course.instructor və ikiassignment.teacher/assigned_by/updated_at dəyişə
bilər; tək yeni canonicalhandover ayrıca təsdiqlənir. Yeni sillabus, paylaşma,
copy,approve və müəllif dəyişməsi yoxdur. Köhnə müəllim canonical observerhistory
vasitəsilə öz əvvəlki jurnalını oxuya bilir.

Repeat0 və dəqiq receiptdən explicitundo mövcuddur. Undo yalnız dəyişməyən
postgraphda nativehandoverrevert və originalallocation metadata restore edir;
handoverevent silinmir, reverted olaraq auditdə qalır. Automaticundo yoxdur.

Workflow `reviewed-consumer-handover.yml` productionenvironment və ümumi
production-deploy mutex istifadə edir; host deployedHEAD, exactCLI, input,
count1/0, baseline/receipt və safeerror whitelist yoxlayır. Dərs/qiymət gövdələri
log/artifacta çıxmır. Rootoperator təzə standard+RAW014→dry→oneapply→repeat0→
poststandard+RAW014 müqayisəsini serialize etməlidir. Paket hazırlanarkən prod
POST,dispatch və mainpush edilməyib.

## Ayrı saxlanan şikayətlər

- 534BİMarketinq: Ülviyyənin jurnalsızlıq tələbi var; Aydının24:5 ifadəsi isə
  BİBiznesinəsasları haqqındadır. İki fənn birləşdirilmir.
- 534MRKMarketinq: cari0a78f884...rəsmi sətir0/0 və vakantdır; legacycourse75
  və müəllim tələbindən yeni müsbət bölgü uydurulmur.
- 534BİBiznesinəsasları: Aydın tədris etmir, yeni müəllim dəqiq göstərilməyib.
- 533İMarketinq: Aydının28.10.2026dan tədris etmədiyi dəqiqdir; yeni sahib
  məlum deyil. Jurnal/qiymətlər silinmir və hansısa başqa müəllimə verilmir.
