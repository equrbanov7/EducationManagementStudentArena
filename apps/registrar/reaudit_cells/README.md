# 2026-11-09 mənbə balları və davamiyyət bərpası

İki əmr var. `build_audit_cells_plan_20261109` şəbəkə/DB sorğusu etmədən iki məxfi fayldan plan yaradır. `repair_audit_cells_20261109` planı canlı tenant daxilində yenidən yoxlayır. Defolt PostgreSQL tranzaksiyası həqiqətən READ ONLY-dir; tətbiq üçün ayrıca `--apply --expected-baseline` tələb olunur. Tətbiq və geri qaytarma eyni tranzaksiyada fail-closed audit yazır. Mənbə balı, tələbə adı və ya giriş məlumatı stdout-a çıxmır.

Plan generatoru:

```
python manage.py build_audit_cells_plan_20261109 \
  --source-file <private-source.json> --source-sha256 <source-file-sha256> \
  --current-file <authenticated-current.json> --current-sha256 <current-file-sha256> \
  --organization-id <org-id> --period-id <period-id> --source-system <ledger-source-token> \
  --out <new-private-plan.json>
```

Mənbə: `journals`, `points`, `excuse_windows`; orijinal `journals_dates_points` sütunları saxlanır. Bütün 21 oktyabr 2026 daxil rəqəmli qaliblər (0 daxil) nəzərə alınır. Qalib maksimum bal deyil: native J-V4 `update_counter`, `updated_at`, `id` ardıcıllığıdır. Əlavə `class_authorities` dəqiq offering/journal/date/start/kind, hours, teacher, lab/seminar mask, end_time (mənbədə yoxdursa null) və sübut pointer-lərini daşıya bilər. Naməlum müddət uydurulmur.

Cari ixrac `{"tables":{"registrar.LessonMark":[...], ...}}` formasındadır. `LegacyEntityMap` ilə bütün `LegacyEntityMapVersion` tarixçəsi birlikdə lazımdır. Ən böyük ardıcıl təsdiqli versiya cari əlaqədir; draft review həmin əlaqəni dəyişmir. Natamam versiya zənciri rədd edilir. Tenant xarici sətir rədd edilir. Cari aktiv periodun bütün aktiv offering ID-ləri canlı vəziyyətlə tam uyğun gəlməlidir.

```
python manage.py repair_audit_cells_20261109 --org <slug> --actor <superadmin> \
  --file <private-plan.json> --sha256 <plan-file-sha256>
# Yuxarıdakı nəticənin baseline-i ilə:
python manage.py repair_audit_cells_20261109 --org <slug> --actor <superadmin> \
  --file <private-plan.json> --sha256 <plan-file-sha256> \
  --apply --expected-baseline <dry-run-baseline>
```

Dəqiq receipt üçün `--undo <apply-receipt>` əvvəl oxuma önizləməsidir; onun yeni baseline-i ilə `--apply --expected-baseline ... --undo ...` yalnız dəyişməmiş yaradılmış obyektləri silir və bərpa edilmiş attendance sətrini əvvəlki dəyərinə qaytarır. Sonrakı müəllim dəyişikliyi, formal düzəliş və ya əlavə dərs xanası undo-nu bloklayır. Təkrar tətbiq/undo 0 yazıdır.

Mənbə rəqəmi iştirak qaydasından əvvəldir. Mövcud rəsmi rəqəmli bal və formal düzəliş qorunur. Dolu attendance sətrini dəyişmək üçün cari mark hash-i ilə yanaşı uğurlu import-run mənşəyi və toxunulmamış zaman intervalı, yaxud həmin ID-ni açıq göstərən native copy/fill receipt-i lazımdır. Müəllifin dolu olması təkbaşına sonrakı redaktə sübutu deyil; native copy receipt müəllifi saxlayan halları əhatə edir. Receipt-dən sonra dəyişmiş xana qorunur. Cari QB dəyişəndə native raw/carry/credit qaydası ilə counter yenilənir; əvvəlcədən ayrıca cache drift varsa tətbiq rədd edilir.

Owner present qaydası yalnız cari enrolled tələbənin tətbiq olunan qrup xanasına aiddir. Naməlum grade route bütün təşkilatı bloklamır; onun mümkün opening-ləri saxlanılır. Dəqiq hüceyrədə qorunan cari bal başqa boş xanaları bloklamır. Ad/FIN təxmini, əsassız alias/transfer və fənn miqyası çevrilməsi yoxdur. Bilinməyən qaydalar hold sayları ilə qalır. Mənbə k1/k2/k3/si yalnız mövcud uyğun native komponentə yazıla bilər; yeni komponent sxemi uydurulmur, final balı hesablanmır.

Testlər `test_reaudit_cells_20261109.py` içində yalnız sintetik məlumatla PostgreSQL-in real migrasiya və SQL trigger-ləri altında işləyir. İstehsal tətbiqi və tam təzə ixrac bu modulun test nəticəsi ilə əvəz olunmur.
