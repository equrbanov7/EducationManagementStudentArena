# Sillabus redaktoru — uçdan-uca JS qoşquları (istinad materialı)

⚠️ **Bunlar pytest tərəfindən TOPLANMIR** (`conftest.py` → `collect_ignore_glob`).
Node + jsdom tələb edirlər; CI-da node yoxdur.

## Niyə lazımdır

Repodakı adi testlər (`test_editor_carryover.py`) göndərilən JS-i **icra etmir** —
onun Python güzgüsünü (`editor_dom.py`) işlədir.  Nəticədə **məzmunu pozan, amma
seçicini saxlayan** dəyişikliklər tutulmur: `collectOut`-un `\n`-i boşluqla əvəz
etməsi (4,790 sillabusluq itki yolu) + `CONTRACT_DIGEST`-in yenilənməsi →
**29/29 test yaşıl qalır**.

Bu qoşqu həmin boşluğu bağlayır: **19 mutasiyanın 19-unu öldürüb.**

## İşlətmək

```bash
export DATABASE_URL="postgresql://…@127.0.0.1:55432/<ÖZ UNİKAL ADIN>"
python -m pytest apps/syllabus/tests/e2e/test_real_js_roundtrip.py -p no:cacheprovider
```

**Tələlər:**
- Ortaq test bazası paralel agentlər tərəfindən çirklənir — **öz unikal baza adını** işlət.
- `localhost:5432` pgbouncer-dir və yalnız `emsarena_db`-ni tanıyır;
  test bazası üçün `127.0.0.1:55432` (`emsarena-agent-postgres`).
- Django test client `ALLOWED_HOSTS`-a dəyir — `settings.ALLOWED_HOSTS = ["*"]`.

## Fayllar

| fayl | nə edir |
|---|---|
| `collect.js` · `collect_edit.js` | jsdom altında `EMSSyllabusFields.collect` |
| `regress.js` | `syllabus_editor.js` ilə qarşılıqlı təsir reqressiyası |
| `add_outcome_e2e.js` | «+ Təlim nəticəsi əlavə et» zənciri |
| `test_real_js_roundtrip.py` | mənbə → redaktor → ƏSL JS → saxla → oxu |
| `test_fifth_path.py` | `assess.project` 0→30 uydurması (bax sənəd, 2-ci maddə) |
| `test_banner.py` · `test_empty_outcomes.py` · `test_regression.py` | köməkçi |
| `sweep.py` · `contra.py` · `ml.py` · `para.py` · `zero.py` | ölçmə skriptləri |

Detallar: `docs/frontend/SILLABUS_REDAKTOR_QALAN_IS.md`
