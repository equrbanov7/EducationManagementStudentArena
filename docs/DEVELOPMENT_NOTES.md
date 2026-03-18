# Development Notes

- Always verify package versions inside the project virtual environment with `venv/bin/python -m ...` or `venv/bin/pip ...`.
- This project currently uses `Django==5.2.8` inside the local `venv`.
- This project currently uses `django-csp==4.0` from the local `venv`, not the system Python.
- CSP settings follow the `CONTENT_SECURITY_POLICY = {"DIRECTIVES": ...}` format required by `django-csp` 4.x.
- Bootstrap and Font Awesome are served from the local `static/vendor/` directory, not from a CDN.
