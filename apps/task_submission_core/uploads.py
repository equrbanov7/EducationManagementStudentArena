from core.upload_security import randomize_uploaded_filename, validate_uploaded_file

ALLOWED_SUBMISSION_EXTENSIONS = {
    ".zip",
    ".rar",
    ".7z",
    ".pdf",
    ".txt",
    ".doc",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
}
MAX_SUBMISSION_SIZE_MB = 25


def prepare_submission_upload(uploaded_file):
    if uploaded_file is None:
        return ""

    original_file_name = uploaded_file.name
    validate_uploaded_file(
        uploaded_file,
        allowed_extensions=ALLOWED_SUBMISSION_EXTENSIONS,
        max_size_mb=MAX_SUBMISSION_SIZE_MB,
    )
    randomize_uploaded_filename(uploaded_file)
    return original_file_name
