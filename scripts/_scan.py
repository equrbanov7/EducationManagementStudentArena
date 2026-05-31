import glob
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AZ = re.compile(r"[ƏəĞğÖöÜüÇçŞşİ]")
# count remaining hardcoded AZ literals (outside trans tags) per template
rows = []
for f in glob.glob(os.path.join(BASE, "apps", "*", "templates", "**", "*.html"), recursive=True) + glob.glob(
    os.path.join(BASE, "templates", "**", "*.html"), recursive=True
):
    if "/venv/" in f:
        continue
    n = 0
    for line in open(f, encoding="utf-8"):
        if "context '" in line or 'context "' in line:
            # strip trans tags then check
            stripped = re.sub(r"\{%.*?%\}", "", line)
            if AZ.search(stripped):
                n += 1
        elif AZ.search(line):
            n += 1
    if n:
        rows.append((n, os.path.relpath(f, BASE)))
rows.sort(reverse=True)
out = ["TOTAL files with leftover AZ: %d" % len(rows), "TOTAL leftover lines: %d" % sum(r[0] for r in rows), ""]
out += ["%4d  %s" % (n, p) for n, p in rows]
open(os.path.join(BASE, "scripts", "_scan_out.txt"), "w", encoding="utf-8").write("\n".join(out))
print("done")
