# 233KE və233 KE az — dar bərpa

İstifadəçi bu iki adın eyni qrup olduğunu təsdiqləyib.30Oktyabr prod çıxarışında
eyni parent/əyani/bakalavr/Azərbaycan sektoru var;233KE-də akademik qeyd yoxdur,
233 KE az-da13aktiv və2xaric akademik qeyd var. İngilis sektoru,1/2alt qruplar
və başqa cohortlar bu əməliyyata daxil deyil.

`repair_233ke_group_alias` yalnız `ke233_alias_spec.py` exact UUID-lərini qəbul edir.
Pinned manifest SHA:
`c41ed24dde58360c1f9925ec50b355c14230a36add34a1480d416590c6caab56`.

Nəticə:

- Yeddi yük sətrinin saatları və assignment-ləri saxlanılır. Dördünün qrup FK-si
  canonical qrupa keçir; üç əvvəlki jurnalın fiziki FK-si saxlanılır.
- İki boş yaz jurnalının ID-si, sahibi və strukturu saxlanılaraq qrupu düzəlir.
- Dörd təkrar jurnalın tələbə/dərs/xanası yoxdur; onlar inactive olur. Aidanın
  köhnə təsdiqli sillabusu da daxil olmaqla bütün dosyelər və versiyalar qalır.
- Jalənin yazılmış dərsi və qaralama sillabusu, Optimallaşdırma üsullarının
  qiymətləndirmə sxemi və Təcrübə sətrinin identity-si dəyişmir. Mövcud DB
  reference-identity qorunması zəiflədilmir.
- İki yaz dərsinə canonical `enroll_group_students`, iki payız jurnalına canonical
  `add_guest_student` tətbiq edilir. SAR/tələbə qrupu dəyişmir; guest əlavəsində
  mənbə233 KE az açıq saxlanılır. Mövcud enrollment və qiymətlər əzilmir.
- Kompleks analiz üçün eyni müəllimin təsdiqli sillabusu yerində paylaşılır;
  yeni nüsxə yaranmır, hədəfdə artıq öz dosyesi varsa üstün saxlanılır.

Alias inactive+`settings.canonical_group` olur. Yalnız bu iki exact WCU UUID-si
üçün pointer yoxlanır. Yük redaktoru canonical ID/etiket göstərir; tarixi row-un
redaktəsi onun original FK-sini saxlayır. Sonrakı sənəd idxalı həmin tarixi
sətri canonical ID ilə də tapır. Bu, ümumi ad-bənzərliyi əsasında birləşmə deyil.
Scoped snapshot yalnız tenant daxilində valid group UUID pointerini ixrac edir.

## İcra

```sh
python manage.py repair_233ke_group_alias --org qku --actor USER \
  --source-sha256 c41ed24dde58360c1f9925ec50b355c14230a36add34a1480d416590c6caab56
```

Defolt dry-run bütün əməliyyatı atomik icra edib rollback edir. Apply üçün
`--expected-baseline SHA --apply` məcburidir. Baseline exact groups, rows,
assignments, tasks, bütün offering reverse-FK-ləri, roster və full academic
fingerprintləri bağlayır. Yeni gözlənilməz əlaqə, dəyişmiş məzmun, sektor/parent
uyğunsuzluğu və ya dolu collision bütün paketi rədd edir.

ProdDataOps: `command=repair_233ke_group_alias`, `batch=baselineSHA`,
`apply=true`, `confirm=APPLY`. Mövcud backup axını saxlanılır. Saylar, baseline
və `ke233-…` batchID xaricində heç bir xam məlumat Actions loguna çıxmır.
İlkin yeni enrollment sayı canonical üzvlük/münaqişə qapılarından sonra dry-run-da
görünür;13nəfərdən hər jurnal üçün maksimum52yeni qeyd mümkündür.

## Geri qaytarma

`--undo ke233-…` önbaxışdır; apply üçün ayrıca cari baseline lazımdır.
Yalnız receiptin yaratdığı enrollment/share ID-ləri geri götürülür. Tətbiqdən
sonra müəllim dərs və ya qiymət yazıbsa undo rədd edilir. Mövcud məzmun və
tarixçə heç vaxt overwrite edilmir. Workload amendment/audit tarixçəsi qalır.
