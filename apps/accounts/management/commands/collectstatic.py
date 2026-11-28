"""Purge the retired FAQ subtree on existing static volumes, including hashed copies."""

import shutil
from pathlib import Path

from django.contrib.staticfiles.management.commands.collectstatic import Command as CollectStatic


class Command(CollectStatic):
    def collect(self):
        self.ignore_patterns.append("accounts/faq")
        if not self.dry_run and self.is_local_storage():
            retired = Path(self.storage.path("accounts/faq"))
            if retired.parent.is_symlink():
                raise OSError("The collected accounts asset directory must not be a symlink.")
            if retired.is_symlink():
                retired.unlink()
            elif retired.is_dir():
                shutil.rmtree(retired)
        return super().collect()
