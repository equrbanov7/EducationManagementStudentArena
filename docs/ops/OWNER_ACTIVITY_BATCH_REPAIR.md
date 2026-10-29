# Eyni jurnal sahibinin fəaliyyət bölgüsü — kafedra dəsti

`repair_owner_activity_batch` yalnız `owner_activity_spec.py`-dakı 22 sabit
row/task/chair/subject/period/group/teacher və mənbə SHA/sətir xəritəsini qəbul edir.
Esmira, Səbiyə və Aydının ayrıca section halları bu siyahıya daxil deyil.
Global source manifest SHA:
`7b06236d033bd909ac9c3983af884e0329ad1a046d1a45923b1149991bbb887f`.

Defolt dry-run: explicit `--rows UUID,...` və ya `--chairs UUID,...` məcburidir.
Chair seçimi yalnız həmin kafedranın allowlist-dəki sətirlərinə açılır; başqa
sətirlər əlavə olunmur. Naməlum/boş/təkrar UUID və qarışıq seçim rədd edilir.

```sh
python manage.py repair_owner_activity_batch --org qku --actor USER \
  --source-sha256 7b06236d033bd909ac9c3983af884e0329ad1a046d1a45923b1149991bbb887f \
  --chairs 99856a60-d755-497c-a475-eb5f79fb26eb
```

`selection` SHA sorted seçilmiş row UUID-lərini və global source SHA-nı bağlayır.
`baseline` həmin selection + fresh selected task/rows/assignments/history,
physical group və period metadata-sının SHA-sıdır. Apply üçün bu exact seçimin
`--expected-baseline SHA --apply` parametri tələb olunur. Başqa subset üçün
baseline işləməz. Bütün seçilmiş dəst atomikdir; blocked sətrlər atlanmır.

İlkin guard: hər sətirdə sabit tək physical group, union=1/subgroup=1, source-dəki
per-group plan=total, aktiv eyni jurnal sahibi, eyni semester total və mövcud
kafedra membership-i. Parent/child və az/ing sektor eyniliyi fərz olunmur. Fresh
snapshot və mənbə komponentlərinin reyestrə uyğunluğu yoxlanmadan prod apply yoxdur.

Canonical yol workload.public fasadındandır: əvvəl azalan assignment, sonra
save_row, sonra həmin owner üçün artan/yeni fəaliyyət assignment-i. Mövcud ID,
qeyd və saathesabı flag-i saxlanır. Müxtəlif payment flag-ləri varsa əməl bloklanır.
Aralıq sync təxirə salınır; yalnız seçilmiş rows üçün final create=False çağırılır,
created/updated offering sayı sıfır olmalıdır. Full task confirm çağırılmır.
Canonical amendment taskı AMENDED edir, distributed actor/date və başqa tarixçə qalır.

Akademik full-field count+hash (dərs/müəllif/mark/enrollment/syllabus/version/section,
share/handover/selfwork/final/component/schedule), başqa rows/offerings və mövcud
role/membership/share əhatəsi dəyişərsə bütün paket rollback olunur. Yeni müəllim,
student, jurnal, paylaşım və membership yaratmaq bu əmrin işi deyil.

Audit receipt yeni assignment ID-lərini və workload backup/baseline-ı saxlayır.
Undo eyni seçimi, `--undo owneract-…` və apply üçün fresh baseline tələb edir.
Sonrakı workload/assignment/qrup/history dəyişməsi undo-nu rədd edir. Yalnız bu
receipt-in yaratdığı assignment-lər canonical unassign ilə silinir; original
assignment ID-ləri və sonradan daxil edilmiş akademik qeydlər saxlanır. Bu auditli
kompensasiyadır: amendment/audit tarixçəsi və son redaktə actor/time izləri qalır.

ProdDataOps: `task_chair=rows:UUID,...` və ya `chairs:UUID,...`;
`batch` blank=dry-run, baselineSHA=forward apply, owneract-ID=undo preview,
owneract-ID:baselineSHA=undo apply. Backup + apply=true/confirm=APPLY saxlanır.
Stdout prefix `owner_activity:`; mode, baseline, selection, batch və numeric counts.
