"""coding_runtime — geriyə-uyğun fasad paketi."""

# Testlər `patch("...coding_runtime.subprocess.run")` / `shutil.which` istifadə edir.
# Bu modulları fasadda expose edirik ki, həmin patch-lər qlobal işləsin (eyni modul
# obyekti execution.py-də də istifadə olunur). `_ensure_docker_image` və `execute_code`
# üçün call-time fasad həlli execution/grading-də edilir.
import shutil  # noqa: F401
import subprocess  # noqa: F401

from apps.exams.services.coding_polyfills import (  # noqa: F401
    NODE_PROMPT_POLYFILL,
    javascript_main_has_top_level_input_loop,
)

from ._shared import (  # noqa: F401
    ExecutionResult,
    get_first_coding_question,
    normalize_output,
    sanitize_filename,
    truncate_capture,
)
from .constants import (  # noqa: F401
    DOCKER_IMAGES,
    LANGUAGE_MODES,
    PISTON_FILE_NAMES,
    PISTON_LANGUAGES,
)
from .execution import _docker_available, _ensure_docker_image, clean_docker_stderr, execute_code  # noqa: F401
from .files import (  # noqa: F401
    build_starter_files,
    default_starter_code,
    execution_language_for_filename,
    file_language_for_name,
    get_main_file,
    mark_file_as_main,
    normalize_files,
    normalize_python_indentation,
    prepare_files_for_execution,
)
from .grading import grade_files_against_tests, run_visible_code  # noqa: F401
from .submission import create_final_submission, create_or_update_draft_submission, sync_submission_files  # noqa: F401

__all__ = [
    "NODE_PROMPT_POLYFILL",
    "ExecutionResult",
    "LANGUAGE_MODES",
    "build_starter_files",
    "clean_docker_stderr",
    "create_final_submission",
    "create_or_update_draft_submission",
    "default_starter_code",
    "execute_code",
    "execution_language_for_filename",
    "file_language_for_name",
    "get_first_coding_question",
    "get_main_file",
    "grade_files_against_tests",
    "mark_file_as_main",
    "normalize_files",
    "normalize_output",
    "normalize_python_indentation",
    "prepare_files_for_execution",
    "run_visible_code",
    "sanitize_filename",
    "sync_submission_files",
    "truncate_capture",
]
