# 2026-09-06 legacy miqrasiyası audit sübut paketi

Bu qovluq PII-siz iki tam disposable PostgreSQL repetisiyasının paylaşılabilən
maşın və insan tərəfindən oxunan sübutlarını saxlayır.

| Fayl | Məna |
|---|---|
| `LEGACY_REHEARSAL_RUN1.json` | birinci tam run-ın deterministik hesabatı |
| `LEGACY_REHEARSAL_RUN2.json` | ikinci tam run-ın deterministik hesabatı |
| `RUN1_SUMMARY.jsonl` / `RUN2_SUMMARY.jsonl` | CLI-nin PII-siz yekun sətri |
| `RECONCILE_RUN1.md` / `RECONCILE_RUN2.md` | iki DB üçün müstəqil deep reconciliation |
| `RECONCILE_STABLE_NORMALIZED.md` | run vaxtı/DB/timing çıxarılandan sonra hər iki deep report-da byte-identik hissə |
| `SHA256SUMS.txt` | paket fayllarının checksum manifesti |

## Müstəqil yoxlama

```bash
sha256sum -c SHA256SUMS.txt
jq -cS '.deterministic' LEGACY_REHEARSAL_RUN1.json > /tmp/run1.json
jq -cS '.deterministic' LEGACY_REHEARSAL_RUN2.json > /tmp/run2.json
cmp /tmp/run1.json /tmp/run2.json
```

Deep report-ların tam fayl hash-ləri fərqlidir, çünki run ID, DB adı, vaxt və
sorğu müddətləri fərqlidir. Həmin provenance/timing hissələri çıxarıldıqdan
sonra sabit məzmunun SHA-256-sı hər iki run üçün eynidir:

`15e66b46e43062500abe22ef985479d59833c61e8c8e0b24a12d020d3141c1e2`

Source dump və production credential-ları bu paketə daxil deyil. Şübhəli
balların şəxsi siyahısı da PII səbəbindən ayrıca məhdud saxlanmalıdır.

