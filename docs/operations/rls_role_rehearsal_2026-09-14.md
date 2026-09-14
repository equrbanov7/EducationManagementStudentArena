# NOBYPASSRLS tətbiq rolu — staging klonunda məşq (2026-09-14)

`deployment.md` §5.2 A-1 («əvvəlcə staging klonunda yoxlayın») üçün sübut.
Real serverə toxunulmayıb; hər şey lokal QA klonunda (`127.0.0.1:55433`,
`emsarena_rehearsal_a0d170000901`) və pytest sandbox-larında icra olunub.

## Mühit

| | Dəyər |
|---|---|
| Rol | `emsarena_app` — `rolsuper=f`, `rolbypassrls=f`, `rolcanlogin=t` (`provision-app-db-role.sh` ilə eyni atributlar) |
| Owner rolu | `emsarena_staging` (miqrasiyalar bu rolda; tətbiq oturumu yox) |
| RLS | 144 cədvəl `ENABLE ROW LEVEL SECURITY`, 142-si `FORCE` |
| Tətbiq | `EMS_DB_ROLE_ENFORCE=error`, `USE_REDIS=False`, klon `registrar 0078 / exams 0069 / organizations 0052` |
| Kod | `fb6749cd` (Develop) |

## Nə yoxlanıldı

1. **Rol × bölmə süpürgəsi** (`scratchpad/rls/sweep.py`, 2026-09-14 19:36):
   28 `qa.*` hesabı (rektor, prorektor, dekan, kafedra müdiri, müəllim,
   tələbə, məzun, tyutor, imtahan mərkəzi rəhbəri/işçisi, RİM, TŞ, HR,
   ikinci tenant `qa.sec.*`) × hər hesabın bütün kabinet bölmələri
   (tam səhifə `?section=` + AJAX fraqmenti `api/sections/`) + `/`, `/exams/`,
   `/exams/groups/`. Hər şey bir `atomic` blokda, sonda rollback — klona yazı yoxdur.
   - **608 sorğu: 0 istisna, 0 HTTP 500, cavab gövdəsində 0 `permission denied for` /
     `row-level security` / `insufficient privilege`.**
   - 500 × 200 · 57 × 302 (anasəhifə/`/exams/` yönləndirmə) · 28 × 404 (`/appeals/`
     marşrutu yoxdur — skriptin öz fərziyyəsi) · 23 × 403 (gözlənilən: tələbə
     `/exams/groups/`; fraqment qapısı rolun görmədiyi bölməni rədd edir, tam səhifə
     eyni halda `profile-info`-ya düşür və «icazəniz yoxdur» qeydi göstərir — ardıcıldır).
   - Ən yavaş cavab 635 ms (`qa.exam_center` statistika), ən çox sorğu 45 (dashboard).
2. **Gecə brauzer süpürgələri** (dalğa 3 `w3sweep`, dalğa 4, dalğa 8 DOCX/pano) —
   hamısı :8011 dev-klonunda, eyni `emsarena_app` NOBYPASSRLS rolu altında; kağız
   bal yazısı, sehrbaz, sual idxalı, nəzarət rejimi (WS-first status) real
   brauzerdə keçirilib (bax `docs/audits/2026-09-13-claude/NIGHT_WAVES_2026_09_14.md`).
3. **`-m postgres` dəsti** — CI `rls-txn-pool` işi (`RLS_TRANSACTION_SCOPED=True`,
   `rls_app_role` NOBYPASSRLS) `b98a87dc` və `b71810d6`-də yaşıl; final-mərkəz WS
   konsumeri (`database_sync_to_async_rls`, `a9b2a7fe`) və worker (`rls_worker_atomic`)
   yolları həmin dəstdədir.

## Nəticə

Kod tərəfində NOBYPASSRLS rola keçid üçün məlum bloker qalmayıb. Prod-da qalan
addımlar yalnız sahibindir (`PROD_DB_ROLE_CHECKLIST.md`): rolu provision et →
`.env`-ə `APP_DATABASE_USER/PASSWORD` + `MIGRATION_DATABASE_URL` (owner) →
`EMS_DB_ROLE_ENFORCE=warn` ilə bir gün → `error`.

Məşq skripti: `scratchpad/rls/sweep.py` (sessiya scratchpad-ı; repo-da deyil —
lazım olsa `manage.py shell -c` ilə yenidən icra olunur, yalnız GET + rollback).
