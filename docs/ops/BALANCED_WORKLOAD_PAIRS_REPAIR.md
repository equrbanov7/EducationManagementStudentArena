# 12 sabit mühazirə/seminar cütü

`repair_balanced_workload_pairs` yalnız `balanced_pairs_spec.py`-dakı 12
sətir/müəllim/fənn/qrup/semestr cütünü qəbul edir. Mənbə SHA-ları və rəsmi
cədvəl sətirləri kodda sabitdir. Başqa sətir və ya mənbə əlavə etmək mümkün deyil.
Manifest SHA:
`a7544b268440d7836ad45f9fe538dac765aa428eb33b5791a3d6f2285941288a`.

Bu dəst saxlanmış kartlardan hazırlanıb, yeni canlı baseline deyil. İlkin
provisional guard hər sətrə bir dəqiq reyestr qrupu, union=1/subgroup=1,
plan=total, tək müəllimdə iki fəaliyyət və eyni cəmli açıq jurnal tələb edir.
Uyğunsuz sətir avtomatik atlanmır: bütün blocked row/səbəblər göstərilir,
bütün batch dayanır. `233 KE`/`233 KE az` və parent/child ad eyniliyi, yaxud
az/ing sektor eyniliyi fərz edilmir. Təzə snapshot və modal yoxlaması olmadan
production tətbiqi edilməməlidir.

Defolt dry-run eyni canonical yazıları atomik sınayıb rollback edir:

```sh
python manage.py repair_balanced_workload_pairs --org qku --actor USER \
  --source-sha256 a7544b268440d7836ad45f9fe538dac765aa428eb33b5791a3d6f2285941288a
```

Apply əlavə olaraq fresh `--expected-baseline SHA --apply` tələb edir.
Baseline bütün əhatə olunan task/rows/assignments, workflow history və dəqiq
qrup metadata-sını əhatə edir. Auditdə hər hədəf sətrin ayrıca baseline SHA-sı var.

Canonical ardıcıllıq: əvvəl azalan assignment, sonra sətir plan/cəmləri, sonra
artan assignment. Müəllim/assignment ID-ləri və qruplar dəyişmir. Hər aralıq
sinxron təxirə salınır; yalnız yekunda dəqiq hədəf rows üçün create=False çağırılır,
created/updated sayı sıfır olmalıdır. Ümumi confirm çağırılmır. Canonical amendment
taskı AMENDED edə bilər; distributed actor/date və başqa workflow qeydləri qalır.

Hər hansı dərs/müəllif, bal/davamiyyət, enrollment, syllabus/version/section,
share/handover, selfwork/final/komponent/schedule məzmun fərqi bütün batch-i
rollback edir. Başqa row/offering və müəllim access dəyişməsi də rədd olunur.

Undo: `--undo balanced12-…`; apply üçün yenə fresh baseline tələb olunur.
Sonrakı workload/qrup/workflow dəyişibsə undo rədd edilir. Sonradan daxil edilən
qiymət/davamiyyət saxlanır: undo vaxtının akademik before/after hash-i eyni qalır.
Bu canonical kompensasiya əməlidir; append-only amendment/audit tarixçəsi silinmir.

ProdDataOps: command `repair_balanced_workload_pairs`, batch blank=dry-run,
baselineSHA=forward apply, undoID=undo preview, undoID:baselineSHA=undo apply.
Generic production backup + apply=true/confirm=APPLY qapıları saxlanır.
