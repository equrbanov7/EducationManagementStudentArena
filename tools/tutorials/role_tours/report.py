"""Generate an Azerbaijani Markdown audit of the role-tour menu, screenshots and chapters."""

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep
from urllib.parse import parse_qs, quote, urlsplit

if __package__:
    from .scenes import role_scenes, section_key
else:
    from scenes import role_scenes, section_key

TUTORIALS = Path(__file__).resolve().parents[1]
RUN = Path("/private/tmp/ems_tours_1128")
STATES = {
    "initial": "ilkin",
    "opened": "açıldı",
    "same": "klik, eyni görünüş",
    "conditional": "şərti",
    "failed": "xəta",
    "missing": "təsdiq yoxdur",
}


def read_json(path):
    # The recorder writes progress.json after every menu while a report may be requested.
    for attempt in range(3):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            if attempt == 2:
                raise
            sleep(0.05)


def escape(value):
    return (
        " ".join(str(value).split()).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|")
    )


def timestamp(value):
    minutes, seconds = divmod(int(value), 60)
    return f"{minutes}:{seconds:02}"


def present(path):
    try:
        return path.is_file() and path.stat().st_size > 0
    except FileNotFoundError:
        return False


def reason(message):
    msg = str(message or "").splitlines()[0] if message else ""
    known = (
        ("not attached", "Seçim səhifə yenilənərkən dəyişdi."),
        ("no longer visible", "Seçim klik anında görünmədi."),
        ("Timeout", "Gözləmə müddəti bitdi."),
        ("Target page", "Çəkiliş zamanı səhifə bağlandı."),
        ("403", "Səhifə girişə icazə vermədi (403)."),
        ("404", "Səhifə tapılmadı (404)."),
        ("500", "Server xətası qeydə alındı (500)."),
    )
    for needle, translated in known:
        if needle.casefold() in msg.casefold():
            return translated
    return msg or "Səbəb çəkilişdə göstərilməyib."


def describe_controls(row, folder):
    """Identify each control by its parent and label, retaining every still-recorded error."""
    controls = {}
    notices = []

    def identify(item):
        key = (item.get("parent", ""), item.get("label", "").strip())
        control = controls.setdefault(key, {"tab": False, "state": "missing"})
        if item.get("tab"):
            control["tab"] = True
        return key, control

    for entry in row.get("available", []):
        identify(entry)
    for entry in row.get("opened", []):
        key, control = identify(entry)
        frames = [entry.get("frame"), entry.get("before", entry.get("frame"))]
        if not all(frame and present(folder / frame) for frame in frames):
            notices.append(("Çatışmayan kadr", key, "Seçimə aid görüntü faylı tapılmadı."))
            continue
        if entry.get("initial"):
            control["state"] = "initial"
        elif entry.get("changed") is False:
            control["state"] = "same"
        else:
            control["state"] = "opened"
    for field, state, title in (("unavailable", "conditional", "Şərti seçim"), ("errors", "failed", "Uğursuz sınaq")):
        for entry in row.get(field, []):
            key, control = identify(entry)
            if control["state"] in {"missing", "conditional"}:
                control["state"] = state
            notices.append((title, key, reason(entry.get("why") or entry.get("message"))))
    for key, control in controls.items():
        if control["state"] == "missing":
            notices.append(("Nəticəsiz seçim", key, "Açılış və ya ilkin vəziyyət üçün kadr təsdiqlənməyib."))
    return controls, notices


def inspect_master(role, records, masters, example):
    key = "tour-" + role.replace("_", "-")
    folder = masters / key
    if not present(folder / "meta.json"):
        return {}, "Master məlumatı hələ yoxdur", "", []
    master = read_json(folder / "meta.json")
    chapters = master.get("chapters", [])
    duration = master.get("duration", 0)
    notes = []
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        duration = 0
        notes.append("Müddət təsdiqlənməyib.")
    positions = [c.get("start") for c in chapters]
    if not chapters or any(
        not isinstance(n, (int, float)) or not math.isfinite(n) or not 0 <= n < duration for n in positions
    ):
        notes.append("Fəsil vaxtları və ya video müddəti natamamdır.")
    elif positions != sorted(set(positions)):
        notes.append("Fəsil vaxtlarının ardıcıllığı pozulub.")
    expected = Counter(
        (s["section"], s["title"], bool(s.get("menu"))) for s in role_scenes(role, records, [], example=example)
    )
    actual = Counter((s.get("section"), s.get("title"), bool(s.get("menu"))) for s in chapters)
    for label, diff in (
        ("Çəkilişdə var, masterdə yoxdur", expected - actual),
        ("Yalnız masterdə var", actual - expected),
    ):
        if diff:
            notes.append(f"{label} ({sum(diff.values())}) — " + ", ".join(str(t) for _, t, _ in sorted(diff, key=str)))
    absent = [ext.upper() for ext in ["mp4", "srt", "vtt"] if not present(folder / f"{key}.{ext}")]
    if absent:
        notes.append("Master qovluğunda çatışmır — " + ", ".join(absent))
    links = {
        c["section"]: int(c["start"])
        for c in chapters
        if c.get("menu") and isinstance(c.get("start"), (int, float)) and math.isfinite(c["start"]) and c["start"] >= 0
    }
    movie = f"index.html?lesson={quote(key)}" if present(folder / f"{key}.mp4") else ""
    return links, f"{timestamp(duration)} · {len(chapters)} fəsil", movie, notes


def choices(controls, is_tab):
    result = []
    for (parent, label), values in controls.items():
        if values["tab"] != is_tab:
            continue
        name = f"{parent} → {label}" if parent else label
        result.append(f"{escape(name)} ({STATES[values['state']]})")
    return "<br>".join(result) or "—"


def role_report(role, label, menu, captures, masters, output, example):
    progress = captures / role / "progress.json"
    rows = read_json(progress) if progress.is_file() else []
    indexed = {row["href"]: row for row in rows}
    listed = {entry["href"] for entry in menu}
    eligible = [r for r in rows if r["href"] in listed]
    times, master, movie, master_notes = inspect_master(role, eligible, masters, example)
    stats = Counter()
    excluded = []
    role_scenes(role, eligible, [], example=example, excluded=excluded)
    stats["excluded_scenes"] = len(excluded)
    notices = [
        (
            s["title"],
            "Rolun videosundan çıxarılıb",
            "",
            ", ".join(s["missing"]) or "Bölmənin əməliyyat səlahiyyəti yoxdur.",
        )
        for s in excluded
    ]
    details = []
    for item in menu:
        label_text = item["label"]
        row = indexed.get(item["href"])
        stats["menus"] += 1
        if row is None:
            stats["pending_menu"] += 1
            notices.append((label_text, "Çəkiliş gözlənilir", "", "Bu menyu üçün çəkiliş qeydi yoxdur."))
            details.append((label_text, "Çəkilməyib", "—", "—", "—"))
            continue
        location = captures / role / str(row.get("frameFolder", row["id"]))
        menu_ok = row.get("ok") and all(present(location / name) for name in ("menu.jpg", "open.jpg"))
        problem = ""
        expected = urlsplit(item["href"])
        group = parse_qs(expected.query).get("ss_group", [""])[0]
        if row.get("subLabel"):
            label_text = f"{label_text} · {row['subLabel']}"
        elif group:
            label_text = f"{label_text} ({group})"
        actual = urlsplit(row.get("destination", ""))
        if menu_ok and not item.get("key") and actual.path.rstrip("/") != expected.path.rstrip("/"):
            problem = f"Açılış kadrının ünvanı {actual.path or '—'}, menyunun ünvanı {expected.path}."
        if (
            menu_ok
            and group
            and (
                row.get("subGroup") != group
                or not row.get("subLabel")
                or parse_qs(actual.query).get("ss_group") != [group]
            )
        ):
            problem = "Açılış kadrında seçilmiş qrupun ünvanı və bölmə başlığı təsdiqlənmədi."
        if problem:
            menu_ok = False
        if menu_ok:
            stats["menu_ok"] += 1
            if row.get("scopeNote"):
                notices.append((label_text, "Əhatə şərti", "", row["scopeNote"]))
        else:
            stats["failed_menu"] += 1
            msg = problem or (reason(row.get("error")) if not row.get("ok") else "Menyu və ya bölmə kadrı tapılmadı.")
            notices.append((label_text, "Bölmə açılışı təsdiqlənmədi", "", msg))
        controls, control_notes = describe_controls(row, location) if not problem else ({}, [])
        for control in controls.values():
            group = "tab" if control["tab"] else "other"
            stats[group] += 1
            stats[group + "_" + control["state"]] += 1
        for title, key, msg in control_notes:
            notices.append((label_text, title, " → ".join(x for x in key if x), msg))
        start = times.get(section_key(row))
        t = "—" if start is None else timestamp(start)
        if movie and start is not None:
            t = f"[{t}]({movie}&t={start})"
        details.append(
            (label_text, "Açıldı" if menu_ok else "Təsdiqlənmədi", t, choices(controls, True), choices(controls, False))
        )
    for extra in sorted(set(indexed) - listed):
        notices.append((indexed[extra]["label"], "İnventardan kənar", "", "Çəkiliş qeydi cari rol menyusunda yoxdur."))
    if len(indexed) != len(rows):
        notices.append(("Menyu", "Təkrar ünvan", "", "Çəkiliş qeydlərində eyni menyu ünvanı bir neçə dəfə var."))
    body = [f"## {escape(label)}", "", f"Video — [{master}]({movie})." if movie else f"Video — {master}.", ""]
    if master_notes:
        body += [f"- {escape(n)}" for n in master_notes] + [""]
    if notices:
        body += ["### Şərti vəziyyətlər və açıq qalan sınaqlar", ""]
        for name, kind, ctrl, msg in notices:
            source = f"{name} → {ctrl}" if ctrl else name
            body.append(f"- **{escape(source)}** — {escape(kind)}. {escape(msg)}")
        body.append("")
    body += [
        "| Menyu | Açılış | Videoda | Tablar | Digər seçimlər |",
        "|---|---|---:|---|---|",
    ]
    for name, status, t, tabs, other in details:
        body.append(f"| {escape(name)} | {status} | {t} | {tabs} | {other} |")
    body.append("")
    return stats, body


def summary_line(name, count):
    confirmed = count["tab_initial"] + count["tab_opened"]
    return (
        f"| {escape(name)} | {count['menu_ok']} / {count['menus']} | {count['tab']} | {count['tab_initial']} | "
        f"{count['tab_opened']} | {count['tab_same']} | {count['tab_conditional']} | {count['tab_failed']} | "
        f"{count['tab_missing']} | {confirmed} / {count['tab']} | {count['other_opened']} / {count['other']} |"
    )


def build_report(inventory, captures, masters, labels, output):
    catalog = read_json(inventory)
    examples = read_json(labels)
    total = Counter()
    details = []
    summary = []
    for role, menu in catalog.items():
        label = examples.get(role, {}).get("label") or role
        stats, body = role_report(role, label, menu, captures, masters, output, examples[role])
        total.update(stats)
        summary.append(summary_line(label, stats))
        details.extend(body)
    explanation = [
        "# Kabinet videolarında menyular və tablar",
        "",
        f"Sintetik hesablarda {len(catalog)} rol üzrə inventara alınan {total['menus']} menyu keçidindən "
        f"{total['menu_ok']} keçidin menyu və açılış kadrı var. Eyni menyu hər rolun əhatəsində ayrıca sayılır. "
        f"Çəkilişi gözlənilən menyuların sayı {total['pending_menu']}, açılışı təsdiqlənməyənlərin sayı {total['failed_menu']}.",
        "",
        f"Rolun əməliyyat səlahiyyətinə uyğun gəlməyən {total['excluded_scenes']} çəkilmiş səhnə video fəsillərindən çıxarılıb.",
        "",
        "Hər rolun bölməsində menyu adları, seçimlər və hazır videoda fəslin başladığı vaxt göstərilir. "
        "Cədvəldə vaxt dəqiqə və saniyə ilə verilir. Tire uyğun kadrın, fəslin və ya seçimin qeydə alınmadığını göstərir.",
        "",
        "«İlkin» tab açılış kadrında artıq seçilib. «Açıldı» klikdən sonrakı görüntüsü qeydə alınmış keçiddir. "
        "«Klik, eyni görünüş» kliklə sınaqdan keçib, lakin ayrıca vəziyyət dəyişikliyi qeydə alınmayıb. "
        "«Şərti» seçim həmin nümunədə passiv, gizli və ya məlumat yükləndikdən sonra əlçatmaz olub. "
        "«Xəta» uğursuz cəhdi, «təsdiq yoxdur» isə nəticə və ya kadr çatışmazlığını bildirir.",
        "",
        "Tabların ümumi sayı çəkilişin tab kimi tanıdığı görünən seçimlərdən və açılan alt tablardan hesablanıb. "
        "«Təsdiqli» sütununa ilkin və açılan tablar daxildir. «Digər açılan» sütunu tabdan kənar seçimlərdə "
        "kliklə qeydə alınan keçidlərin sayını həmin seçimlərin ümumi sayı ilə müqayisə edir. "
        "Açılmamış bölmələrin tab sayı məlum deyil. Görünməyən səlahiyyətlər, fərqli məlumat vəziyyətləri "
        "və məlumatı saxlayan əməliyyatlar üçün nəticə çıxarılmır.",
        "",
        "| Rol | Menyu açıldı / inventar | Tab | İlkin | Açıldı | Eyni görünüş | Şərti | Xəta | Təsdiq yoxdur | Təsdiqli / tab | Digər açılan / cəmi |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    return "\n".join(explanation + summary + [summary_line("Cəmi", total), ""] + details).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description="Rol turlarının menyu və tab hesabatını Markdown formatında yazır.")
    parser.add_argument("output", type=Path, help="Yaradılacaq Markdown faylının yolu")
    parser.add_argument("--inventory", type=Path, default=RUN / "inventory.json")
    parser.add_argument("--captures", type=Path, default=RUN / "capture")
    parser.add_argument("--masters", type=Path, default=TUTORIALS / "out")
    parser.add_argument("--labels", type=Path, default=TUTORIALS / "scenarios/faq-role-examples.json")
    args = parser.parse_args()
    report = build_report(args.inventory, args.captures, args.masters, args.labels, args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.output.parent, delete=False) as handle:
        handle.write(report)
    Path(handle.name).replace(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
