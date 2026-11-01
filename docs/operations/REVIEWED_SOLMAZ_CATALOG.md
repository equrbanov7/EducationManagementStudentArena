# Solmazın dəqiq mənbə ilə patok və sillabus düzəlişi

Bu paket yalnız müəllim 7722 / mənbə işçisi 22 və 2026/2027 Payızdakı dörd
335F1, 335F2, 334F1, 334F2 açılışını əhatə edir. Hazır kod canlı tətbiq
sübutu deyil. İlkin metadata 8c snapshot-dandır; bütün cari məhdudiyyətlər
əməliyyat daxilində təzədən oxunur və kilidlənir.

Rəsmi Azərbaycan dili və ədəbiyyatı yük kitabında iki Payız sətri var:
Dünya ədəbiyyatı(Qədim dövr və orta əsrlər) 30 mühazirə + 30 + 30 seminar = 90,
Dünya ədəbiyyatı(XX-XXI əsrlər) 15 mühazirə + 30 + 30 seminar = 75 müəllim saatı.
XVII-XIX əsrlər sətri Yaz üçündür. Kitabın SHA256 izi sabit pins-dədir.

Dəyişikliklər:

- Yalnız 334F2 yük sətri və mövcud dolu açılışın fənni 2075→2076.
- Həmin sətrin `lecture_plan=15` saxlanır; patokun ikinci qrupunda
  `union_count=0`, `lecture_total=0`, `total_hours=30` olur. Bu, mövcud
  335F2 seminar bölgüsünün modelinə uyğundur; qrupun 45 kontakt saatı saxlanır.
- Dəqiq artıq 15 saatlıq mühazirə bölgüsü mərkəzi `unassign` ilə,
  `sync_offerings=False` şərti altında çıxarılır. `hours=0` DB tərəfindən
  qadağandır. Tam əvvəlki bölgü payload-ı qəbzdə qalır; hər hansı inbound
  əlaqə varsa əməliyyat dayanır. Dərs, tələbə, qiymət və cədvəl silinmir.
- Müəllimin öz 8355 mənbəsindən bir yeni köçürmə-təsdiqli versiya əlavə edilir.
  Mövcud müəllim qaralama versiyasının bütün bölmələri, statusu və tarixçəsi qalır.
  Mənbənin köhnə təsdiqi iddia edilmir; cari açıq bərpa səlahiyyəti yazılır.
- 335F2 həmin öz sillabusunu paylaşım vasitəsilə görür. 334F2 isə 334F1-in
  mövcud təsdiqli 8721 mənbəli versiyasını görür. Məzmun iki dəfə köçürülmür.

8355-in köhnə başlığında fənn 187 yazılıb. İki öz müəllifli mənbə jurnalı
14214 / 14218, qruplar 812 / 813 və rəsmi Payız yükü 2078 fənnini göstərir.
15 tam həftə 30 + 30 saatdır. Yalnız bu paketdə 187→2078 mənbə aliası
nəzərdən keçirilib; ümumi fənn xəritələri və digər 187 / 2078 sillabusları dəyişmir.
14120/14122 jurnallarının birbaşa 8721 bağlantısı və334F1/334F2 Payız
konteksti ikinci fənnin 2076 olduğunu təsdiqləyir; 7679 Yaz mənbəsi istifadə edilmir.

## Cari qorunma

Mərkəzi RBAC, aktiv müəllif, mövcud `amended` rəsmi sənəd, eyni tenant,
period, dörd qrup/fənn/açılış, yeddi ilkin bölgü, bütün 165 / 180 saatlıq əhatə,
9 tam tipli immutable mənbə xəritəsi və mövcud donorun tam məzmun izi yoxlanır.
Tam əks FK və gizli M2M qrafı kilidlənir; 115 modelin, o cümlədən boş
cədvəllərin relation sxemi sabit müqavilə ilə müqayisə edilir.

Hər ilkin jurnal, 0 bal daxil bütün qiymətlər, q/b, i/e, üzrlü buraxılış,
kredit, imtahan, cədvəl, sillabus bölməsi və müəllim qaralama versiyası tam
sətir hash-ları ilə qorunur. Qəbzdə qiymət və tələbə adı gövdələri yoxdur.
Yeni insan sillabusu, paylaşım, versiya, naməlum relation və ya əvvəlki
qəbzdən sonra konkret dəyişiklik əməliyyatı dayandırır.

## İcra və geri alma

`reviewed-solmaz-catalog.yml` defolt dry-run-dır. Mənbə yalnız sabit
şifrəli release/tag/asset və plaintext/cipher SHA256 ilə qəbul edilir.
Aktor xaricində sərbəst müəllim, fənn, qrup, əmr və fayl selektoru yoxdur.
Host işə düşməzdən əvvəl canlı HEAD yoxlanır; ümumi production mutex işləyir.
Tətbiq yalnız təzə dry-run baseline və `APPLY` ilə mümkündür.

Təkrar icra sıfır yeni versiya və paylaşım qaytarır. Geri alma yalnız
ən son dəqiq qəbz və dəyişməz post-state ilə mümkündür. Yeni paylaşım çıxarılır,
yalnız yeni mənbə versiyası arxivləşdirilir; ilkin müəllif işi dəyişmir.
Artıq bölgü əvvəlki UUID, bütün sahələr və timestamps ilə bərpa edilir.
Bütün audit və köçürmə tarixçəsi saxlanır. Paket üçün cari runtime dry-run,
tək apply, təkrar 0 və müstəqil post-RAW/sillabus yoxlaması hələ tələb olunur.
