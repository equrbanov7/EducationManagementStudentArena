# Tam QA auditi 2026-09-05 — subagent brifinqi

Bu fayl auditdə işləyən HƏR agent üçün ortaq kontekstdir. Oxumadan işə başlama.

## 1. Mühit

| Nə | Dəyər |
|---|---|
| Kanonik repo | `/Users/elvin/Developer/EMSArena` (branch `audit/full-qa-2026-09-05`, Develop-dən) |
| Python | `/Users/elvin/Developer/EMSArena/venv/bin/python` (3.11, bütün asılılıqlar + playwright) |
| Canlı QA serveri | `http://127.0.0.1:8100` — `runserver --noreload`, yəni **kod dəyişikliyi restart-sız görünmür** (restart-ı yalnız orkestrator edir) |
| Baza | QA klonu `emsarena_rehearsal_a0d170000901` (Postgres 127.0.0.1:55433, owner `emsarena_staging`/`emsarena_staging_password`, tətbiq rolu `emsarena_app` NOBYPASSRLS). **Sərbəst yaz** — klon birdəfəlikdir. |
| Qorunan baza | lokal `emsarena_db` (:5432) — **ASLA toxunma** (real köçürülmüş data) |
| Test hesabları | `scripts/qa_live/accounts.py` (29 hesab); parol `~/EMSArena-backups/TEST_HESABLARI.md`-dən oxunur (repo-dan kənar, commit ETMƏ) |
| Tələbə portalı | `/accounts/login/telebe/` · heyət portalı `/accounts/login/muellim/` |
| Kabinet | `/accounts/profile/?section=<açar>` (tam səhifə) · `/accounts/profile/api/sections/<açar>/` (AJAX JSON `{ok, html}`) |
| Nəticə qovluğu | `~/EMSArena-backups/qa-2026-09-05/` (JSON, ekran görüntüləri — reboot-a davamlı); hesabatlar `docs/audits/2026-09-05/` |

## 2. Harness

```bash
cd /Users/elvin/Developer/EMSArena
# HTTP süpürgə (brauzersiz): rol × bölmə, status/ms/evristika → JSON
venv/bin/python -m scripts.qa_live.crawl_sections --users qa.teacher --out /tmp/x.json
# Headless brauzer: real login, sidebar KLİK, konsol/şəbəkə xətası, aktiv menyu, üfüqi daşma, screenshot
venv/bin/python -m scripts.qa_live.pw_crawl --user qa.dean --out ~/EMSArena-backups/qa-2026-09-05/shots --viewports 1280x900,375x812
```

Python-dan: `from scripts.qa_live.http_session import login, timed_get, fragment, full_page, sidebar_sections`
→ `s = login("qa.teacher")`; `s.get(BASE_URL + path)`; POST üçün CSRF: `s.cookies["csrftoken"]` (header `X-CSRFToken`, `Referer` ver).
Playwright: `from playwright.sync_api import sync_playwright` — `scripts/qa_live/pw_crawl.py`-dəki `_login` nümunəsi.

Ümumi süpürgənin hazır nəticəsi: `~/EMSArena-backups/qa-2026-09-05/json/crawl_all.json` (29 hesab × bütün bölmələr).

## 3. Layihə qaydaları (pozma)

1. **Şablonlarda inline/internal CSS və JS YAZILMIR** — yalnız xarici `static/` faylı (CSP `SELF+NONCE`). Dinamik dəyər `data-*` atributu ilə. JS `window.EMSReady(fn)` / `EMSDelegate.on` ilə AJAX-safe olmalıdır (`docs/frontend/AJAX_SAFE_JS_PATTERN.md`). Bax `CLAUDE.md`.
2. **Modul ölçüsü**: yeni fayl ≤600 sətir; `scripts/module_size_budget.json`-dakı dondurulmuş faylları BÖYÜTMƏ (`python scripts/check_module_size.py --check`). Bax `AGENTS.md`.
3. **Tenant izolyasiyası > hər şey.** RLS (`core/rls.py`) + RBAC (`apps/organizations/permissions.py`). İcazə yoxlaması rol ADI ilə deyil, icazə AÇARI ilə (`get_permission_scope(user, org, "x.y")`).
4. Rənglər yalnız `--ems-*` tokenləri (`static/css/design-tokens.css`); tətbiq **yalnız açıq (light)** temadır — `prefers-color-scheme: dark` YAZMA.
5. i18n: `{% trans "key" context "ctx" %}`; `%` işarəsi trans içində sınır; msgid toqquşmasına diqqət. Yeni mətn 4 dil kataloquna əlavə olunur (`scripts/i18n_fill_*.py` nümunələri; `python scripts/check_i18n_catalogs.py`).
6. Django şablon şərhi çoxsətirli `{# #}` DEYİL, `{% comment %}`.
7. Bölmə panelinin içində qabıq başlığını (`#profileSectionTitle`) TƏKRARLAMA (ikinci `h1` yox).
8. Kod dəyişikliyi: lint `black` (line-length 120) + `isort` + `flake8`; `python manage.py makemigrations --check`; testlər `DATABASE_URL="sqlite://" venv/bin/pytest <yol> -p no:cacheprovider -q` (RLS/`-m postgres` testləri sqlite-də keçilmir).
9. Hər düzəliş üçün red→green test yaz (mövcud test faylına və ya yeni `test_*.py`).
10. Sirr/parol commit ETMƏ; `~/EMSArena-backups` yolları hesabatda qala bilər.

## 4. Tapıntı formatı (JSON, StructuredOutput ilə qaytar)

```json
{"id":"NAV-teacher-03","module":"registrar","page":"my-schedule","role":"teacher","severity":"P2",
 "title":"…","steps":["…"],"expected":"…","actual":"…","root_cause":"apps/registrar/schedule.py:120 …",
 "evidence":"~/EMSArena-backups/qa-2026-09-05/shots/qa.teacher/my-schedule@1280.png",
 "fix_proposal":"…","fixed":false,"files":["…"]}
```

Severity: **P0** sistem işləmir / data korlanır / ciddi təhlükəsizlik · **P1** əsas funksiya sınıq · **P2** funksional və ya vacib UX · **P3** cilalama.
«Qəsdən belədir» halları üçün `docs/audits/2026-09-02/ISSUES.md` (WONTFIX/DEFERRED) və `PHASE32_ROLE_MATRIX_FINAL.md`-ə bax — onları təkrar tapıntı kimi yazma.

## 5. Sahib qərarları (dəyişmə)

- Sillabus təsdiqçisi = **kafedra müdiri** (dekan yalnız oxuyur/şərh yazır).
- İmtahan mərkəzi başqa müəllimlərin sual bankını **oxuya bilər** (audit olunur) — WONTFIX.
- Tələbə/istifadəçi özü təşkilata qoşulmur; «Təşkilata qoşul» menyusu gizlidir.
- Sol sidebar həmişə görünür; hər ekran kabinet bölməsidir, panel sağda açılır.
- Tədris ili formatı `2025/2026`, semestr `Payız/Yaz/Yay`; ballar tam ədəd.
