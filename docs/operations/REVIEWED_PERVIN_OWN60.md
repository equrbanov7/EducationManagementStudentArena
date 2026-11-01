# Pərvin334F1/F2 — müəllimin öz8573 sillabusunun bərpası

Bu əməliyyat yalnız əvvəlki rəsmi45 saat düzəlişindən **sonra** işləyir.
Mənbə14133 jurnalının birbaşa8573 göstəricisi, müəllim213, qruplar739/740 və
2026/2027 Payız dövrü sabit müqavilə ilə yoxlanır. Mənbənin219/2125 fənn kodu
yalnız həmin birbaşa əlaqədə yoxlanmış yazılış fərqidir; ümumi alias yaratmır.

Mənbədəki30 mövzu,10 bölmə və30 mühazirə+30 seminar saatı dəyişmədən gəlir.
Cari rəsmi15 mühazirə+30 seminar=45 saat saxlanır. Mənbənin60 saat olması
versiyanın qərar qeydində və əməliyyat nəticəsində açıq göstərilir; mövzular
kəsilmir,15 saat uydurulmur və rəsmi yük artırılmır.

İki boş cari hədəfdə müəllifin öz sillabusu yaradılır və `approval_source=migration`
ilə təsdiqlənmiş görünür. `approved_by=NULL` qalır: köhnə insan təsdiqi barədə
iddia yoxdur. Mövcud qaralama, təsdiqli versiya və ya paylaşılmış sillabus
tapılarsa avtomatik üzərinə yazılmır.

## Ardıcıllıq

1. Cari build üçün CI/deploy uğurlu olmalıdır; workflow serverdəki buildSHA-nı yoxlayır.
2. `reviewed-pervin-syllabi.yml` dry-run: yalnız aktiv təşkilat superadmini,
   rəsmi45 saatlıq iki jurnal/sətir/təyinat, tam köhnə kimlik bağları,
   dəqiq tələbə siyahısı və əlaqə sxemi qəbul olunur.
3. Fresh dry-run `baseline` ilə `apply=true`, `confirm=APPLY` çağırılır.
4. Təkrar dry-run `already_present`, `versions_created=0` qaytarmalıdır.
5. Müstəqil jurnal və sillabus ixracı ilə iki düzgün fənnin sillabusu və bütün
   dərs, qiymət, davamiyyət, kredit, imtahan və müəlliflik məlumatı tutuşdurulur.

Workflow sərbəst fayl/URL/əmr və ya müəllim/fənn/qrup seçimi qəbul etmir.
Sabit şifrəli release asset və hər iki SHA256 yoxlanır; mənbə jurnalda göstərilmir.

## Geri alma

Yalnız bu əməliyyatın UUID qəbzi və fresh dry-run hash-i qəbul olunur.
Yaradılmış iki versiya arxivlənir, iki dosye passiv edilir; bərpadan əvvəlki
bütün qeydlər saxlanır. Sonradan dərs, qiymət, məzmun və ya başqa istinad dəyişibsə,
geri alma da dayanır və ayrıca nəzərdən keçirmə tələb olunur.

Bu sənəd tətbiq faktı deyil. `status=applied` qəbzi və müstəqil post-yoxlama
alınmayana qədər problem blankında “həll olunub” yazılmır.
