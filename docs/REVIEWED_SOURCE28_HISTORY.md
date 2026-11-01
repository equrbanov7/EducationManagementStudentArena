# Source28: ayrıca tarixçə təsnifatı

Bu yol yalnız mövcud sabit ce94b0cf… mənbəsinin 28 PRESENT xanası və
2026-10-29 15:15 seminarı üçündür. Mənbə, müəllim, tələbə, qrup, rəsmi fəaliyyət
bölgüsü, cari dəyər, formal düzəliş, kilid və tam-row qoruyucuları dəyişmir.

Immutable ems_prod_1027 nüsxəsinin 13 audit qeydi ayrıca nəzərdən keçirilib:

- legacy_import.empty_lesson: 8444 aktorunun 25 oktyabr texniki əməliyyatı
  5 sentyabrın boş, sıfır xanalı sütununu silib. Bu, 29 oktyabr iştirakını silmək
  göstərişi deyil; köhnə audit və silinmiş sentyabr sütunu geri yaradılmır.
- Bir workload.WorkloadAmendment rəsmi vacant_fill əməliyyatıdır.
  Cari dəqiq müəllim/fəaliyyət/saat bölgüsü yenə ayrıca kilid altında yoxlanılır.
- 8149 müəlliminin 11 grade auditi 26 oktyabra aid 39 doldurulmuş dəyişiklik saxlayır.
  Onlar dəyişmir; 29 oktyabr üçün icazə və ya clear istisnası yaratmır.

Kod yalnız bu 13 dəqiq audit UUID-si, tam PostgreSQL row SHA256-sı və
old/new/changes JSON SHA256-sı uyğun gələndə təsnifatı qəbul edir. Aktor,
resource, action, scope və original audit flag-ləri də yoxlanılır. Bütün 13
anchor cari tam sorğuda olmalıdır; itmiş və ya dəyişmiş qeyd tətbiqi saxlayır.
Resource-prefiksə və ya tarixə görə ümumi istisna yoxdur.

Original contrary_delete_evidence və unresolved_scope_row flag-ləri export
və sübutda qalır. Sabit Source28 servisi ayrıca təsdiqlənmiş təsnifat proof-unu
qəbzə yazır. Yeni/naməlum/malformed audit, hədəf 29 oktyabr xanasındakı clear,
0 bal, q/b, EXCUSED və sonrakı dəyişiklik əvvəlki kimi HOLD yaradır. Digər tarixlərin
qiymətləri və formal/mənbə bağları saxlanır.

Dry baseline, apply-dən əvvəl təkrar cari yoxlama, transaction rollback,
idempotent təkrar və yalnız dəyişməz receipt-created sətirlər üçün explicit
undo eyni müqavilə ilə qalır. Bu dəyişiklik Source58 və Four əhatəsini genişləndirmir.
Tarixi arxiv cari uyğunluq iddiası deyil; deploy-dan sonra təzə native dry vacibdir.
