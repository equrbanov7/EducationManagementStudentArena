# Source58 üçün tam audit sübutunun təhlükəsiz çıxarışı

`source58-audit-chunks.yml` yalnız sabit Source58 bərpa scope-unun auditini
oxuyur. Mövcud native recovery-ni tətbiq etmir, onun 8 MiB aggregate / 1 MiB
unknown-audit limitlərini dəyişmir. Naməlum audit, silmə və clear niyyəti
istisna edilmir; bu çıxarış heç bir bərpaya icazə vermir.

Giriş yalnız aktiv təşkilat superadmininin `actor` istifadəçi adıdır. Host
mövcud `verify_head` ilə deploy olunmuş HEAD-i təsdiqləyir. Native komanda
PostgreSQL repeatable-read/read-only transaction, tenant RLS və mövcud actor
validatorundan istifadə edir. Primary scope üçün native ilə eyni bounded
academic/credit closure və exact audit locator işlənir; parity testi drift-i
rədd edir. Sonradan hər iki collector birlikdə yenilənməlidir.

İlk olaraq bütün uyğun auditlərin ID, exact PostgreSQL `row_to_json` SHA256
və bayt uzunluğu oxunur. 1000 audit və 64 MiB ümumi forensic həddi aşılırsa
çıxarış dayanır. Bu, recovery həddinin artırılması deyil: nəticə tətbiq üçün
həmişə yararsızdır. Tam auditlər bir-bir oxunur və həmin SHA/baytlarla
müqayisə olunur; JSON yenidən serializasiya edilmədiyi üçün ilkin baytlar
bütövlükdə saxlanır.

Hər audit 256 KiB parçalara ayrılır, yaddaşda şifrələnir, sonra ZIP-ə yalnız
şifrəli envelope yazılır. Şifrəli final manifest bütün sıralı auditləri,
raw SHA/uzunluqları, hər parçanın sıra/offset/uzunluq və plaintext/cipher SHA
izlərini bağlayır. Exact audit sayı tamamlanmayıbsa manifest yaranmır və
qismən fayl silinir. Təyinat əvvəl varsa üzərinə yazılmır. Fayl yaranarkən
0600-dır. Stdout yalnız şifrəli ZIP-in SHA izini göstərir; xəta səbəbləri
şəxsi məlumat çıxarmayan sabit kodla əvəz edilir.

Review zamanı manifestin bütün auditləri və ardıcıl parçaları daxil etdiyini,
parçalar birləşdirildikdə raw SHA/bayt uzunluğunu və locator inventory sayını
ayrıca yoxlayın. Hər auditdə clear/delete/correction/undo niyyətini tam
araşdırın. Bu sübutdan `no audit`, `no credit`, `no clear` nəticəsi çıxarmayın.
Yalnız ayrıca review edilmiş tam hash-bound semantik pin gələcək native
review-a namizəd ola bilər; generic resource prefix istisnası yolverilməzdir.

Komanda: `export_wcu_source58_audit_chunks --actor USER --public-key PUBLIC_PEM
--output NEW_CIPHERTEXT_ZIP`. Yalnız xüsusi workflow transportu tətbiqdəki
public key pinini və encrypted-before-copy qaydasını təmin edir. Lokal
hazırlama zamanı workflow dispatch, native execute və prod yazısı edilməyib.

## Worker atomic audit istisnası

`check_worker_atomic_coverage.py` yalnız bu komanda üçün dəqiq istisna saxlayır.
Səbəb DB-yə toxunmaması deyil: bütün oxumalar `capture()` daxilində özü açdığı
**yeni REPEATABLE READ READ ONLY** transaction-da, sabit təşkilat və
`bypass=False` RLS kontekstində edilir. Xarici `worker_atomic` bu fresh guard-ı
pozardı. `test_source58_audit_capture.py` real PostgreSQL-də write rejection,
outer-atomic rəddi, dəyişməz auditlər və tenant/user/bypass kontekstini yoxlayır.
