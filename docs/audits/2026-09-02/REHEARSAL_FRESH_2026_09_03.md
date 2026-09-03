# Təzə tam repetisiya — 2026-09-03 (düzəldilmiş köçürmə kodu ilə)

Məqsəd: 2026-09-02 auditinin P0/P1 düzəlişləri (arxiv qaydası, yer-tutucu
e-poçtlar, J12 `journal_lesson_recovery`, `legacy_rooms`) daxil olmaqla **tam
24 fazalı** legacy→EMSArena köçürməsini **təzə birdəfəlik** hədəfə icra etmək və
nəticəni QA klonu ilə müqayisə etmək.

## Hədəf və identifikatorlar

| | |
|---|---|
| Hədəf baza | `emsarena_rehearsal_d44526b97cbc` (127.0.0.1:**55433**, konteyner `emsarena-staging-pg`) |
| Owner DSN | `postgres://emsarena_staging:emsarena_staging_password@127.0.0.1:55433/emsarena_rehearsal_d44526b97cbc` |
| App DSN (run bununla işləyir) | `postgres://emsarena_app:emsarena_staging_app_password@127.0.0.1:55433/emsarena_rehearsal_d44526b97cbc` |
| Superadmin | `staging_admin` — parol **repoya yazılmır**, yalnız `scratchpad/rehearsal_fresh.env` (chmod 600) |
| Org | slug `myedu-univ`, `org_type=university`, owner `staging_admin`, id `b3499430-e3f1-4acb-a651-a6aad986d26e`, 18 default rol siqnalla yaradıldı |
| Run id | `8a476c8c-2a1e-4d72-9aee-f5d68b336e8c` |
| `transform_version` | `rehearsal-identity-v2.aca98087fe65` (v1 ailəsindən fərqlidir — düzəldilmiş qaydalar) |
| `policy_digest` | `aca98087fe65f8410032f2ee901c31ff234f245f9ea8f57aa58e62cbe401356e` |
| Kod | izolyasiya worktree `../rehearsal-fresh`, detached `f3fada3c` (`.env` və `.venv` symlink) |
| Mənbə | MariaDB `emsarena-legacy-source-rehearsal` @ 127.0.0.1:**50200**, `@@GLOBAL.read_only=1` təsdiqləndi; snapshot faylı `~/Downloads/myedudb.sql` (2 142 912 818 bayt, SHA `177ef226…68fe0`) |
| Log | `<scratchpad>/logs/rehearsal_fresh.log` · pidfile `…/logs/rehearsal_fresh.pid` · PID **14503** (ppid 1, `caffeinate -dimsu` altında) |
| Hesabat qovluğu | `docs/migration/reports/fresh-2026-09-03/` |
| Başlanğıc | 2026-09-03 00:22:21 UTC · gözlənilən müddət ~2.5 saat |

## Faza registrisi (24 faza, `--phase` verilmədi = hamısı)

10 academic_structure · 12 academic_catalog · **13 legacy_rooms** · 20 identity_cohort ·
25 student_placement · 26 worker_materialisation · 28 sar_materialisation ·
30 syllabus_migration · 32 journal_periods · 34 journal_offerings ·
36 journal_enrollments · 38 journal_lessons · 39 journal_lesson_meta ·
40 journal_marks · **41 journal_lesson_recovery (J12)** · 42 journal_components ·
43 journal_entry_scores · 44 journal_finals · 45 journal_selfwork · 46 journal_lock ·
47 legacy_grade_facts · 48 journal_reconcile · 49 legacy_grade_artifacts ·
50 journal_excuse_documents

## Dəqiq əmr

Skript: `<scratchpad>/run_rehearsal_fresh.sh` (env dəyişənləri daxil).
Detach: `<scratchpad>/daemonize.py <log> <pidfile> /usr/bin/caffeinate -dimsu <skript> apply`.

```bash
python manage.py legacy_import_rehearse \
  --mode apply --apply-confirm emsarena_rehearsal_d44526b97cbc --rehearsal-ordinal 1 \
  --report-dir <repo>/docs/migration/reports/fresh-2026-09-03 \
  --organization-slug myedu-univ --actor-username staging_admin \
  --source /Users/elvin/Downloads/myedudb.sql --expected-size-bytes 2142912818 \
  --batch-rows 1000 --source-chunk-size 1000 \
  --username-policy legacy_key --student-identifier-policy legacy_pk \
  --email-trust-policy deny_all --stage-contact-pending --max-staged-accounts 20000 \
  --student-role-name student --worker-role-name teacher \
  --stage-and-activate --max-activated-accounts 20000 \
  --sar-curriculum-fallback synthesise --plan-semester-scheme ordinal
```

Siyasət run `fa9516a9-…` (Rehearsal #5, 2026-08-27) ilə eynidir; fərq yalnız
kodun düzəlmiş olması və registrinin 17 → 24 fazaya genişlənməsidir.

### Mühit tələləri (fail-closed qapılar)

- **App rolu məcburidir.** Owner rolu (`emsarena_staging`) SUPERUSER+BYPASSRLS
  olduğu üçün `legacy_rehearsal_target_role_privileged` verir — `DATABASE_URL`
  `emsarena_app` olmalıdır.
- `LEGACY_MARIADB_SOURCE_READ_TIMEOUT` **≤ 300** olmalıdır (`_MAX_TIMEOUT_SECONDS`),
  əks halda `legacy_mariadb_gateway_config_invalid`.
- `LEGACY_REHEARSAL_TARGET_DISPOSABLE=disposable-local-only`,
  `LEGACY_MARIADB_SOURCE_ATTEST_ENABLED=1`,
  `LEGACY_MARIADB_SOURCE_LOCAL_DISPOSABLE=local-container-only`.
- `caffeinate -dimsu` MƏCBURİDİR — yuxu `legacy_rehearsal_cancelled` kimi görünür.

## İlk dəqiqələrin müşahidəsi (00:22–00:26 UTC)

- Faza A attestasiyası keçdi: `source_attestation.status=passed`,
  `server_read_only=true`, students 7 816 / workers 729 proyeksiyası.
- `target_guard`: disposable marker ✔, loopback ✔, non-default port ✔,
  `role_is_superuser=false`, `role_bypasses_rls=false`.
- `academic_structure` (10) tamamlandı: departments 31 + speciality 83 +
  groups 766 = **880 migrated, 0 karantin, 0 skip**.
- `academic_catalog` (12) gedişdə (ECTS/plan INFO+WARNING kodları axır).
- `legacy_rehearsal_*` xətası **yoxdur** (yeganə belə sətir INFO
  `legacy_rehearsal_attestation`), `severity='error'` sətri yoxdur.

## İzləmə

```bash
tail -f <scratchpad>/logs/rehearsal_fresh.log     # boşdursa = xəta yoxdur (JSON yalnız sonda çap olunur)
ps -p 14503 -o pid,ppid,etime,command             # ppid 1 = detached

PSQL='docker exec -i emsarena-staging-pg psql -U emsarena_staging -d emsarena_rehearsal_d44526b97cbc'
$PSQL -c "select id,status,started_at,finished_at,migrated_count,skipped_count,quarantined_count,failure_code
          from legacy_import_legacymigrationrun;"
$PSQL -c "select source_table, count(*) batches, sum(migrated_count) mig, sum(quarantined_count) q,
          sum(skipped_count) s, max(created_at) last from legacy_import_legacyimportbatch
          group by 1 order by last;"           -- faza gedişi
$PSQL -c "select rule_code, severity, count(*) from legacy_import_legacymigrationissue
          group by 1,2 order by 3 desc limit 30;"
```

## Kəsilsə — davam etdirmə

Run kəsildikdə statusu `running` qalır (exit 3). Eyni skript ikinci arqumentlə:

```bash
<scratchpad>/run_rehearsal_fresh.sh apply 8a476c8c-2a1e-4d72-9aee-f5d68b336e8c
```

(`--resume-run-id` əlavə edir; siyasət/scope eyni olmalıdır, əks halda fail-closed.)
Ləğv: eyni əmrə `--cancel-run --resume-run-id <id>`.

## Bitəndən sonra: QA klonu ilə müqayisə çeklisti

`emsarena_rehearsal_a0d170000901` (köhnə, run `fa9516a9`) ↔ yeni baza:

| Ölçü | Klonda (köhnə qayda) | Yeni bazada gözlənilən |
|---|---|---|
| Tələbə mənbə sətri | 7 816 | 7 816 (dəyişməz) |
| Aktiv tələbə hesabı | 5 213 | **~7 502** (yalnız `azadedildi=1` → arxiv) |
| Arxiv/`alumni` | 2 503 deferred, o cümlədən 2 291 səhv arxiv | **~199–200** (yalnız `legacy_sar_departed_student`) |
| `legacy_sar_active_no_admission_year` (INFO) | yox | **~2 291** (sentinel `FALLBACK_ADMISSION_YEAR=1950`) |
| Yer-tutucu e-poçt `@placeholder.invalid` | 0 | **114** (100 tələbə + 14 işçi), `legacy_account_email_placeholder_synthesised` |
| Karantin (email invalid/blank/duplicate) | 86 skip + 292 quarantined | yer-tutucu qaydası ilə azalmalıdır |
| Dərs (`registrar_lesson`) | J12-siz | **+11 607** J12 bərpası (`journal_lesson_recovery`) |
| LessonMark | — | **+161 775** |
| Qayıb saatı | — | **+37 579** |
| Otaqlar (`legacy_rooms`) | 0 | **158** |
| `birth_date` / `gender` doluluğu | 0 % | dolu (2026-08-30 `legacy_demographics`) |
| Cari akademik dövr | yoxdur | **hələ də yoxdur** — `is_current` qəsdən köçürülmür (V9); `legacy_repair_current_period --period "2025/2026 Yaz"` ilə əl ilə təyin edilir |
| Determinizm | — | `deterministic.determinism_digest` hesabatda; ikinci run `--compare-report` ilə yoxlanılır |

Müqayisə üçün SQL və hesabat: yeni `docs/migration/reports/fresh-2026-09-03/`
faylı ilə `docs/migration/reports/LEGACY_REHEARSAL_FULL_V2_RUN1.json`
(`deterministic.issue_histogram`) yan-yana qoyulur.
