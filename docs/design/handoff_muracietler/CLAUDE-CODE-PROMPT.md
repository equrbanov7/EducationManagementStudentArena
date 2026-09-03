# Task for Claude Code — Müraciətlər paneli (Requests module)

Copy everything below into Claude Code as the task.

---

You are implementing one new module in this Django codebase: **Müraciətlər paneli** — a
university-wide request/ticket system. A complete high-fidelity design handoff is in
`design_handoff_muracietler/`.

**Read first, in this order:**

1. `design_handoff_muracietler/README.md` — the full specification: roles, routing table, statuses,
   state machine, every component's exact CSS values, backend model suggestions, a11y, DoD.
2. `design_handoff_muracietler/index.html` — open in a browser. It renders the same screen for all
   six roles, live and interactive. Click through: submit a request as Tələbə, reply and forward as
   Dekanlıq. This is the behaviour you are reproducing.
3. `design_handoff_muracietler/design/0X Rol - *.dc.html` — per-role source. They differ from each
   other by exactly one value (the `role` prop), so build **one** view and **one** template that
   branch on the logged-in user's role.

**Rules:**

- The `.dc.html` files are design references, not production code — do not copy them into the app
  and do not ship `support.js`. Recreate the UI as Django templates using the existing
  `static/css/design-tokens.css` / `ems_components.css` conventions.
- Hard-coded arrays in the prototypes (`UNITS`, `KINDS`, `STATUS`, `TICKETS`) are stand-ins for
  querysets/constants. `UNITS`, `KINDS` and `STATUS` must be reproduced **exactly** as in README §3.
- All UI copy is Azerbaijani and **final** — use it verbatim, including placeholders, empty states,
  hint texts and toast messages.
- Routing and permissions are server-side. The client never chooses the destination unit; the kind
  decides it. Never trust a role or unit sent from the browser.
- Match the design pixel-for-pixel at a 1400 px canvas; collapse to a single column with the detail
  panel as a slide-over below ~1100 px.

**Deliver:**

1. Models + migration: `RequestKind` (or constants), `Request`, `RequestEvent`, `Attachment`.
2. One list/detail view with the six-role branching, plus endpoints for: create, reply+resolve,
   reply+request-info, reply+reject, forward, attachment upload/download.
3. Template + CSS matching the design; filters, tabs, KPI shortcuts, debounced search (260 ms).
4. Server-side validation: subject ≥ 5, body ≥ 20, reply/forward note ≥ 10 characters;
   attachments PDF/JPG/DOCX, max 10 MB.
5. Notifications on every status change, and the "izləməkdə davam edim" watch subscription.
6. Tests for the state machine and for permission boundaries (a sender cannot act on a request;
   a unit cannot act on a request that is not currently at that unit).

Work through README §8 (Definition of done) as the acceptance checklist and report which items pass.
