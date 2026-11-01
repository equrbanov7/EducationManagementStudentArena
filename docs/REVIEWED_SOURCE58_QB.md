# Sabit Source58 q/b bərpası

Bu kodun hazır olması canlı tətbiqə uyğunluğun təsdiqi deyil. Təzə cari sübut
olmadan təhlükəsiz tətbiq sayı məlum deyil. Mənbə öz-özlüyündə yazı səlahiyyəti vermir.

Sabit mənbə SHA256: `203b48f81ef7a7a85db67e5c375667700ee5f2e9051987474a4c0f91a31e4fa0`.
Əhatə: 58 q/b, 9 keçmiş dərs, 6 açılış, 44 qeydiyyat. Generic197, Source28 və
dörd QB allowlist-ləri dəyişmir. Yeni yolun seçilə bilən tenant/target/fənn parametri yoxdur.

## Məcburi cari yoxlamalar

- Sabit actor/tenant, aktiv müəllim və tələbə profilləri, cari dəqiq qeydiyyat/qrup,
  dövr və kilidlər, fəaliyyət üzrə müsbət rəsmi yük təyinatı. Buraxılmış yük siyasəti
  mövcud `plan_reached_chair` funksiyasından gəlir.
- Tam məhdud reverse graph, hər iki istiqamətdə supersession və credit/reversal
  closure, typed mənbə xəritələri, hər status/vaxt/fəaliyyət üzrə cari iddialar.
- Formal üzrlü buraxılış/düzəliş/silinmə və mövcud mənbə iddiaları. Təsirsizliyi
  dəqiq lokatorla sübut olunmayan sənəd və maskalanmış/yerləşməyən tarixçə saxlayır.
  Naməlum yazı/counter override, clear və delete hadisəsi atılmır.
- Tətbiq kilidləri altında təkrar cari yoxlama və gözlənilən baseline. Standart
  export-un READ ONLY tələbi dəyişmir; ayrıca runtime public fasad yalnız SELECT
  sübutunu səlahiyyətli outer transaction daxilində toplayır.

Yalnız yeni sətirlər INSERT edilir. Mövcud 0 bal, i/e, q/b, üzrlü qeyd və müəllif
dəyişmir. Bütün köhnə xanaların tam DB SHA256 izi və credit/sillabus/yük/profil
qoruması müqayisə olunur. Əkslik varsa bütün transaction geri qaytarılır.

Sayğac mərkəzi registrar funksiyası ilə hesablanır. Keş fərqi təkbaşına maneə deyil:
mənbənin effektiv təsiri və əvvəlki keş uyğunsuzluğu ayrıca göstərilir. Credit
çıxılması və birbaşa əvvəlki qeydiyyatın carry qaydası qorunur; +116 raw saat
avtomatik +116 effektiv saat sayılmır.

## Host və şifrəli mənbə

`reviewed-source58-qb.yml` defolt dry-run, production environment və mövcud
`production-deploy` mutex-i istifadə edir. Host əvvəl deployed HEAD-i yoxlayır.
Yalnız `reviewed-source58-qb-20261101` release-inin
`source58-reviewed-content.json.enc` asset-i qəbul olunur. Cipher SHA256:
`7924aee0cef0dca924488f30a5e874de41c2a692b10db9391526e910c6233b7d`.
OpenSSL deşifrəsindən sonra plaintext SHA yenə yoxlanır. Mənbənin0600 faylı Docker
stdin ilə APPUID sahiblik/0600/sha readback sübutu ilə ötürülür; `docker cp` işlənmir.
Release-in mövcudluğu və fresh eligible say ayrıca əməliyyat sübutu tələb edir.

Tətbiq üçün `apply=true`, `confirm=APPLY`, təzə dry baseline tələb olunur.
CLI yalnız sabit summary/count/hash verir. Mənbə mövzuları, adlar, qiymət gövdəsi
və səbəb mətnləri log-a çıxmır. Hostun ixtiyari komanda/tag/source/target girişi yoxdur.

## Təkrar və geri alma

İlkin qəbz source SHA, dəqiq sourcepoint/lesson/mark/enrollment bağları,
tam qoruma izləri və canonical əvvəl/sonra sayğaclarını saxlayır. Təkrar yeni
sətir yaratmır. Öz qəbzi yalnız bağlı JSON sxemi və eyni mənbə/bağlar/dəyişməz
məzmun sübutu ilə tanınır; resource adı təkbaşına istisna deyil.

Undo ilkin tətbiqin qaytardığı tam `receipt_sha256`, dəqiq batch və təzə undo
baseline tələb edir. Sonrakı credit/reversal, qiymət, müəlliflik, formal düzəliş,
yük və qorunan graph dəyişməsi bloklayır. Yalnız receipt-created dəyişməz sətirlər,
yeni reverse istinad yoxdursa silinir. Canonical-before yenidən hesablanır;
əvvəlki köhnəlmiş keş dəyəri geri yazılmır. Bu reconciliation müqaviləsi qəbzdə açıqdır.
