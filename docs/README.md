# EMSArena sənədləri

Sənədlər mövzu üzrə qovluqlara bölünüb. Yeni sənəd əlavə edəndə uyğun
kateqoriyaya qoy; auditlər üçün [audits/README.md](./audits/README.md)
reyestrindəki qaydaya əməl et (tarixli qovluq + FIX_REPORT tarixçəsi).

| Qovluq | Məzmun |
|---|---|
| [audits/](./audits/README.md) | Bütün audit hesabatları, tarixçə reyestri və düzəliş hesabatları |
| [architecture/](./architecture/) | Sistem arxitekturası, modellər, təşkilat sistemi, akademik dizayn, roadmap; `access-control/` və `database/` alt-sənədləri |
| [exams/](./exams/) | İmtahan mərkəzi hesabatı, supervision real-time dizaynı |
| [api/](./api/) | API sənədi və roadmap |
| [operations/](./operations/) | Deployment, staging runbook, hesab provisioning, demo istifadəçilər, lokal Postgres sandbox |
| [security/](./security/) | Secret rotasiyası, tenant-izolyasiya checklist-i, OTP auth |
| [performance/](./performance/) | Performans qeydləri, load baseline, transaction pooling planı |
| [frontend/](./frontend/) | AJAX-safe JS pattern-i, UI rəng tokenləri miqrasiyası |
| [prompts/](./prompts/) | Xarici agentlər (Codex və s.) üçün hazırlanmış task prompt-ları |
| [qa/](./qa/) | QA auditləri (E2E, skip/xfail) |

## Tez-tez axtarılanlar

- Deploy necə işləyir → [operations/deployment.md](./operations/deployment.md)
- **Prod DB rolu / .env addımları (EXAM-P0-01)** → [operations/PROD_DB_ROLE_CHECKLIST.md](./operations/PROD_DB_ROLE_CHECKLIST.md)
- RLS / tenant izolyasiyası → [security/tenant-isolation-checklist.md](./security/tenant-isolation-checklist.md), [audits/RLS_BYPASS_AUDIT.md](./audits/RLS_BYPASS_AUDIT.md)
- Son tam audit və düzəlişlər → [audits/2026-07-11-codex-tam-audit/](./audits/2026-07-11-codex-tam-audit/FIX_REPORT_2026-07-11.md)
- Final imtahan mərkəzi → [exams/FINAL_EXAM_CENTER_REPORT.md](./exams/FINAL_EXAM_CENTER_REPORT.md)
- Akademik dövr / universitet sistemi → [architecture/UNIVERSITY_SYSTEM_ROADMAP.md](./architecture/UNIVERSITY_SYSTEM_ROADMAP.md)
