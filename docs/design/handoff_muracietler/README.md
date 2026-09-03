# Handoff: Müraciətlər paneli (Requests / Tickets) — EMS Arena

## 1. What this is

One screen, six roles. A university-wide request (ticket) system: a student or a teacher submits a
request, the system routes it to the responsible unit, that unit answers it, asks for more
information, forwards it to another unit, or rejects it. Everything is tracked on a timeline that
the requester can see.

Target codebase: `equrbanov7/EducationManagementStudentArena` (Django, branch `main`).
UI language is **Azerbaijani** — all copy in the design files is final copy, use it verbatim.

### Files

```
index.html                                  ← open this first: all six roles, live, side by side
design/00 Baza - Muracietler paneli.dc.html ← the source design (role switchable via Tweaks)
design/01 Rol - Telebe.dc.html              ← same screen, role locked to Tələbə
design/02 Rol - Muellim.dc.html
design/03 Rol - Telebe Merkezi.dc.html
design/04 Rol - Dekanliq.dc.html
design/05 Rol - Kafedra mudiri.dc.html
design/06 Rol - Tedris Shobesi.dc.html
design/support.js                           ← runtime for the .dc.html prototypes (do not ship)
design/brand/                               ← logo assets
```

The 01–06 files are **byte-identical to 00 except for one value** — the `role` prop default. That
is the point: the role is the only input; layout, components and CSS are shared. Build ONE view and
ONE template; branch on the user's role inside it.

### About the design files

These are **design references written in HTML**, not production code. Each `.dc.html` is a
self-contained page with a template plus a small logic class rendered by `support.js`. All demo data
is hard-coded arrays (`UNITS`, `KINDS`, `STATUS`, `TICKETS`) inside the `<script type="text/x-dc">`
block — each array is a stand-in for a queryset. Recreate the UI as Django templates using the
project's existing `static/css/design-tokens.css` / `ems_components.css` conventions. Do not ship
the prototype HTML.

**Fidelity: high.** Every colour, size, radius and string below is exact and taken from the source.
Design canvas: 1400 px wide, content `max-width: 1360px`, padding `24px 28px 40px`.

---

## 2. Roles

Six roles, two families.

| Role (`role` prop) | Family | Unit key | Can create | Sees |
|---|---|---|---|---|
| `Tələbə` | sender | — | yes | own requests (`fromRole = telebe`) |
| `Müəllim` | sender | — | yes | own requests (`fromRole = muellim`) |
| `Tələbə Mərkəzi` | handler | `telebe` | no | requests currently at the unit + requests it forwarded |
| `Dekanlıq` | handler | `dekan` | no | same |
| `Kafedra müdiri` | handler | `kafedra` | no | same |
| `Tədris Şöbəsi` | handler | `tedris` | no | same |

`Maliyyə Şöbəsi` (`maliyye`) and `İKT Şöbəsi` (`ikt`) exist as routing targets but have no role
screen in this handoff — they use the identical handler view, so add them by mapping the role.

### What changes per family

| | sender (Tələbə / Müəllim) | handler (units) |
|---|---|---|
| Context bar | `Tələbə kabineti` / `Müəllim kabineti` · `öz müraciətlərim` | unit name · `şöbəyə gələn müraciətlər` |
| "Yeni müraciət" button | shown | hidden |
| KPI cards | Açıq müraciətim · Məlumat gözlənilir · Cavablanıb · Orta cavab müddəti | Mənə gələn açıq · Yeni — baxılmayıb · Cavab müddəti keçən · İzlədiyim |
| Tabs | `Müraciətlərim` (count) · `Arxiv` | `Mənə gələnlər` (count) · `İzlədiklərim` (count) · `Arxiv` |
| List row, secondary line | current unit name | requester name · group/kafedra |
| List row, right label | `N iş günü müddət` / `bağlanıb` | `sizdədir` / `<unit>-də` |
| Detail actions | none — read-only note instead | reply box + 4 actions (only when the request is AT this unit and open) |

Everything else — filters, search, detail panel, timeline, SLA banner, empty state, toast — is
identical for all six.

### Per-role differences that are NOT just family

- **Tələbə** can create: `Transkript sorğusu`, `Arayış sorğusu`, `Qiymətə etiraz`, `Şikayət`,
  `Tələbə hərəkəti`, `Təhsil haqqı`, `Texniki problem`.
- **Müəllim** can create: `Şikayət`, `Təqdimat`, `Texniki problem`.
- A handler's forward dialog lists **all units except its own**.

---

## 3. Domain data

### 3.1 Units (`UNITS`)

| key | name | note (shown in the forward dialog) |
|---|---|---|
| `telebe` | Tələbə Xidmətləri Mərkəzi | sənəd, arayış, transkript, qeydiyyat |
| `tedris` | Tədris Şöbəsi | plan, cədvəl, fənn, semestr açılışı |
| `dekan` | Dekanlıq | tələbə hərəkəti, akademik məsələlər |
| `kafedra` | Kafedra müdirliyi | müəllim, fənn tədrisi, sillabus |
| `maliyye` | Maliyyə Şöbəsi | təhsil haqqı, ödəniş, güzəşt |
| `ikt` | İKT Şöbəsi | sistem girişi, texniki nasazlıq |

### 3.2 Request kinds (`KINDS`) — routing + SLA table

| key | label | who can send | routes to | SLA (iş günü) | badge bg / fg |
|---|---|---|---|---|---|
| `transkript` | Transkript sorğusu | tələbə | `telebe` | 3 | `#dbeafe` / `#1e40af` |
| `arayis` | Arayış sorğusu | tələbə | `telebe` | 2 | `#dbeafe` / `#1e40af` |
| `qiymet` | Qiymətə etiraz | tələbə | `dekan` | 5 | `#fef3c7` / `#92400e` |
| `sikayet` | Şikayət | tələbə, müəllim | `dekan` | 10 | `#fee2e2` / `#b91c1c` |
| `hereket` | Tələbə hərəkəti | tələbə | `dekan` | 7 | `#f1f5f9` / `#334155` |
| `odenis` | Təhsil haqqı | tələbə | `maliyye` | 5 | `#f1f5f9` / `#334155` |
| `teqdimat` | Təqdimat | müəllim | `kafedra` | 10 | `#dbeafe` / `#1e40af` |
| `texniki` | Texniki problem | tələbə, müəllim | `ikt` | 2 | `#f1f5f9` / `#334155` |

Sub-notes shown in the create dialog: `Rəsmi transkriptin verilməsi`,
`Təhsil, hərbi və ya bank arayışı`, `İmtahan nəticəsinə apellyasiya`,
`Tədris prosesi ilə bağlı şikayət`, `Köçürmə, akademik məzuniyyət, bərpa`,
`Güzəşt, hissə-hissə ödəniş, qaytarma`, `Kafedraya rəsmi təklif və ya təqdimat`,
`Sistemə giriş, jurnal, e-poçt`.

**Routing is automatic** — the sender never picks a unit; the kind decides. The create dialog shows
the resolved destination live: `Bu müraciət «<unit>»-nə gedəcək · cavab müddəti N iş günü.`

### 3.3 Statuses (`STATUS`) — pill bg / fg

| status | bg | fg | open? |
|---|---|---|---|
| `Yeni` | `#dbeafe` | `#1e40af` | open |
| `Baxılır` | `#fef3c7` | `#92400e` | open |
| `Yönləndirilib` | `#f1f5f9` | `#334155` | open |
| `Məlumat gözlənilir` | `#fef3c7` | `#92400e` | open |
| `Həll olunub` | `#dcfce7` | `#15803d` | closed |
| `Rədd edilib` | `#fee2e2` | `#b91c1c` | closed |

"Open" = not `Həll olunub` and not `Rədd edilib`. Overdue = open AND `age > kind.days`.

### 3.4 State machine

```
Yeni ──baxış──▶ Baxılır ──┬── cavab + «Həll olundu — bağla» ──▶ Həll olunub   (terminal)
                          ├── cavab + «Rədd et»               ──▶ Rədd edilib  (terminal)
                          ├── cavab + «Əlavə məlumat istə»    ──▶ Məlumat gözlənilir ──▶ Baxılır
                          └── «Başqa şöbəyə yönləndir»        ──▶ Yönləndirilib (at = new unit)
```

Every transition appends a timeline entry. Forwarding changes the **owning unit** (`at`), never
deletes the request; the forwarding unit keeps it under `İzlədiklərim`.

Timeline marks (`MARK`) — 20×20 circle, `font-size:.64rem`, weight 800:

| mark | meaning | bg / fg |
|---|---|---|
| `↑` | submitted | `#dbeafe` / `#1e40af` |
| `👁` | seen / accepted | `#f1f5f9` / `#334155` |
| `→` | forwarded | `#f1f5f9` / `#334155` |
| `?` | more info requested | `#fef3c7` / `#92400e` |
| `✓` | resolved | `#dcfce7` / `#166534` |
| `✕` | rejected | `#fee2e2` / `#b91c1c` |

---

## 4. Screen anatomy (top to bottom)

### 4.1 Context bar
`display:flex; gap:8px 12px; padding:9px 14px; margin-bottom:16px; background:#fff;
border:1px solid #e2e8f0; border-radius:12px; font-size:.79rem`
Chat-bubble icon 15 px stroke-1.9 `#2563eb` · **who** (800, `#0f172a`) · `·` (`#cbd5e1`) ·
scope (`#64748b`) · role pill pushed right: `padding:3px 10px; radius 999px; background:#eff6ff;
color:#1e40af; .74rem/700`.

### 4.2 Title row
`h1` `1.55rem/800/-.02em`, text `Müraciətlər`. Intro paragraph `.86rem/#64748b`, `max-width:700px`,
`text-wrap:pretty` — sender and handler copy differ (see source, use verbatim).
Primary button **Yeni müraciət** (senders only): `padding:10px 18px; radius 10px; bg #2563eb;
color #fff; .85rem/700`, plus-icon 14 px; hover `#1d4ed8`.

### 4.3 KPI cards
`grid; repeat(auto-fit, minmax(158px,1fr)); gap:11px`. Each card is a **button** that applies a
filter. `padding:12px 14px; radius 13px; 1px border`; hover `border-color:#2563eb`.
Label `.67rem/800/uppercase/letter-spacing:.07em`, value `1.26rem/800`, note `.72rem`.
The first card is always primary-tinted (`#eff6ff` / `#bfdbfe`). Handler cards 2 and 3 switch to a
neutral or danger palette depending on whether their count is zero:
- *Yeni — baxılmayıb*: >0 → primary tint, note `ilk baxış gözlənilir`; 0 → neutral, `hamısına baxılıb`.
- *Cavab müddəti keçən*: >0 → `#fee2e2` / `#fecaca` / `#b91c1c`, note `təcili baxılmalıdır`;
  0 → neutral, `gecikən yoxdur`.

Click targets: card 1 → `stat=Açıq`; card 3 (handler) → `stat=Gecikən`; card 4 (handler) →
`tab=İzlədiklərim`.

### 4.4 Tabs
`display:flex; gap:2px; border-bottom:1px solid #e2e8f0; overflow-x:auto`.
Item `padding:10px 14px; border-bottom:2px solid`; active `#2563eb` border + `#1e40af` text + 800,
inactive transparent border + `#64748b` + 600. Optional count pill `padding:1px 6px; radius 999px;
.7rem/800` — active `#dbeafe`/`#1e40af`, inactive `#f1f5f9`/`#64748b`. Selecting `Arxiv` also sets
`stat = Hamısı`. `aria-current` on the active tab.

### 4.5 Filter bar
White card, `padding:11px 13px; radius 13px; gap:8px; flex-wrap`.
- Search input, `flex:1; min-width:190px; height:36px; padding-left:32px; radius 10px;
  background:#f8fafc`, magnifier 14 px at `left:11px; top:11px`. Placeholder
  `Mövzu, nömrə və ya göndərən axtar`. **Debounced 260 ms.** Matches subject, request number and
  requester name. Visually-hidden `<label>`: `Müraciət axtar`.
- Status chips `Açıq olanlar` · `Müddəti keçən` · `Bağlananlar` · `Hamısı`, height 36, radius 9;
  active `#2563eb` bg + white text, inactive white + `#334155` + `#cbd5e1` border. Default `Açıq`.
- Kind dropdown (`aria-haspopup="listbox"`), label `Bütün növlər` or the chosen kind label,
  max-width 230, chevron 12 px. Panel: `width:250px; radius 11px; box-shadow 0 14px 34px
  rgba(15,23,42,.16); max-height:260px; overflow:auto`, options `padding:8px 10px; radius 8px`,
  selected `#eff6ff` bg + `#1e40af` + 800, hover `#eff6ff`. Keyboard: Enter/Space select, Esc close.
- **Sıfırla** — text button, resets to `q:'', stat:'Açıq', kind:'Hamısı'`.

### 4.6 Two-column body
`grid-template-columns: minmax(0,1fr) minmax(0,420px); gap:16px; align-items:start`.
Below ~1100 px collapse to one column and turn the detail panel into a slide-over/modal.

**List rows** are buttons, `padding:13px 15px; radius 13px; gap:8px; text-align:left`;
selected `border #2563eb` + `background #eff6ff`, hover `border-color:#2563eb`.
Row line 1: mono request no `.71rem/700/#94a3b8` · kind badge (`radius 6px; .7rem/800`) ·
optional red `cavab müddəti keçir` badge · status pill right-aligned.
Row line 2: subject `.89rem`, weight **800 when status is `Yeni`**, otherwise 700, `line-height:1.35`.
Row line 3: `.75rem/#64748b` — from-line · date · optional paperclip + file count ·
right-aligned owner/SLA label (`#b91c1c` + 700 when overdue).

**Empty state**: dashed `#cbd5e1` border, radius 16, `padding:56px 24px`, 30 px chat icon,
title `.9rem/800`, note `.82rem/#64748b` max-width 360. Titles/notes vary:
`İzlədiyiniz müraciət yoxdur` / `Müddəti keçən müraciət yoxdur` / `Müraciət tapılmadı`.

### 4.7 Detail panel (`<aside>`)
`position:sticky; top:16px; max-height:calc(100vh - 40px); overflow:auto; radius 16px; 1px #e2e8f0`.
Header block (`padding:16px 17px`, bottom border): no · kind badge · status pill; `h2` `1.02rem/800`;
from-line + full timestamp `.77rem/#64748b`; then the **SLA banner** — clock icon + one line,
`padding:10px 12px; radius 10px`:
- open, on time → `#eff6ff` / `#bfdbfe` / `#1e40af`, `Cavab müddətinə N iş günü qalıb (norma M iş günü)`
- open, overdue → `#fee2e2` / `#fecaca` / `#b91c1c`, `Cavab müddəti N gün keçib (norma M iş günü)`
- closed → `#f8fafc` / `#e2e8f0` / `#64748b`, `Müraciət bağlanıb — <status lowercased>`

Body (`padding:16px 17px; gap:15px`), section labels `.72rem/800/uppercase/.07em/#94a3b8`:
1. **Müraciətin mətni** — body in a `#f8fafc` box, `padding:12px 14px; radius 11px; .83rem/1.6`.
2. **Əlavə olunan sənədlər** (if any) — file rows, doc icon + name + size, hover `#f8fafc`.
3. **Müraciətin gedişi** — timeline: 22 px gutter with mark circle and a 2 px `#e2e8f0` connector,
   right side `who` `.82rem/800` + `when` `.73rem/#94a3b8` + `what` `.8rem/#64748b/1.5`,
   `padding-bottom:14px`.
4. **Action box** (handlers, request at this unit, still open) — `#f8fafc` box, radius 12:
   label `Cavab ver`, textarea 3 rows placeholder `Müraciət sahibinin görəcəyi cavab`, then buttons
   `Həll olundu — bağla` (primary) · `Əlavə məlumat istə` · `Başqa şöbəyə yönləndir` (outlined
   primary, opens the forward dialog) · `Rədd et` (`#fecaca` border, `#b91c1c` text).
   **All three status buttons are disabled until the reply is ≥ 10 characters**; disabled styling
   `#e2e8f0` bg / `#94a3b8` text / `cursor:not-allowed`, plus the hint
   `Cavab mətni ən azı 10 simvol olmalıdır — müraciət sahibi məhz bu mətni görəcək.`
   The forward button is never disabled.
5. **Read-only note** (everyone else) — eye icon + one line in a `#f8fafc` box. Four variants:
   sender/open, sender/closed, handler/closed, handler/watching (see source, verbatim).

### 4.8 Create dialog — «Yeni müraciət»
Overlay `rgba(15,23,42,.42)`, panel `max-width:620px; max-height:88vh; radius 16px;
box-shadow 0 24px 60px rgba(15,23,42,.28)`. Click-outside and **Esc** close it; the panel is
focused on open (`role="dialog" aria-modal="true"`), click inside does not bubble.
- Header: `Yeni müraciət` + `Növü seçin — sistem müraciəti avtomatik aidiyyəti şöbəyə göndərəcək.`
- **Müraciətin növü \*** — radio list filtered by the sender's role: 8 px dot in the kind colour,
  label + note, right-aligned `N iş günü`. Selected → `#2563eb` border + `#eff6ff`.
- **Mövzu \*** — input, min 5 chars, placeholder `Bir cümlə ilə nə istədiyiniz`.
- **Müraciətin mətni \*** — textarea 4 rows, **min 20 chars**, placeholder
  `Konkret tarix, fənn və qrup adı yazsanız cavab daha tez gələcək.`; live counter below —
  `Ən azı 20 simvol — hazırda N` in `#dc2626`, then `N simvol` in `#94a3b8`.
- **Sənəd əlavə et** — dashed dropzone button,
  `Fayl seç — PDF, JPG və ya DOCX, maks. 10 MB`; attached files listed with a remove ✕.
- Routing hint box (`#eff6ff` / `#bfdbfe`, info icon) — see 3.2.
- Footer on `#f8fafc`: `Ləğv et` + `Müraciəti göndər` (disabled until valid; on a click while
  invalid, mark the form touched so the two fields turn red `#dc2626`).
- On send: toast `Müraciət <unit>-nə göndərildi — gedişini buradan izləyə bilərsiniz.`

### 4.9 Forward dialog — «Müraciəti yönləndir»
`max-width:540px`. Subtitle = `<no> · <subject>`.
- **Hansı şöbəyə? \*** — every unit except the current one, name + note.
- **Yönləndirmə qeydi \*** — textarea, min 10 chars, placeholder
  `Niyə bu şöbəyə göndərilir və nə gözlənilir`.
- Checkbox, default **on**: `Müraciəti izləməkdə davam edim — cavab veriləndə mənə də bildiriş gəlsin.`
- Info box: `Müraciət sahibi yönləndirməni öz panelində görəcək — müraciət itmir, sadəcə məsul şöbə dəyişir.`
- On send: status → `Yönləndirilib`, `at` → target unit, timeline entry `→`, toast
  `<no> — <unit>-nə yönləndirildi · izləməkdə davam edirsiniz.`

### 4.10 Toast
`position:fixed; left:50%; bottom:24px; transform:translateX(-50%); background:#0f172a;
color:#fff; radius 11px; padding:11px 17px; .83rem/600`, green `#4ade80` check icon,
`role="status" aria-live="polite"`, auto-dismiss after **2800 ms**.

---

## 5. Design tokens

```css
--ems-primary-50:#eff6ff;  --ems-primary-100:#dbeafe; --ems-primary-200:#bfdbfe;
--ems-primary-600:#2563eb; --ems-primary-700:#1d4ed8; --ems-primary-800:#1e40af;
--ems-neutral-0:#ffffff;   --ems-neutral-50:#f8fafc;  --ems-neutral-100:#f1f5f9;
--ems-neutral-200:#e2e8f0; --ems-neutral-300:#cbd5e1; --ems-neutral-400:#94a3b8;
--ems-neutral-500:#64748b; --ems-neutral-700:#334155; --ems-neutral-900:#0f172a;
--ems-success:#16a34a; --ems-success-bg:#dcfce7;
--ems-danger:#dc2626;  --ems-danger-bg:#fee2e2;
--ems-warning:#f59e0b; --ems-warning-bg:#fef3c7;
```

Text colours that are **not** tokens (deliberately darker for contrast on tinted backgrounds):
`#92400e` on warning bg, `#b91c1c` on danger bg, `#15803d` / `#166534` on success bg, `#fecaca`
as the danger border. Never use `--ems-success` or `--ems-warning` for text on a light background.

Font stack `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial,
sans-serif`; request numbers use `ui-monospace, SFMono-Regular, Menlo, monospace`.
Radii: 6 (small badge) · 9–10 (control) · 11–13 (card) · 16 (panel/dialog) · 999 (pill).

---

## 6. Backend notes

Suggested models:

- `RequestKind` — code, label, note, target_unit, sla_days, badge palette (or a constants table
  matching §3.2 exactly).
- `Request` — number (`MR-nnnn`), kind, subject, body, created_by, created_at,
  `current_unit` (FK), `status` (choices per §3.3), `is_open` (derived), attachments.
- `RequestEvent` — request, mark, actor_label, created_at, text. Append-only; every transition
  writes one.
- `Attachment` — request or event, filename, size, file. Accept PDF/JPG/DOCX, max 10 MB.

Permissions:
- `POST /muracietler/yeni` — senders only; kind must be in the role's allowed set (§3.2 column 3);
  the destination unit is computed server-side from the kind, never taken from the client.
- Reply / resolve / reject / request-info — only if `request.current_unit == user.unit` and the
  request is open. Reply text ≥ 10 chars, server-validated.
- Forward — same precondition; target must differ from the current unit; note ≥ 10 chars.
- A sender may only read their own requests; a handler reads requests at their unit plus those
  their unit appears on in the event log (the `İzlədiklərim` scope).

Notifications: on every status change, notify the requester; on forward, notify the target unit and
— if "izləməkdə davam edim" was checked — keep the forwarding unit subscribed.

SLA / overdue is computed in **working days** from submission against `kind.sla_days`. The demo
uses a plain `age` integer; replace it with a real business-day calculation.

## 7. Accessibility (already in the design, keep it)

- Visually-hidden `<label>` on the search input; `aria-current` on tabs and selected list rows.
- Dropdown `aria-haspopup="listbox"` / `aria-expanded`, options `role="option"` + `aria-selected`,
  Enter/Space activation.
- Dialogs `role="dialog" aria-modal="true" aria-labelledby`, focused on open, Esc to close;
  add a focus trap in production.
- Toast `role="status" aria-live="polite"`.
- Focus ring: `outline:2px solid #2563eb; outline-offset:2px` on `:focus-visible`;
  inputs `border-color:#2563eb; box-shadow:0 0 0 3px #dbeafe`.
- Never rely on the status colour alone — the pill always carries its text label.

## 8. Definition of done

1. One template + one view serving all six roles; role comes from the session user, not a URL param.
2. All eight kinds with correct routing and SLA; destination computed server-side.
3. Full state machine with an append-only timeline, and forwarding that preserves the watch list.
4. Validation enforced both client- and server-side (5 / 20 / 10 characters).
5. Filters, tabs, KPI-card shortcuts and debounced search all work against real data.
6. Visual output matches `index.html` at 1400 px, and degrades to one column on narrow screens.
