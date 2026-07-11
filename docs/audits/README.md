# Audit reyestri

Bütün audit nəticələri burada saxlanır. Qayda: hər yeni audit **tarixli qovluqda**
(`YYYY-MM-DD-<mənbə>-<mövzu>/`) yerləşir; audit üzrə düzəlişlər ediləndə həmin
qovluğa `FIX_REPORT_YYYY-MM-DD.md` əlavə olunur — beləcə hər auditin tam
tarixçəsi (tapıntı → yoxlama → düzəliş → sübut) bir yerdə qalır.

## Tarixçə

| Tarix | Audit | Mənbə | Əhatə | Yekun | Düzəliş statusu |
|---|---|---|---|---|---|
| 2026-07-11 | [Codex tam repozitoriya auditi](./2026-07-11-codex-tam-audit/EMSArena_End_to_End_Audit_AZ_2026-07-11.md) | Codex | İmtahan sistemi (prioritet) + bütün layihə | İmtahan 43/100, layihə 58/100 — **NO-GO** | [FIX_REPORT 2026-07-11](./2026-07-11-codex-tam-audit/FIX_REPORT_2026-07-11.md): 5 P0 + 2 P1 + proxy P0 bağlandı |
| 2026-07-04 | [FAZA 4 / Task 1 — request-external DB path auditi](./FAZA4_TASK1_AUDIT.md) | Daxili | Celery/worker DB giriş nöqtələri | 25 entry-point sarınıb | Bağlı — CI gate-i (`_lint.yml`) qoruyur |
| 2026-07-02 | [Skip/xfail auditi](../qa/SKIP_XFAIL_AUDIT_2026-07-02.md) | Daxili | Test suite skip/xfail inventarı | — | Bağlı |
| 2026-05-24 | [RLS bypass auditi (FAZA 10)](./RLS_BYPASS_AUDIT.md) | Daxili | `bypass_rls` istifadə yerləri | — | Bağlı |
| 2026-03-27 | [E2E QA auditi](../qa/2026-03-27-e2e-qa-audit.md) | Daxili | E2E axınlar | — | Bağlı |

## 2026-07-11 Codex auditinin faylları

| Fayl | Məzmun |
|---|---|
| [EMSArena_End_to_End_Audit_AZ_2026-07-11.md](./2026-07-11-codex-tam-audit/EMSArena_End_to_End_Audit_AZ_2026-07-11.md) | Əsas hesabat: icraçı xülasə, tapıntılar, ballar, yol xəritəsi |
| [EMSArena_Exam_Audit_Matrices_AZ_2026-07-11.md](./2026-07-11-codex-tam-audit/EMSArena_Exam_Audit_Matrices_AZ_2026-07-11.md) | Lifecycle, state machine, rol-icazə, endpoint matrisləri |
| [EMSArena_Exam_System_File_Inventory_AZ_2026-07-11.md](./2026-07-11-codex-tam-audit/EMSArena_Exam_System_File_Inventory_AZ_2026-07-11.md) | 1,019 faylın kateqoriyalı inventarı |
| [EMSArena_Exam_All_Python_Symbols_AZ_2026-07-11.md](./2026-07-11-codex-tam-audit/EMSArena_Exam_All_Python_Symbols_AZ_2026-07-11.md) | Bütün Python class/function simvolları |
| [EMSArena_Exam_Database_Table_Inventory_AZ_2026-07-11.md](./2026-07-11-codex-tam-audit/EMSArena_Exam_Database_Table_Inventory_AZ_2026-07-11.md) | Exam DB cədvəl/field inventarı |
| [FIX_REPORT_2026-07-11.md](./2026-07-11-codex-tam-audit/FIX_REPORT_2026-07-11.md) | Tapıntıların yoxlanması və edilən düzəlişlər (sübutlarla) |
| [REAUDIT_PROMPT.md](./2026-07-11-codex-tam-audit/REAUDIT_PROMPT.md) | Codex-in yenidən-audit tapşırığı: düzəlişlərin verifikasiyası + performans ölçmə |
| [INFRA_HANDOFF.md](./2026-07-11-codex-tam-audit/INFRA_HANDOFF.md) | Kod ilə həll olunmayan qalan işlər (server/infra/yük/məhsul-dizayn) |
| `screenshots/exam/` | Audit zamanı çəkilmiş UI screenshot-ları |
