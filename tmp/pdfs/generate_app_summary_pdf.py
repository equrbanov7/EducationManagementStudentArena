from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output" / "pdf"
OUTPUT_PATH = OUTPUT_DIR / "emsarena-app-summary.pdf"

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 34
CONTENT_WIDTH = PAGE_WIDTH - (MARGIN * 2)
ACCENT = colors.HexColor("#144A74")
ACCENT_SOFT = colors.HexColor("#EAF3FB")
PANEL_BG = colors.HexColor("#F7F9FC")
TEXT = colors.HexColor("#203040")
MUTED = colors.HexColor("#5A6B7A")
LINE = colors.HexColor("#D7E1EA")


def wrap(text: str, font_name: str, font_size: float, width: float) -> list[str]:
    return simpleSplit(text, font_name, font_size, width)


def draw_lines(
    pdf: canvas.Canvas,
    lines: list[str],
    *,
    x: float,
    y_top: float,
    font_name: str,
    font_size: float,
    leading: float,
    color=TEXT,
) -> float:
    pdf.setFont(font_name, font_size)
    pdf.setFillColor(color)
    y = y_top
    for line in lines:
        pdf.drawString(x, y, line)
        y -= leading
    return y


def draw_bullets(
    pdf: canvas.Canvas,
    items: list[str],
    *,
    x: float,
    y_top: float,
    width: float,
    font_name: str = "Helvetica",
    font_size: float = 9.0,
    leading: float = 11.0,
) -> float:
    bullet_x = x
    text_x = x + 10
    text_width = width - 10
    y = y_top
    for item in items:
        lines = wrap(item, font_name, font_size, text_width)
        pdf.setFont(font_name, font_size)
        pdf.setFillColor(TEXT)
        pdf.drawString(bullet_x, y, "-")
        for index, line in enumerate(lines):
            pdf.drawString(text_x, y - (index * leading), line)
        y -= max(leading * len(lines), leading) + 3
    return y


def panel_height(body_lines: list[str], *, body_leading: float, title_gap: float = 17, padding: float = 14) -> float:
    return padding + title_gap + (len(body_lines) * body_leading) + padding


def draw_panel(
    pdf: canvas.Canvas,
    *,
    x: float,
    y_top: float,
    width: float,
    height: float,
    title: str,
    body_lines: list[str],
    body_font: str = "Helvetica",
    body_size: float = 9.2,
    body_leading: float = 11.2,
) -> None:
    pdf.setFillColor(PANEL_BG)
    pdf.setStrokeColor(LINE)
    pdf.roundRect(x, y_top - height, width, height, 10, fill=1, stroke=1)

    pdf.setFont("Helvetica-Bold", 10.2)
    pdf.setFillColor(ACCENT)
    pdf.drawString(x + 14, y_top - 18, title)

    draw_lines(
        pdf,
        body_lines,
        x=x + 14,
        y_top=y_top - 35,
        font_name=body_font,
        font_size=body_size,
        leading=body_leading,
        color=TEXT,
    )


def draw_section_label(pdf: canvas.Canvas, title: str, x: float, y: float) -> None:
    pdf.setFillColor(ACCENT)
    pdf.setFont("Helvetica-Bold", 11.6)
    pdf.drawString(x, y, title)
    label_width = stringWidth(title, "Helvetica-Bold", 11.6)
    pdf.setStrokeColor(LINE)
    pdf.setLineWidth(1)
    pdf.line(x + label_width + 10, y - 2, x + CONTENT_WIDTH, y - 2)


def draw_architecture(pdf: canvas.Canvas, x: float, y_top: float, width: float) -> float:
    box_height = 168
    pdf.setFillColor(ACCENT_SOFT)
    pdf.setStrokeColor(LINE)
    pdf.roundRect(x, y_top - box_height, width, box_height, 12, fill=1, stroke=1)

    node_titles = ["Browser/UI", "Django app", "Data/storage", "Async/realtime"]
    node_bodies = [
        "Templates, Bootstrap 5,\nvanilla JS, AJAX",
        "config.urls mounts blog,\nlive_exam, courses,\nassignments, labs, more",
        "PostgreSQL by default;\nlocal SQLite fallback;\nprotected media files",
        "ASGI + Channels sockets;\nRedis cache/channel layer;\nCelery email tasks",
    ]

    gap = 10
    node_width = (width - 30 - (gap * 3)) / 4
    node_height = 64
    node_y = y_top - 18

    for index, (title, body) in enumerate(zip(node_titles, node_bodies, strict=True)):
        node_x = x + 15 + (index * (node_width + gap))
        pdf.setFillColor(colors.white)
        pdf.setStrokeColor(colors.HexColor("#C7D7E5"))
        pdf.roundRect(node_x, node_y - node_height, node_width, node_height, 9, fill=1, stroke=1)
        pdf.setFillColor(ACCENT)
        pdf.setFont("Helvetica-Bold", 9.0)
        pdf.drawString(node_x + 10, node_y - 14, title)
        draw_lines(
            pdf,
            body.splitlines(),
            x=node_x + 10,
            y_top=node_y - 28,
            font_name="Helvetica",
            font_size=7.7,
            leading=9.2,
            color=TEXT,
        )

        if index < 3:
            start_x = node_x + node_width
            mid_y = node_y - (node_height / 2)
            end_x = node_x + node_width + gap
            pdf.setStrokeColor(ACCENT)
            pdf.setLineWidth(1.2)
            pdf.line(start_x + 3, mid_y, end_x - 8, mid_y)
            pdf.line(end_x - 8, mid_y, end_x - 12, mid_y + 3)
            pdf.line(end_x - 8, mid_y, end_x - 12, mid_y - 3)

    notes = [
        "One ASGI entrypoint serves both HTTP and WebSocket traffic (`config/asgi.py`).",
        "Versioned live-exam API routes live under `/api/v1/`; domain apps mount from `config/urls.py`.",
        "Local settings can run with SQLite, in-memory cache/channel layers, and console email when external services are absent.",
    ]
    draw_bullets(
        pdf,
        notes,
        x=x + 15,
        y_top=y_top - 96,
        width=width - 30,
        font_size=8.2,
        leading=10.0,
    )
    return y_top - box_height


def build_pdf() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pdf = canvas.Canvas(str(OUTPUT_PATH), pagesize=A4)
    pdf.setTitle("EMS Arena App Summary")
    pdf.setAuthor("OpenAI Codex")
    pdf.setSubject("One-page repo-evidence summary")

    y = PAGE_HEIGHT - MARGIN

    pdf.setFillColor(ACCENT)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(MARGIN, y, "EMS Arena")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 9.2)
    pdf.drawString(MARGIN, y - 15, "One-page summary based on repo evidence only")
    pdf.setStrokeColor(ACCENT)
    pdf.setLineWidth(2)
    pdf.line(MARGIN, y - 24, PAGE_WIDTH - MARGIN, y - 24)
    y -= 42

    col_gap = 16
    col_width = (CONTENT_WIDTH - col_gap) / 2

    what_is = (
        "EMS Arena is a Django-based educational management system for universities and other "
        "educational institutions. The repo combines course delivery, exams, assignments, labs, "
        "blog content, and a live quiz mode in one server-rendered web app."
    )
    who_for = (
        "Primary persona: teachers and academic staff who manage courses, exams, assignments, "
        "and labs. Students are secondary end users for enrollment, submissions, exams, and live sessions."
    )

    what_is_lines = wrap(what_is, "Helvetica", 9.2, col_width - 28)
    who_for_lines = wrap(who_for, "Helvetica", 9.2, col_width - 28)
    top_height = max(
        panel_height(what_is_lines, body_leading=11.2),
        panel_height(who_for_lines, body_leading=11.2),
    )
    draw_panel(pdf, x=MARGIN, y_top=y, width=col_width, height=top_height, title="What it is", body_lines=what_is_lines)
    draw_panel(
        pdf,
        x=MARGIN + col_width + col_gap,
        y_top=y,
        width=col_width,
        height=top_height,
        title="Who it's for",
        body_lines=who_for_lines,
    )
    y -= top_height + 18

    draw_section_label(pdf, "What it does", MARGIN, y)
    y -= 14
    feature_box_height = 105
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(LINE)
    pdf.roundRect(MARGIN, y - feature_box_height, CONTENT_WIDTH, feature_box_height, 10, fill=1, stroke=1)
    features = [
        "Course hubs with topics, resources, enrollments, and groups.",
        "Test and written exams, question banks, randomization, time limits, and anonymous grading.",
        "Assignments and projects with deadlines, retries, file or link submission, and teacher feedback.",
        "Lab workflows with per-student question allocation, timed blocks, and grading.",
        "Live exam sessions with QR or PIN join, leaderboards, and real-time host and player updates.",
        "Blog, subscriptions, notifications, organization roles, audit logging, and multi-language UI.",
    ]
    draw_bullets(pdf, features, x=MARGIN + 15, y_top=y - 16, width=CONTENT_WIDTH - 30)
    y -= feature_box_height + 18

    draw_section_label(pdf, "How it works", MARGIN, y)
    y -= 14
    y = draw_architecture(pdf, MARGIN, y, CONTENT_WIDTH) - 18

    draw_section_label(pdf, "How to run", MARGIN, y)
    y -= 14
    run_box_height = 108
    pdf.setFillColor(PANEL_BG)
    pdf.setStrokeColor(LINE)
    pdf.roundRect(MARGIN, y - run_box_height, CONTENT_WIDTH, run_box_height, 10, fill=1, stroke=1)
    run_steps = [
        "Create and activate a virtualenv: `python3 -m venv venv && source venv/bin/activate`",
        "Install deps: `pip install -r requirements.txt`",
        "Create `.env` with at least `SECRET_KEY=...`; `.env.example`: Not found in repo.",
        "Apply DB setup: `python manage.py migrate` and optionally `python manage.py createsuperuser`",
        "Start the app: `python manage.py runserver`",
    ]
    draw_bullets(pdf, run_steps, x=MARGIN + 15, y_top=y - 16, width=CONTENT_WIDTH - 30, font_size=8.7, leading=10.6)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica-Oblique", 7.8)
    pdf.drawString(
        MARGIN + 15,
        y - run_box_height + 11,
        "Optional full stack: `docker compose up -d` for Postgres and Redis. Local settings also support SQLite and in-memory defaults.",
    )
    y -= run_box_height + 12

    footer = (
        "Repo evidence used: README.md, config/settings/base.py, config/settings/local.py, "
        "config/urls.py, config/asgi.py, config/celery.py, apps/live_exam/consumers.py, core/email_tasks.py."
    )
    footer_lines = wrap(footer, "Helvetica", 6.8, CONTENT_WIDTH)
    draw_lines(pdf, footer_lines, x=MARGIN, y_top=max(y, MARGIN + 18), font_name="Helvetica", font_size=6.8, leading=8.0, color=MUTED)

    pdf.save()
    return OUTPUT_PATH


if __name__ == "__main__":
    path = build_pdf()
    print(path)
