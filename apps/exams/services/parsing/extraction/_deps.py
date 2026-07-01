"""extraction paketi — opsional (pypdf, PyMuPDF) importlar bir yerdə."""

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    import fitz
except ImportError:
    fitz = None
