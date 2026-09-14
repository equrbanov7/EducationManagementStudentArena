# EMSArena sənədləri

Sənədlər mövzu üzrə qovluqlara bölünüb. Yeni sənəd əlavə edəndə uyğun
kateqoriyaya qoy; auditlər üçün [audits/README.md](./audits/README.md)
reyestrindəki qaydaya əməl et (tarixli qovluq + FIX_REPORT tarixçəsi).

| Qovluq | Məzmun |
|---|---|
| [audits/](./audits/README.md) | Bütün audit hesabatları, tarixçə reyestri və düzəliş hesabatları |
| [architecture/](./architecture/) | Sistem arxitekturası, modellər, təşkilat sistemi, akademik dizayn, roadmap; `access-control/` və `database/` alt-sənədləri |
| [exams/](./exams/) | İmtahan mərkəzi hesabatı, supervision real-time dizaynı |
| [features/](./features/) | Funksiya sənədləri (istifadəçi/əməliyyat baxışı): kağız imtahan balı, sehrbazda reyestr qrupları, sual idxalı (düstur/şəkil) |
| [api/](./api/) | API sənədi və roadmap |
| [operations/](./operations/) | Deployment, staging runbook, hesab provisioning, demo istifadəçilər, lokal Postgres sandbox |
| [security/](./security/) | Secret rotasiyası, tenant-izolyasiya checklist-i, OTP auth |
| [performance/](./performance/) | Performans qeydləri, load baseline, transaction pooling planı |
| [frontend/](./frontend/) | AJAX-safe JS pattern-i, UI rəng tokenləri miqrasiyası |
| [prompts/](./prompts/) | Xarici agentlər (Codex və s.) üçün hazırlanmış task prompt-ları |
| [qa/](./qa/) | QA auditləri (E2E, skip/xfail) |

## Tez-tez axtarılanlar

- Deploy necə işləyir → [operations/deployment.md](./operations/deployment.md)
- **2026-09-14 ilk deploy yoxlama siyahısı** → [operations/deployment.md §5.2](./operations/deployment.md#52-2026-09-14-dəyişikliklər--sahibin-ilk-deploy-u-üçün-yoxlama-siyahısı)
- Kağız (yazılı/praktiki) imtahan balının daxil edilməsi → [features/kagiz_imtahan_bali.md](./features/kagiz_imtahan_bali.md)
- İmtahan sehrbazında reyestr qrupları → [features/imtahan_sehrbazi_reyestr_qruplari.md](./features/imtahan_sehrbazi_reyestr_qruplari.md)
- Sual idxalı: düstur (LaTeX/KaTeX) və şəkil → [features/sual_idxali_dustur_sekil.md](./features/sual_idxali_dustur_sekil.md)
- 2026-09-13 audit + gecə dalğaları changelog → [audits/2026-09-13-claude/FINAL_REPORT_AZ.md](./audits/2026-09-13-claude/FINAL_REPORT_AZ.md), [NIGHT_WAVES_2026_09_14.md](./audits/2026-09-13-claude/NIGHT_WAVES_2026_09_14.md)
- **Prod DB rolu / .env addımları (EXAM-P0-01)** → [operations/PROD_DB_ROLE_CHECKLIST.md](./operations/PROD_DB_ROLE_CHECKLIST.md)
- RLS / tenant izolyasiyası → [security/tenant-isolation-checklist.md](./security/tenant-isolation-checklist.md), [audits/RLS_BYPASS_AUDIT.md](./audits/RLS_BYPASS_AUDIT.md)
- Son tam audit və düzəlişlər → [audits/2026-07-11-codex-tam-audit/](./audits/2026-07-11-codex-tam-audit/FIX_REPORT_2026-07-11.md)
- Final imtahan mərkəzi → [exams/FINAL_EXAM_CENTER_REPORT.md](./exams/FINAL_EXAM_CENTER_REPORT.md)
- Akademik dövr / universitet sistemi → [architecture/UNIVERSITY_SYSTEM_ROADMAP.md](./architecture/UNIVERSITY_SYSTEM_ROADMAP.md)
