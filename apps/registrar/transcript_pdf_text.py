"""Transkript PDF-i üçün ÖLÇÜLƏRƏK sətirə bölmə (2026-09-11).

Sahib: «transkriptdə bəzi yazılar üst-üstə düşür — uzun olanda alt sətrə keçsin».

Nə səhv idi
-----------
Fənn adı `int(width / 4.4)` SİMVOL sayı ilə kəsilirdi, tələbə blokunda isə
sabit 40 simvol.  Simvol sayı piksel eni deyil: «ə», «ü», «ş» kimi enli
qliflərlə dolu azərbaycanca ad eyni simvol sayında xeyli enli olur, kod
prefiksi («MYEDU-L1915») isə limitə ümumiyyətlə daxil deyildi.  Nəticə —
mətn qonşu sütunun («Kredit», «Tələbə №») üstünə minirdi.  Üstəlik kəsmə
RƏSMİ sənəddə məlumat itirirdi («…köhnə 050…»).

İndi
----
Mətn şriftlə ÖLÇÜLÜB sözbəsöz sətirlərə bölünür; sığmayan tək söz simvolla
qırılır.  Heç nə kəsilmir, heç nə qonşu sütuna keçmir — sətir sadəcə
hündürlənir.  Ölçmə `transcript_pdf._text_width` ilə eynidir (eyni şrift
faylı), ona görə çəkilən nəticə hesablanandan fərqlənmir.
"""

from __future__ import annotations

from collections.abc import Callable

#: Bir sətrin hündürlüyü (pt) — şrift ölçüsünə nisbətlə.
LINE_FACTOR = 1.28


def line_height(size: float) -> float:
    return round(size * LINE_FACTOR, 2)


def wrap_lines(value: str, *, width: float, measure: Callable[[str], float]) -> list[str]:
    """``value``-nu ``width`` (pt) içinə sığan sətirlərə bölür.

    ``measure(text) -> pt`` çağıran tərəfin şrift/ölçü ilə bağladığı ölçü
    funksiyasıdır.  Boş mətn → ``[""]`` (bir boş sətir: hündürlük hesabı
    sıfıra düşməsin).
    """
    text = " ".join(str(value or "").split())
    if not text:
        return [""]
    if measure(text) <= width:
        return [text]

    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = f"{current} {word}" if current else word
        if measure(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        # Söz TƏK BAŞINA sığmırsa — simvolla qırılır (uzun kod/URL halı).
        if measure(word) <= width:
            current = word
            continue
        chunk = ""
        for char in word:
            if measure(chunk + char) <= width or not chunk:
                chunk += char
            else:
                lines.append(chunk)
                chunk = char
        current = chunk
    if current:
        lines.append(current)
    return lines or [""]


#: Fənn sətri: tək xətt 12pt ritmini saxlayır; hər əlavə xətt bir sətir hündürlüyü artırır.
ROW_SIZE = 7.6
ROW_LINE_H = line_height(ROW_SIZE)


def row_height(line_count: int) -> float:
    return 12 + (max(1, line_count) - 1) * ROW_LINE_H


__all__ = ["LINE_FACTOR", "ROW_LINE_H", "ROW_SIZE", "line_height", "row_height", "wrap_lines"]
