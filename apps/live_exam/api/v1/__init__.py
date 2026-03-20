"""
apps/live_exam/api/v1/__init__.py

Version 1 of the Live Exam REST API.

All endpoints in this package are mounted under the ``/api/v1/live/``
prefix and respond with JSON.  Consumers should use this prefix in all
HTTP calls so that future breaking changes can be introduced under ``/api/v2/``
without affecting v1 clients.

Versioning contract
-------------------
* New **non-breaking** additions (new optional response fields, new optional
  query parameters) may be added without a version bump.
* **Breaking** changes (removed fields, changed semantics, new required params)
  must be introduced under a new ``/api/v2/`` mount while keeping ``/api/v1/``
  working for a deprecation period.

Current endpoints
-----------------
GET  /api/v1/live/<pin>/state/     – live session state (rate-limited)
"""
