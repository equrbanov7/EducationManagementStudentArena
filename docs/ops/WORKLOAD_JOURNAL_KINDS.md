# Dərs yükü → jurnal növləri və müəllim payları

Jurnal siyahısının növ etiketi, SQL növ süzgəci və jurnal içindəki pillələr
ScheduleSlot/Lesson ilə yanaşı exact fənn+dövr+fiziki qrupun müsbət yük növlərini
oxuyur. Hələ yazılmamış seminar/lab görünür; saxta dərs sütunu yaradılmır.
Ləğv edilmiş yük sənədi və qrupsuz açılış başqa qrupun planını daşımır.

Yükün canonical offering sync-i hər müəllimin müsbət lecture/seminar/lab
təyinatından `source=workload` növ payı yaradır. Müxtəlif müəllimlərin payları
yalnız onların növlərini göstərir; tək sahib üçün əlavə pay yaranmır. Müəllim
aktiv və həmin təşkilatda canlı `grade.input` səlahiyyətli olmalıdır.

Manual/legacy paylar, tələbə seçilmiş payların scope-u, aktiv təhvil qərarı,
fərqli jurnal sahibi, bağlı jurnal və kilidli semestr qorunur. Yük müəllimi
çıxarılanda yalnız avtomatik pay deaktivləşir; keçmiş dərslər/müəlliflər və
qiymətlər saxlanır. Eyni növdə iki müəllimin tələbə sərhədi bilinmirsə bütün
rosterə giriş verilmir: `ambiguous` qaytarılır. `groups_note` yalnız məlum
fiziki qrup ad/kodlarından ibarətdirsə həmin qrupa tətbiq olunur; yarımqrup
haqqında sərbəst mətn təxmin edilmir. Aktiv manual/legacy bölgü əvəzlənmir.

## Mövcud jurnallar üçün dar bərpa

`resync_task_offerings` yeni jurnal və enrollment yarada bilir. Aşağıdakı əmr
yalnız mövcud aktiv jurnalların paylarını bərpa edir:

```sh
python manage.py sync_workload_journal_shares --org qku --year 2026/2027 --actor USER
python manage.py sync_workload_journal_shares --org qku --year 2026/2027 --actor USER \
  --expected-baseline DRY_RUN_BASELINE --apply
```

Defolt dry-run eyni canonical yazını atomik tranzaksiyada hesablayıb geri alır.
Apply üçün dry-run baseline-ı məcburidir. Baseline task/row/assignment/physical
group, mövcud offering və share, canlı müəllim/rol/üzvlük, semestr və akademik
məzmun vəziyyətini bağlayır. Mənbə row/assignment/M2M kilidləri prefetch-dən
əvvəl alınır ki, təzə baseline köhnə yaddaşdakı planla qarışmasın.

Workload, ownership, manual/legacy paylar, üzvlük və rol dəyişsə və ya akademik
məzmunun tam-sahə hashı fərqlənsə bütün batch rollback olur. Böyük mark dəstləri
Python yaddaşına çıxmır: DB ordered row-JSON MD5 + count hesablayır; baseline
bu nəticələri SHA256 ilə bağlayır. MD5 yalnız dəyişmənin aşkarlanması üçündür.
Parol, tələbə adı və qiymət dəyərləri stdout-a çıxmır.

ProdDataOps `command=sync_workload_journal_shares`, `year=2026/2027`,
`batch=baselineSHA` (yalnız apply), `roster_tag` boş. Adi backup və
`apply=true`/`confirm=APPLY` qorunur. Çıxış `workload_shares:` prefix-li numeric
saylar və baseline-dır. Bütün kafedralar bir batch-dır; yeni deploy hər müəllim
üçün təkrarlanmır. Əvvəlcə workload və qrup bərpalarının tətbiqi tamamlanmalıdır.
