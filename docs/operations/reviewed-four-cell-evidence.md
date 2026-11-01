# Dörd mövcud dərs xanasının məhdud yoxlanması

Bu paket bərpanın icra edildiyini bildirmir. Mənbə nöqtələri yalnız
5458056, 5558632, 5558637 və 5558643-dür. Mənbədə hamısı `qb`, excusable=0,
score yoxdur; 0 qiyməti və i/e ilə əvəz edilmir. İki dəqiq mövcud seminar dərsi
və dörd dəqiq aktiv qeydiyyatdan başqa yeni dərs və ya roster yaradılmır.

`export_wcu_four_cell_history --actor USER --public-key PATH --output PATH`
əmri PostgreSQL-də yeni REPEATABLE READ READ ONLY transaction açır. Yalnız
sabit tenant/scope, aktiv tenant superuser, sorğu/vaxt/sətir/bayt limitləri ilə
AuditLog, typed ledger, correction/reversal, hygiene və LegacyGradeFact/Artifact
sübutunu toplayır. Mətnlər, kontaktlar və sərbəst JSON çıxmır; məhdud typed
identifikatorlar, vəziyyətlər və server SHA-ları şifrələnir. Ayrı workflow
uzaqdakı build SHA-nı checkout ilə tutuşdurur. Müəyyən olunmayan AuditLog
sətirləri və tarix/kind etiketinin saat daşımaması ayrıca görünür.

Mövcud `repair_reviewed_journal_content` mühərriki eyni iki target üçün ayrıca
SHA-pinned dörd sətirlik paketi qəbul edir. Paket SHA:
`00fd00569b1a1af9460c57db647313622a70b0026d06716cf3843311d490ba1f`.
Mənbə adı/əlaqə məlumatları kodda saxlanmır. Köhnə bazanın fiziki dəyişməzliyi
və course/enrollment ledger-i iddia edilmir: on typed worker/student/subject/group
ledger-i və dəqiq relational tuple tələb olunur. Mənbə 16-sahə hash-ləri physical
17-sahə DB sətrinin hash-i kimi təqdim edilmir.

Tətbiqdən əvvəl fresh export nəzərdən keçirilməli, bütün 90 sabit batch və 1791
root üzrə müqayisə/universe receipt-i ilə əlaqələndirilməlidir. Runtime mühərriki
həmin dörd tələbə/subject/period/date/time/kind üçün bütün canonical offering-ləri
(active/inactive, enrolled/dropped) ayrıca yoxlayır; başqa canonical nüsxə saxlanır
və ikinci nüsxə yaradılmır. Formal correction, gradefact, hygiene, silmə/təmizləmə,
malformed grade intent, undo marker və ziddiyyətli ledger saxlayıcı guard-dır.

Adi audit best-effort-dur; qeydin olmaması silinmənin heç vaxt baş vermədiyinin
riyazi sübutu deyil. Bu məhdudiyyət apply qəbzində qeyd olunur. İstifadəçinin
mənbə ilə sübutlu boş xana bərpası icazəsi əsasında mövcud tam əlçatan audit
scope-da əks sübut yoxdursa case namizəd qala bilər; ayrıca müəllim təsdiqi
tələb edilmir. Digər 338 held mənbə xanası bu icazəyə daxil deyil.

Fresh baseline həm akademik vəziyyəti, həm available history/source claim-ləri
əhatə edir. Writer yalnız boş LessonMark yaradır, authorship NULL saxlanır;
mövcud bütün lesson/mark, hüquq, roster, SAR və authorship fingerprint-ləri
qorunur. Canonical sanctioned absence recompute işləyir. Başqa dəyişiklik,
sonradan gələn audit və ya guard xətası bütün transaction-u geri qaytarır.

Geri qaytarma ayrıca `undo_reviewed_four_cells --org qku --actor USER
--manifest PATH --batch RECEIPT` ilə defolt dry-run-dır. `--apply
--expected-baseline SHA` yalnız orijinal apply qəbzinin yaratdığı dəyişməz mark
subset-ni silə bilər. Orijinal before fingerprint, cache recompute və protected
fingerprint tam bərpa olunmursa bütün undo rollback olur. Müəllimin sonrakı
işinə toxunulmur. Undo qəbzi gələcək avtomatik diriltməni saxlayır.

## Syllabus capture sürəti

Ayrı `syllabus-content-packs.yml` həmin sabit 90 batch-i 19 fixed pack-də, hər
biri ən çox 5 ardıcıl müstəqil capture ilə işləyir. Hər çağırış ayrıca READ ONLY
transaction, əvvəlki cap və müstəqil cipher saxlayır. Union limit artırılmır,
silent skip yoxdur; explicit held/quarantine və always-finalizer saxlanır.
Bu müxtəlif anlarda çəkilən read-only sübutdur, vahid atomik snapshot deyil.
