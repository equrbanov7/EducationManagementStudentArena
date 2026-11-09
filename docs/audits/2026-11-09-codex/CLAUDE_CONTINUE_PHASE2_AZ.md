# Claude / növbəti agent üçün Mərhələ 2 davam sənədi

## Cari vəziyyət — 9 noyabr, 03:13 UTC

- PR **#278** açıqdır: `codex/reaudit-remediation-20261109`, published HEAD
  `57be1ba6c848a06ff6ffbf4709b2227b0aa901d1`. Məxfi audit tarixi yeni branch-də
  yoxdur; ilkin commit yalnız main `be25b9a5e...` parent-lidir. Köhnə
  `codex/reaudit-20261109` tarixini push etməyin.
- **Bu mərhələdə production akademik data tətbiqi hələ 0**, bizim deploy yoxdur.
  Claude-un main CI/deploy-u bitib. PR-in bütün testləri keçəndən sonra fresh
  imtahan probe, exact-head merge, main deploy, encrypted full snapshot qalır.
- CI42551368437 tək synthetic process startup race göstərdi; tests-only readiness
  handshake ilə düzəldi, real Linux6 test keçdi. CI42552659855-də həmin dəst keçdi.
- CI42552659855 tam bitdi: iki legitimate twin-subject bal marşrutu testi və
  köhnə audit scope-options testi düşüb. Digər bütün CI sahələri keçib.
  Root audit options testini yeniləyib (7/7 pass). Formal twin + receipt-li merge
  scope + latest same-target precedence düzəldi:122/122 authentic PG test keçdi.
  Yanlış/undone/stale/malformed merge proof və ancient subject-pin fallback bloklanır.
  Failing files: `apps/exams/tests/test_exam_journal_gaps_2026_10_27.py`,
  `apps/workload/tests/test_repair_twins_2026_11_05b.py`.
  Agentlər freeze edib; bütün düzəlişlər bir combined fix commit ilə yeni CI-yə gedir.
- Cari canlı əsas kod `be25b9a5efa433d6052a20c7cfe1aff38662b851`-dir.
  Source28 main native DRY42552819564 `reviewed_source28_unresolved_course_audit_requires_review`
  ilə saxlanıb. Source ce94 SHA tam yoxlanıb. Heç apply edilməyib.
- Source28 diagnostic42553116190 uğurlu:57audit,13full-row-hash anchor,
  4semantic receipt,40remaining candidate (39grade +1repeated_sections).
  Metadata həmin40-ın zərərsiz olduğunu sübut etmir; fresh fullsnapshot gövdəsi
  ilə join lazımdır.133existingcapture faylında həmin gövdələr tapılmayıb.
- Typed AuditLog export genişləndi: blank resource_type-li native merge/restore/
  companion auditləri content_type app4 vasitəsilə daxil edilir; iki natural-key
  sahə əlavədir. Tenant/Sep1/caps saxlanıb. Class-history adapter native prefix+date
  sərhədini saxlayır, fingerprint/seal dəyişmir.27PGtest keçdi. Köhnə snapshotı yeni
  schemahash kimi re-label etməyin; yeni deployed HEAD-dən fresh capture alın.
- Private güncəl status: `PRIVATE/production-progress.json`; CI logları da private.
  `PRIVATE` = `/Users/elvin/Desktop/RIM/Secret/reaudit-20261109`.
  Operator recipes: `execution-runbook/`, `syllabus-batches/OPERATOR_AZ.md`,
  `cells-offline/OPERATOR_AZ.md`, `phase2-cells/duplicate-qb-safe-paths.json`.
- Sillabus default385 dry scope, **apply≤100** explicit IDs; shared/reuse bağlı
  komponentlər bölünmədən batch edilir. Private batching helper7test keçib.
- Cells224897nonblank +870conditionalblank;261numeric0. Rawsource atmamaq.
  Full native stdout aggregate-dir; private offline per-source adapter9PGtest
  keçib,0SQL. Provisionaldır: exporter-in preSept1correction və crossperiod
  predecessor coverage boşluqları native capture qədər authority yaratmır.
- **Half-pair3 fixed74-mark əməliyyatı cells-dən ƏVVƏL**: cells pinləri dəyişə bilər.
  Struktur/authorship sonrası freshcapture ilə cells plan yenidən qurulur.
  Cells/park sonrası hər syllabus batch ayrıca freshbaseline alır.
- Historical final comparator13offline test keçib;109262source winner təsdiqlidir.
  Source sem2–13-dür; cari sem14-də im/im2 yoxdur. Actual production comparison
  hələ edilməyib. Heç bir nəticəni sadəcə maksimum olduğuna görə seçməyin.

Aşağıdakı checkpoint-lər tarixidir; son status üçün üst hissə və private JSON əsasdır.

## Son checkpoint — 9 noyabr, 02:03 UTC

- HEAD `8475dbae9`: cells writer/builder və native full snapshot transport hazırdır.
- Cells: 16/16 authentic PostgreSQL testi; real migrations, SQL triggers və pooled
  RLS saxlanıb. NonNULL müəllif native copy/fill receipt-lə sübut oluna bilir;
  receipt-dən sonrakı edit qorunur. App faylları frozen/commit olunub.
- Snapshot+transport: son 24/24 PostgreSQL/pure test keçib. Pagination keyset-dir.
  Remote capture artıq yalnız deploy edilmiş native command-ı çağırır; tool SHA
  ilə deploy SHA eyni olmalıdır. Ephemeral app-code upload yoxdur.
- Sillabus: 104 əsas test və son 32 əməliyyat/canonical/source testi keçib.
  Final read-only auditorun 11 PostgreSQL testi keçib.
- Anar 823 mark hash pin-i yenilənib; native workflow apply öncəsi backup götürür.
- Əlavə CI gate-ləri yoxlandı. 4 yeni command üçün mövcud fresh READ ONLY / offline
  exemption pattern-i sənədləşdirilib; RLS worker gate, context-map və i18n keçib.
- Claude CI+deploy `42546620951` SUCCESS. Main `be25b9a5e...`, artıq göndərmək olar.
- Bizim PR/push hələ yoxdur; production məlumatı bu mərhələdə dəyişdirilməyib.
- Agent final_grade_rules sabit 8 inactive slot üçün `park_inactive_slots` əməliyyatı
  və31 PG testi bitirib (02:08 UTC). legacy_final_selection 24 missing class authority
  generatorunun stale delete/retime tarixini runtime-da revalidate edən dar guard
  əlavə edir. offline_score_audit 6 duplicate QB nəticəsini tamamlayıb: heç bir whole
  predecessor unlink hazır deyil; historical source grades itə bilər. İndi legacy
  im/im2 və apellyasiya mənbəyini semester üzrə READ ONLY araşdırır.
- 27 iri generated JSON (57.7 MB) Git-dən çıxarılır, worktree-də yerində qalır.
  SHA və private archive yolu `evidence/large-evidence-index.json`-dadır.
- STAFF_PLAN_KEY uyğun lokal nüsxəsi məlum ciphertext-lə yoxlanıb:
  `/Users/elvin/Desktop/RIM/Secret/staff_plan_key_20261028.txt` (məzmuna print yoxdur).

### Əlavə əməliyyat checkpoint — 02:07 UTC

- `cf1cb78c6`: bütün 76 fixed schema-nı real PostgreSQL-də icra edən tam
  capture testi hər iki RLS rejimində keçdi (snapshot suite artıq13/13).
- `930de0131`: böyük row-level JSON-lar private archive-ə, 4 fresh-transaction /
  offline command exemption-i mövcud RLS gate pattern-inə əlavə edilib.
- Təkrar `manage.py check` və `makemigrations --check --dry-run` keçib.
- Canlı imtahan probe `42548875074`, 02:04 UTC: open7, last4h0,
  started15m0, finished15m0, active live6h0, question/reveal0.
- Farida native dry-run `42548887689` attempt1 source açılmazdan əvvəl
  STAFF_PLAN_KEY olmadığına görə dayandı; DB-yə çatmayıb, data dəyişməyib.
- Repo və production environment secret inventarında həmin ad yox idi.
  Mövcud ciphertext-lə yoxlanmış lokal açar production environment secret-i
  kimi təhlükəsiz stdin ilə əlavə edilib; dəyər loga çıxmayıb. Yeni açar deyil.
  Run42548887689 attempt2 nəticəsi: `farida_slot_assignment_graph_changed`.
  Mənbə açıldı, cari dərs yükü əlaqəsi pini ilə fərq var; dry-run rədd oldu.
  Hələ apply yoxdur; fresh snapshotda fərqi izah etmədən pin boşaltmayın.
- Public health üçün doğru host `https://ems.wcu.edu.az/health/`-dir;
  köhnə docs-dakı emsarena.com 522 verdi, bunu QKU app failure kimi saymayın.
  Doğru host bu lokal şəbəkədən403 qaytardı; daxili deploy health uğurludur.
  Public reachability ayrıca təsdiqlənməyib.

### Nəşr və əhatə checkpoint — 02:15 UTC

- Repo public-dır. Bütün generated JSON-lar və detallı Phase1 hesabatları
  private archive-ə çıxarılıb, local worktree nüsxələri qorunub.106fayl58.8MB;
  yalnız content-free hash inventarı Git-dədir. `evidence/*.json` ignored-dır;
  xam nəticələri `git add -f` etməyin. Native app scope JSON-ları yalnız guard
  ID/hash-ləridir, student_id/score/name/FIN yoxdur.
- Köhnə public `codex/reaudit-20261109` remote branch-i silindi. Lokal branch və
  bütün commitlər qalır. Əlavə verified0600 backup:
  `PRIVATE/reaudit-branch-before-clean.bundle` (10,870,212bytes, parent main prerequisite).
  Yeni PR üçün bütün kod bitəndə HEAD tree-dən yalnız currentmain parent-li
  `codex/reaudit-remediation-20261109` clean commit/branch yaradılacaq. Köhnə
  audit-heavy commitlər PR/main ancestry-sinə daxil edilməməlidir. Branch silmək
  GitHub-un əvvəlki commit URL/cache-lərinin fiziki purge olunduğu demək deyil.
- `4867a7aca`: syllabus default385 qorunur, explicit reviewed whitelist1700;
  shared closure və foreign/newperiod qoruyucuları34PGtestlə təsdiqlənib.
- `b6662c40e`: remediation workflow `duplicate_qb` read-only əməliyyatını da
  dəstəkləyir. Final+duplicate hər ikisi input mutation flag-lərini rədd edir,
  deployed SHA əvvəl/sonra yoxlanır. Transport17test, Anar/Farida ilə64test öncəpass.
- Final legacy source136172im/im2 sətirdir, hamısı sem2–13; sem14də0. Ona görə
  yalnız cari period snapshotı final audit üçün yetərli deyil. Offlineagent
  historical finals/receipts və enrollment/offering closure-u əlavə edir,
  əvvəlki row/byte cap-ləri artırmır. Raw source yalnız private legacy-final-source.
- Legacyagent missinglesson class_history runtime fingerprintini tamamlayır;
  yeni formal delete/retime/reversal planı dayandırmalıdır.
- Doğru public `/ping/` 200 qaytardı; `/health/` external403, daxili deploy healthy.
- Son kod commitlərindən sonra mainə hələ heçnə göndərilməyib; academicdatawrites0.

### Son texniki checkpoint — 02:25 UTC

- `d1e816b82`: historical final/paper capture hazır (78 model); 16 PG test keçib.
  Bütün dövrlərin FinalGrade/Resit/ExamScoreEntry/Sheet/LegacyGradeFact/Review/
  Artifact metadata və offering/enrollment/period closure-u var; binary yoxdur.
  Current Lesson/Mark scope dəyişmir. AcademicPeriod canonical maps da əlavə edilib.
- `f272be89e`: missing class source authority current correction/delete/retime/
  reversal fingerprint-i ilə native dry/apply-da revalidate olunur.24PG+9offline
  test keçib; 4 audit prefix+Sept1 tarix sərhədi fullsnapshot ilə eynidir.
- `039fed8e2`: full cells source224897nonblank row-dur. Unmapped pretty95.3MB,
  compact82.7MB; row atmaq olmaz. v2 bundle plan gzip+base64 edir; plainSHA qalır.
  Outer cap128MiB/cipher16MiB dəyişməyib, native cells plan256MiB, syllabi20MB,
  structure1MiB. Private APPUID writer256MiB native plan limitinə uyğundur.
  v1 unpack geriyə uyğundur. Builder compact JSON yazır, current input512MiB
  producer limitini qəbul edir; executableplan256MiB ilə məhduddur.
- Son root combined suite46/46 keçdi: package6 + snapshot16 + cells/history24.
- final_grade_rules timeout/cancellation runner-i bitirir: hostdocker timeoutun
  orphan remote apply saxlamasını dayandırmalı, run-specific PID/proc identity,
  deadline, TERM/KILL və verified cleanup. Linux real process testləri tələb edilib.
  Eyni agent safe_summary apply/undo istiqaməti və receiptguardı əlavə edir.
  Onun faylları freeze olmadan commit/PR etməyin.
- offline_score_audit private historical final comparison helper hazırlayır;
  name/FIN fallback yoxdur, typed semester/student/subject/enrollment lineage.
- Son appwriter production apply0. PR/ourCI hələ yoxdur. Yeni clean branch adı
  yuxarıdadır; agent freeze-dən sonra all checks + cleanparentmain commit → push.

## Səlahiyyət və nəticə

Sahib hesabatdan sonra düzəlişləri, production tətbiqini və deploy-u açıq tapşırıb.
Son mesaj: yatmağa gedir, əlavə təsdiq gözləməyin; bütün işləri tamamlayın,
tətbiqdən sonra yoxlayın və yekun hesabat yazın. Limit yaxınlaşanda bu sənəd
Claude-un davam edə bilməsi üçündür. Bu, auditin bitdiyi və ya production-un
düzəldildiyi iddiası deyil.

**Hazırda canlı akademik məlumatlar dəyişdirilməyib. Bizim deploy yoxdur.**
Claude CI/CD artıq tamamlanıb (02:01 UTC-də success yoxlanıb).
Main CI `42546620951`, head `be25b9a5efa433d6052a20c7cfe1aff38662b851` (#183).
Main #277 əvvəlki deploy-u `42544041073` uğurla bitib. Vəziyyəti yenidən oxuyun.

## İş yeri

- Branch: `codex/reaudit-20261109`.
- Worktree: `/Users/elvin/.codex/worktrees/reaudit-20261109/EMSArena`.
- Venv: `/Users/elvin/Developer/EMSArena/venv/bin/python`.
- Claude-un `/Users/elvin/Developer/EMSArena` tətbiq fayllarına toxunulmayıb.
- Audit checkpoint: `4357d8ec0`; main #277 merge `b1fd9db33`.
- Read-only snapshot `19661a422`, limit/decode `15ff9ef5e`.
- QB/saat/cədvəl command `d7f537c34`.
- PR204 final/apellyasiya inteqrasiyası `dd69cc87e`.
- Sillabus scope, slot/komponent qoruması, şifrəli əməliyyat workflow-u `781c703de`.
- Main #183 yerli merge `6f99d2419`; bütün 5 dilin hər iki tərəfin mesajları qorunub.
- **Git status-u oxuyun: agentlərin hələ commit edilməmiş işi ola bilər. Reset/stash etməyin.**

## Sahibin vacib qaydaları

1. Legacy məlumatın sərhədi **21 oktyabr 2026 daxil**dir. Bütün mənbə balları,
   sıfır daxil, dəqiq student/fənn/qrup/dərs əlaqəsi ilə bərpa edilməlidir.
2. Sonrakı rəsmi bal, müəllim düzəlişi və qəbul edilmiş apellyasiya qorunur.
   Sadəcə ən böyük rəqəm son rəsmi nəticə deyil.
3. Mənbə balı uzlaşdırıldıqdan sonra tələbəyə aid həqiqətən boş xana sahibin
   qərarı kimi `owner_assigned_present` olur. Şübhəli QB yaratmayın.
4. Artıq/səhv QB-ni mənbə, altqrup, credit/carry/correction əsasında aradan qaldırın.
   Ümumi sıfırlama etməyin. Mənbəli QB konflikti üçün dəqiq source və current audit lazımdır.
5. Bütün cari qaralama sillabuslar məzmun/fənn/dil/saat uyğunluğu ilə tamamlanıb
   real operator təsdiqi almalıdır; müəllim jurnal yaza bilməlidir.
6. Dəqiq mənası bilinməyən fənn/şəxs əlaqəsi və qiymət uydurulmur.
7. Hər tətbiq: təzə dry-run baseline, backup, receipt; təkrar run sıfır dəyişiklik;
   post-state yoxlaması; undo yalnız öz receipt-i və dəyişməmiş data ilə.

## Məxfi material

Yalnız lokal qovluq: `/Users/elvin/Desktop/RIM/Secret/reaudit-20261109/` (0700).
Raw/şəxsi ballar/credential/private key repoya və loga çıxmır. `.json` payload-lar0600.

- `agent-db.json`: yalnız izolyasiya olunmuş local test PG (127.0.0.1:55432) bağlantısı.
  Parolu çap etməyin. Prod klonu DEYİL. Köhnə primary/staging aktual deyil.
- `phase2-model-schema.json`: lokal model sahələri, tətbiq source schema.
- `metadata.json`: əvvəlki prod metadata, 00:18 UTC, actor_id8444;
  username `data.teachers` içində həmin id-dən götürülür, loga çıxmır.
- `journal-pack-*`: əvvəlki full individual capture-lar; son complete payload per offering.
- `phase2-cells/legacy-source.json`:1590journal/226517point;
  SHA `d1026a6f7e645d6596a3a584c8205ec81088595b9a0fee2b0be0d74ae736a840`.
- `phase2-conflict-authority.json`:25 priority mark ID/timestamp/authorship metadata.
- Decryption key əvvəlki əməliyyatlarda istifadə edilmiş
  `/Users/elvin/EMSArena-backups/prod-export-key/private.pem`dir. Məzmuna heç vaxt print yoxdur.
- Legacy MariaDB `ems-legacy-delta-src:50330`; yalnız read-only helper
  `evidence/read_sources.py` istifadə edilir; credential dockerinspect-dən yaddaşa alınır.

## Hazır / aktiv kod

- `apps/registrar/reaudit_journal_structure*`:3 fixedhalf-pair,≤25inactivecache,
  ≤25offering additive timetable; masksız subgroup dərsi bütün qrupa çevrilmir.
  Baseline native proposal fingerprint-i də bağlayır.18latest+30nativePGtest keçib.
- PR204G02–G08:40Pythonfile three-way, main70bal vəselect_related saxlanıb;
  R06wrongsubject guard da var.300 fərqli PGtest keçib. Texniki sübut
  `evidence/pr204_grade_integration.json`-dadır.
- PR204G01:syllabus service/readiness scope guard-ları və2template+9i18nentry/language.
  Root90suite-də89pass, readinessperiod boşluğu tapılıb düzəldi; son20G01+
  17subgroupmerge=37test keçdi. Digər69testə təsir edən dəyişiklik olmayıb.
- F15: eyni adlı komponentkind/max/date fərqlidirsə familyrollback;
  target-dəbirslotolması sourcecədvəliartıqsildirmir; fulltime/room/week/teacher
  identity qorunur.3yeni regresiya keçib.
- `reaudit_syllabi`: realoperator publication, content/dil/saattypedproof,
  scopedcarryhook suppression,receipt/undo.104PGtest (18new) yeni#183 üzərindəpass.
  Source generator və canonical adapter də commit olunub.
- `reaudit_cells`:sourcegradesfirst,0,ownerpresent,masks,importrestoration,
  no later correction overwrite,receipt/undo,read-onlydryrun.16test authentic
  migrations və pooled RLS ilə keçib; kod 8475dbae9-da commit edilib.
- Finalread-onlyaudit: hazır və commit olunub: `apps/exams/services/reaudit_final_results.py`,
  `apps/registrar/reaudit_final_projection.py` və
  `audit_reaudit_final_results_20261109 --actor` hazırlayıb; 11 PG test keçib.
- `scripts/ops/reaudit_remediation.py` / `.github/workflows/reaudit-remediation.yml`:
  cells/syllabi/structure şifrəli bundle, finals read-only; nativehead pin,
  freshbaseline,applyconfirmation,backup,temizləmə.13 transport testi keçib.

## Kritik açıq məqamlar

- **Canonical ledger:** immutable LegacyEntityMap target-i köhnə qala bilər.
  Latestapplied LegacyEntityMapVersion canonicaldır; native latest_version()
  initialversion yaza bilər, dry-run-da çağırılmır. Agentlər pure read adapterini
  əlavə edir. Snapshot base+version ikitərəfliclosure artıq rootqueries.py-dədir:
  base və ya version cari targetə bağlanırsa base + BÜTÜN versions çıxır,
  latestquarantined/blank target ixracdan düşmür.
- **entered_by NULL yetərli deyil:**18priorityQBconflict15authored/3NULL;
  7prioritysourcegradegap HAMISI authored. Bunlar importla daşınmış müəllif ola
  bilər. Sourceauthority timestamp/importledger/currentAuditLog ilə yoxlanır,
  nonNULL özü sonradan müəllim dəyişməsi sübutu deyil.5gradegap created!=updated;
  sonradan rəsmi correction qorunmalıdır. Offlineagent bu düzəlişi edir.
- AnarF16:28lessonhash hələoriginaliləeynidir; marks817→823, HAMISIentered_byNULL.
  Təzə823mark hash `4870edd5f87d98febf7d6637c54f4a90a78dc08f38341ef0373f08c20404e5da`.
  Originallessonhash `b1944bf627762d6424402beb19bae6ee8e3b63f61e24a420cd671d1fb0dd0f8b`.
  Pin f35c89318-də yenilənib; fresh full capture / gates ilə yenidən doğrulayıb
  native reviewed-anar-authorship istifadə etmək olar. Mövcudmarklarısilmir.
- F12(95loadgap),F13family, F14(2inactive8slots),F06source28, F10/11identity,
  6duplicateQB namizədi hələfreshsnapshotdan sonra konkretləşməlidir.
  REPORT_AZ.md F01–F19tamreyestrdir; hazırcommand bütünfindinglərinhəllideməkdeyil.

## Production davam ardıcıllığı

1. Agentlərin qalan kodunu/testlərini tamamla; `git status`, dəyişiklikreview,
   Black/isort/flake8,3gates,managecheck/makemigrationscheck. JSONPIIscan.
2. Hazırki Claude CI/CDtamamlanmasını GET ilə təsdiqlə. Sahib yeni göndərişi buna
   bağlayıb. Yeni main varsa lokalmerge, dəyişmişsahətest. Sonra birPR/CI göndər.
3. Canlıimtahanprobe native `prod-exam-ops.yml script=exam_activity_probe`.
   Sonrun42546791061:01:40UTC, open_total7, last4h0,last15m0,live6h0; bu köhnəlir.
4. YaşılCI sonraauthorizedmerge/deploy; eynihead buildinfo+health doğrula.
5. **Təzə tam snapshot hələ alınmayıb.** Scope `prod-audit.yml` inputreaudit,
   actor, deployed_head. Featurebranchrun42546385473 environmentmain-only ilə
   runnerbaşlamadan rəddolub, heçDBsorğusuolmayıb. Qoruma keçilməyib/dəyişməyib.
   Main-deployedcodeolandanmainrefdədispatch. Deploy edilmiş native command işləyir; DB READ ONLY. Tmp-də yalnız public key və şifrəli nəticədir.
6. Snapshotdownload: `reaudit-state-RUN-ATTEMPT`encryptedartifact; private0600.
   `scripts/ops/decode_reaudit_snapshot.py --folder ... --private-key ...
   --output .../phase2-current.json --tool-head SHA --deployed-head SHA`.
   Çıxış `{tables:{DjangoModelLabel:[rows]},manifest,transport}`.
7. Sourceplanbuilders: cellscommand `build_audit_cells_plan_20261109`; syllabus
   `scripts/ops/prepare_reaudit_syllabi.py` (hazırdır). No guessed routes.
8. Şifrəli releasebundle (`reaudit-operation-bundle/2`, gzip+plan gzip,opensslSTAFF_PLAN_KEY),
   fixedtag `reaudit-20261109-*`,asset `bundle.json.gz.enc`. Rawplanrepo/logayox.
   Workflowdefaultdryrun; reviewcounts/holds; applybaseline+confirmAPPLY.
9. Dataorder: identity/fənn→jurnalstruktur→mənbəbalları/komponentlər→qalanboşi/ə
   →sillabusapproval→final. Sillabuscode ready olsa teacherunblock ayrıcaearlysafe.
10. Hərapplyreceiptvəzero-repeat saxla; yeni snapshot+finalaudit ilə before/after
    bütünIDs üzrə yoxla; qalanproblem varsa dəqiq səbəbvənextactionlist.
11. SonkodfixgərəkərsətestCIdeploy, sonrahealth+read-onlyaudit. Reportnəticə:
    kodhazır / prodapplied / verified / unresolved statusları ayrıdır.

Bu sənədi hər real mərhələ dəyişəndə yeniləyin; köhnə “tamamlandı” iddiasına
əsaslanıb canlıdata apply etməyin. Sahibdən yenidən ümumiicazə istəmək lazım deyil.
