# exam/validators.py

import os
import zipfile
from django.core.exceptions import ValidationError

# İcazə verilən fayl tipləri
ALLOWED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg', '.zip']

# Bloklanan (virus riskli) fayl tipləri
BLOCKED_EXTENSIONS = [
    '.exe', '.js', '.sh', '.bat', '.cmd', '.msi',
    '.php', '.html', '.htm', '.py', '.rb'
]

def validate_file_extension(file):
    ext = os.path.splitext(file.name)[1].lower()

    if ext in BLOCKED_EXTENSIONS:
        raise ValidationError("Bu tip fayl təhlükəli ola bilər və yüklənməsi qadağandır.")

    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError("Bu fayl tipi icazəli deyil. Yalnız PDF, JPG, PNG, ZIP.")

def validate_file_size(file):
    max_size = 10 * 1024 * 1024  # 10 MB

    if file.size > max_size:
        raise ValidationError("Fayl maksimum 10MB ola bilər.")

def validate_zip_contents(file):
    ext = os.path.splitext(file.name)[1].lower()

    if ext != ".zip":
        return  # ZIP deyilsə, çıxırıq

    try:
        zip_file = zipfile.ZipFile(file)
    except zipfile.BadZipFile:
        raise ValidationError("ZIP faylı zədəlidir və açıla bilmədi.")

    for info in zip_file.infolist():
        inner_ext = os.path.splitext(info.filename)[1].lower()

        # ZIP içində qovluq varsa, keçirik (çünki .ext olmur)
        if not inner_ext:
            continue

        if inner_ext in BLOCKED_EXTENSIONS:
            raise ValidationError(
                f"ZIP içində təhlükəli fayl aşkarlandı: {info.filename}"
            )