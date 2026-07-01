"""coding_runtime paketi — files."""

import re
from pathlib import Path

from apps.exams.models import CodingExamQuestion
from apps.exams.services.coding_polyfills import NODE_PROMPT_POLYFILL, javascript_main_has_top_level_input_loop

from ._shared import (
    sanitize_filename,
)
from .constants import (
    MAX_CODE_BYTES,
    TRIPLE_QUOTE_RE,
)


def file_language_for_name(filename, fallback_language):
    suffix = Path(filename).suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix == ".js":
        return "javascript"
    if suffix in {".cpp", ".cc", ".cxx", ".hpp", ".h"}:
        return "cpp"
    if suffix == ".java":
        return "java"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix == ".css":
        return "css"
    return fallback_language


def execution_language_for_filename(filename, fallback_language):
    language = file_language_for_name(filename, fallback_language)
    if language == "css":
        return CodingExamQuestion.LANGUAGE_HTML
    allowed_languages = {value for value, _ in CodingExamQuestion.LANGUAGE_CHOICES}
    return language if language in allowed_languages else fallback_language


def default_starter_code(language):
    if language == CodingExamQuestion.LANGUAGE_CPP:
        return "#include <iostream>\n" "using namespace std;\n\n" "int main() {\n" "    return 0;\n" "}\n"
    if language == CodingExamQuestion.LANGUAGE_JAVA:
        return "public class Main {\n" "    public static void main(String[] args) {\n" "    }\n" "}\n"
    return ""


def build_starter_files(coding_question):
    language = coding_question.language
    starter_code = coding_question.starter_code or ""
    if language == CodingExamQuestion.LANGUAGE_HTML:
        return [
            {
                "name": "index.html",
                "content": starter_code
                or (
                    "<!doctype html>\n"
                    '<html lang="en">\n'
                    "<head>\n"
                    '  <meta charset="UTF-8">\n'
                    '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
                    "  <title>Practical preview</title>\n"
                    '  <link rel="stylesheet" href="style.css">\n'
                    "</head>\n"
                    "<body>\n\n"
                    '  <script src="script.js"></script>\n'
                    "</body>\n"
                    "</html>\n"
                ),
                "language": "html",
                "is_main": True,
            },
            {"name": "style.css", "content": "", "language": "css", "is_main": False},
            {"name": "script.js", "content": "", "language": "javascript", "is_main": False},
        ]

    filename = coding_question.default_filename
    return [
        {
            "name": filename,
            "content": starter_code or default_starter_code(language),
            "language": file_language_for_name(filename, language),
            "is_main": True,
        }
    ]


def _line_has_unclosed_triple_quote(line, current_quote=None):
    matches = list(TRIPLE_QUOTE_RE.finditer(line))
    if not matches:
        return current_quote

    quote = current_quote
    for match in matches:
        marker = match.group(1)
        if quote is None:
            quote = marker
        elif quote == marker:
            quote = None
    return quote


def _line_bracket_delta(line):
    code = line.split("#", 1)[0]
    return sum(1 for char in code if char in "([{") - sum(1 for char in code if char in ")]}")


def normalize_python_indentation(content):
    """Repair accidental tiny unindents that CodeMirror can leave hard to see."""
    text = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    keep_trailing_newline = text.endswith("\n")
    lines = text.split("\n")
    if keep_trailing_newline:
        lines = lines[:-1]

    normalized_lines = []
    indent_stack = [0]
    bracket_depth = 0
    triple_quote = None
    explicit_continuation = False
    previous_opens_suite = False

    for raw_line in lines:
        line = raw_line
        leading_text = line[: len(line) - len(line.lstrip(" \t"))]
        expanded_leading = leading_text.expandtabs(4)
        leading = len(expanded_leading)
        stripped = line.lstrip(" \t")

        if stripped and triple_quote is None and bracket_depth <= 0 and not explicit_continuation:
            target_indent = leading
            current_indent = indent_stack[-1]
            if previous_opens_suite and leading > current_indent:
                if leading not in indent_stack:
                    indent_stack.append(leading)
            elif leading < current_indent and leading not in indent_stack:
                lower_indents = [value for value in indent_stack if value < leading]
                target_indent = max(lower_indents) if lower_indents else 0
            elif current_indent == 0 and 0 < leading < 4 and not previous_opens_suite:
                target_indent = 0

            if target_indent != leading or "\t" in leading_text:
                line = (" " * target_indent) + stripped
                leading = target_indent

            if leading < indent_stack[-1]:
                while len(indent_stack) > 1 and indent_stack[-1] > leading:
                    indent_stack.pop()

        normalized_lines.append(line)

        if not stripped:
            continue

        triple_quote = _line_has_unclosed_triple_quote(line, triple_quote)
        if triple_quote is None:
            bracket_depth = max(0, bracket_depth + _line_bracket_delta(line))
            explicit_continuation = line.rstrip().endswith("\\")
            previous_opens_suite = bracket_depth == 0 and line.rstrip().endswith(":")
        else:
            explicit_continuation = False
            previous_opens_suite = False

    return "\n".join(normalized_lines) + ("\n" if keep_trailing_newline else "")


def normalize_files(files, *, coding_question):
    if not isinstance(files, list):
        files = []
    if not files:
        files = build_starter_files(coding_question)

    normalized = []
    seen_names = set()
    for item in files:
        if not isinstance(item, dict):
            continue
        name = sanitize_filename(item.get("name"))
        if not name or name in seen_names:
            continue
        content = str(item.get("content", ""))
        if len(content.encode("utf-8")) > MAX_CODE_BYTES:
            content = content.encode("utf-8")[:MAX_CODE_BYTES].decode("utf-8", errors="ignore")
        language = file_language_for_name(name, coding_question.language)
        if language == "python":
            content = normalize_python_indentation(content)
        normalized.append(
            {
                "name": name,
                "content": content,
                "language": language,
                "is_main": bool(item.get("is_main")),
            }
        )
        seen_names.add(name)

    if not normalized:
        normalized = build_starter_files(coding_question)

    if not any(item["is_main"] for item in normalized):
        normalized[0]["is_main"] = True
    else:
        main_seen = False
        for item in normalized:
            if item["is_main"] and not main_seen:
                main_seen = True
            elif item["is_main"]:
                item["is_main"] = False

    return normalized


def get_main_file(files):
    return next((item for item in files if item.get("is_main")), files[0] if files else None)


def mark_file_as_main(files, filename):
    safe_name = sanitize_filename(filename)
    if not safe_name:
        return files
    if not any(item.get("name") == safe_name for item in files):
        return files
    return [{**item, "is_main": item.get("name") == safe_name} for item in files]


def _cpp_contains_main(content):
    return bool(re.search(r"\bmain\s*\(", content or ""))


def _wrap_cpp_snippet(content):
    prefix_lines = []
    body_lines = []
    for line in (content or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#include") or stripped.startswith("using "):
            prefix_lines.append(line)
        else:
            body_lines.append(line)

    header_lines = []
    if not any(re.match(r"\s*#include\s*<iostream>", line) for line in prefix_lines):
        header_lines.append("#include <iostream>")
    header_lines.extend(prefix_lines)
    if not any(re.match(r"\s*using\s+namespace\s+std\s*;", line) for line in prefix_lines):
        header_lines.append("using namespace std;")

    body = "\n".join(body_lines).strip("\n")
    indented_body = "\n".join(("    " + line if line.strip() else "") for line in body.splitlines())
    wrapped_lines = [*header_lines, "", "int main() {"]
    if indented_body:
        wrapped_lines.append(indented_body)
    wrapped_lines.extend(["    return 0;", "}"])
    return "\n".join(wrapped_lines) + "\n"


def prepare_files_for_execution(language, files):
    prepared_files = [dict(item) for item in files]

    if language == CodingExamQuestion.LANGUAGE_CPP:
        main_file = get_main_file(prepared_files)
        if main_file and not _cpp_contains_main(main_file.get("content", "")):
            main_file["content"] = _wrap_cpp_snippet(main_file.get("content", ""))
        return prepared_files

    if language == CodingExamQuestion.LANGUAGE_JAVASCRIPT:
        main_file = get_main_file(prepared_files)
        if main_file and not javascript_main_has_top_level_input_loop(main_file.get("content", "")):
            main_file["content"] = NODE_PROMPT_POLYFILL + (main_file.get("content", "") or "")
        return prepared_files

    return prepared_files
