# Audit 2026-09-28 — Düzəliş planı

**Mənbə:** `FINAL_REPORT_AZ.md` + `findings/*.md`. **Başlanğıc commit:** `4c312306` (Develop).
**Qərar qaydası:** sahib «tövsiyə olunan formada davam et» dedi — məhsul qərarı tələb edən bəndlərdə
hesabatdakı tövsiyə variantı seçilir (aşağıda «Qərar» sütununda göstərilib).

## İcra modeli

- Hər iş paketi (İP) ayrıca agentdir; **fayl sahibliyi üst-üstə düşmür**. Başqa İP-nin faylına ehtiyac olarsa,
  agent onu dəyişmir, hesabatda qeyd edir.
- Yeni tərcümə sətirləri yalnız `scripts/i18n_fill_<İP>_2026_09_28.py` skriptlərinə yazılır; `locale/*`-u
  orkestrator ardıcıl işlədir (paralel `.po` yazılışı sətir itirir).
- Hər İP öz sandbox bazasında (`:55432/ems_fix_<İP>`) yalnız öz testlərini işlədir; hər düzəlişə reqressiya testi.
- Real baza (`:5432`), QA klonu (`:55433`), prod server, e-poçt — **toxunulmur**.
- Orkestrator hər İP bitdikcə: qapılar (module size, context_map, module_deps, public_api, i18n, black/isort/flake8)
  → həmin İP-nin testləri → mövzu üzrə commit (push yoxdur). Sonda tam test dəsti.

## Dalğa 1 (P0 + P1 + əlaqəli P2)

| İP | Tapıntılar | Sahiblik (qısa) | Qərar |
|---|---|---|---|
| **A1 — İmtahan variant tokenləri** | EX28-01 (P0) | exams parsing, question_bank/library view-ları, bank→exam attach, randomizer, `views/student/_helpers.py`, take_exam şablonları + JS | Hər cəhd üçün qeyri-şəffaf token + yaradılışda qarışdırma |
| **A2 — Qiymətləndirmə və vaxt** | EX28-02, EXA-01, EX28-06 (siyasət), EX28-03, EX28-04, EX28-05, EX28-07, EX28-08, EX28-09 | exams manual_grading, journal_sync, attempts servis/domain, sweep, tasks, result_release, results/attempts/coding view-ları | EX28-03: cəhd qalıbsa açar gizlədilir; EX28-07: `deadline = min(start+müddət, end_datetime)`; rəsmi = ən son bitmiş final cəhdi |
| **A3 — Apellyasiya, tarixçə, buraxılış** | EXA-02, EXA-03, EXA-04, EXA-05..08, EX28-11 | apps/appeals, registrar/exam_attempt_history, exams final_center (tickets, PIN), shared/access | Apellyasiya yalnız yoxlanmış cəhdə, pəncərə `teacher_checked_at`-dan; tarixçə koordinator/dekana açıq |
| **B1 — Jurnal bütövlüyü** | DB-01, J-01, J-02, J-03, J-05, J-09, W3 | registrar grade_audit/status, finals, views (save_finals), gradebook_lessons/components, journal_actions, corrections, journal_access, cədvəl yazı yolları | W3: `pg_advisory_xact_lock(org, period)` |
| **B2 — Tələbə həyat dövrü və qruplar** | S1, S2, S3/S4, SA-09 (audit izi) | registrar movements/transfer/services(enroll), organizations group_split/group_actions/group_students, registrar/course_groups | S1: yeni `Enrollment.Status.SUSPENDED`, bərpada geri qaytarılır |
| **C — Sillabus, dərs yükü, cədvəl** | SYL-1..4, SYL-6, SYL-7, W1, W2, W4, TT-1..5 | apps/syllabus, apps/workload, apps/timetable, accounts/views/syllabus | TT-1: yalnız təşkilat miqyaslı aktyor; W1: heç göndərilməmiş tapşırıq offering yaratmır |
| **D — Təhlükəsizlik** | SA-01..07, SA-10, SF-1..3, T-01, EX28-10 + live_exam P2-ləri | accounts auth/OTP, admin_auth, view_as, network_zone, profile_actions, media_views, live_exam, gemini_client, ai_grading, logging_filters, subject_folder, assignments teacher crud | JSON OTP marşrutları silinir; superadmin üçün vahid predikat |
| **E — Sorğu anonimliyi** | SV-1, SV-2, SV-3, SV-4 | apps/surveys | Fakültə/kafedra filtrləri «daraldıcı»; ilk bağlanışda nəticə dondurulur |
| **F1 — Backup/DR və compose** | AD-01, AD-02, AD-03, DB-08, compose hissələri (DB-02 PG/PgBouncer, AD-05 arg, AD-04 env) | docker-compose*.yml, docs/operations (deployment, sandbox), scripts/ops, docker/prometheus, alertmanager | Off-site: rclone crypt/restic skripti env ilə, konfiqurasiya olunmayanda alert |

## Dalğa 2

| İP | Tapıntılar | Sahiblik |
|---|---|---|
| **F2 — Konfiqurasiya, CI, asılılıqlar, yük** | AD-04, AD-05 (deploy skripti), AD-06, AD-07, DB-02 (rol timeout-ları, nginx), DB-03 (admission control), FQ-TEST-1 | config/settings, .github, requirements, Dockerfile.prod, remote_deploy.sh, docker/nginx, docker/postgres-init, provision skripti, core middleware |
| **G — Frontend, a11y, i18n** | FQ-FE-1..4, FQ-A11Y-1, FQ-I18N-1..3 | bildiriş şablonları, labs/assignments/projects modal JS-ləri, xəta şablonları, CLAUDE.md yoxlama əmri, i18n skripti |

## Sahib üçün qalanlar (kodla həll olunmur)

1. **AD-03:** macOS firewall-u yandırmaq; köhnə prod-surət bazalarını (`ems_restore_*`, `ems_prodcopy`, …) silmək —
   dağıdıcı əməldir, ayrıca təsdiq istənəcək; agent konteynerini yeni compose ilə yenidən qaldırmaq (loopback bind).
2. **AD-01:** off-site hədəf (bucket/NAS) və şifrə açarı; skript hazır olacaq, `.env`-ə dəyərlər yazılmalıdır.
3. **SA-06:** loglar hostdan kənara getmişdirsə Gemini açarını dəyişmək.
4. **SA-04:** prod-da `profile.role='superadmin' AND NOT is_superuser` sayını yoxlamaq (yalnız-oxuma sorğusu hesabatdadır).
5. **AD-05/AD-07:** GHCR registry tokeni, `main` üçün branch protection (GitHub parametrləri).
6. **DB-02:** rol timeout-larını prod serverdə tətbiq etmək (deploy skripti idempotent edəcək — deploy lazımdır).
7. **SA-08:** yüksək rollar üçün ikinci faktor — Brevo gecikməsi (≈1 saat) səbəbindən e-poçt OTP ilə məcburi etmək
   girişi bloklaya bilər; TOTP qərarı tələb olunur. Bu dalğada edilmir.
8. Deploy (push → Staging → main) — yalnız sahibin göstərişi ilə.

## Bu planda olmayanlar (sonrakı mərhələ)

AD-08 runtime dövrləri, AD-09 `accounts` bölünməsi, DB-13 sorğu memo-su, J-06/J-08 (DB CHECK real məlumat təmizliyi
tələb edir), time_machine/race test infrastrukturu, 5 paralel BEM sistemi, staging mühiti.
