"""Ön-giriş sessiya hovuzu — imtahan/kabinet pillələrində login yükünü ayırmaq üçün.

Real imtahan günündə tələbələr imtahandan ƏVVƏL bir pəncərədə daxil olur; login
sıçrayışının tutumu `login` pillələrində ayrıca ölçülür. Burada isə imtahanın
öz tutumunu ölçmək üçün hər tələbəyə Django `login()` ilə (parol hash-i olmadan,
eyni siqnallar/sessiya açarları ilə) sessiya yaradılır və açar fayla yazılır.
`manage.py shell -c "exec(open(PATH).read())"` ilə, test stack-in owner DB URL-i ilə.
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.db import close_old_connections
from django.http import HttpRequest

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

START = int(os.environ["CAP_SESSION_START"])
COUNT = int(os.environ["CAP_SESSION_COUNT"])
PAD = int(os.environ.get("CAP_STUDENT_PAD", "3"))
OUT = os.environ["CAP_SESSION_OUT"]
THREADS = int(os.environ.get("CAP_SESSION_THREADS", "8"))
# Verilərsə: həmin BİR hesaba COUNT sessiya (açarlar "0".."COUNT-1") — məs. imtahan
# müəllifinin paralel ixracları (export rejimi).
ONE_USER = os.environ.get("CAP_SESSION_USER", "")
User = get_user_model()
SessionStore = import_module(settings.SESSION_ENGINE).SessionStore
BACKEND = settings.AUTHENTICATION_BACKENDS[0]


def _session_for(user):
    request = HttpRequest()
    request.META["REMOTE_ADDR"] = "10.250.0.1"
    request.META["HTTP_USER_AGENT"] = "capacity-preauth"
    request.session = SessionStore()
    login(request, user, backend=BACKEND)
    request.session.save()
    return request.session.session_key


def chunk(indexes):
    close_old_connections()
    out = []
    try:
        with rls_worker_atomic(), bypass_rls():
            if ONE_USER:
                user = User.objects.get(username=ONE_USER)
                return [[i, _session_for(user)] for i in indexes]
            names = {f"stress_student_{i:0{PAD}d}": i for i in indexes}
            for user in User.objects.filter(username__in=list(names)):
                out.append([names[user.username], _session_for(user)])
    finally:
        close_old_connections()
    return out


started = time.monotonic()
indexes = list(range(0, COUNT)) if ONE_USER else list(range(START, START + COUNT))
size = 250
batches = [indexes[i : i + size] for i in range(0, len(indexes), size)]
result = {}
with ThreadPoolExecutor(max_workers=THREADS) as pool:
    for part in pool.map(chunk, batches):
        result.update({str(i): key for i, key in part})
with open(OUT, "w") as fh:
    json.dump(result, fh)
print("CAP_SESSIONS", json.dumps({"requested": COUNT, "created": len(result), "seconds": round(time.monotonic() - started, 1)}))
