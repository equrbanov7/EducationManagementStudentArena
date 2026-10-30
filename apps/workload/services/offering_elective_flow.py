"""Canonical elective synchronization, shared by ordinary and reviewed sources."""

import logging

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .offering_electives import record_group_choice

logger = logging.getLogger(__name__)


class ElectiveFlow:
    def _official_elective(self, key, entry, offering, blocks, *, lesson_hours, desired_id, eligible):
        """Rəsmi blok seçimi → qrupun qərarı (+ yoxdursa açılış). Qaytarır: qeydiyyata düşən açılış və ya ``None``."""
        group, period = entry["group"], entry["rows"][0].period
        option = self._reviewed_options.get(key) or blocks.block_for(group, key[0])
        chosen = blocks.existing_choice(group.pk, key[1], option.elective_group)
        if chosen is not None and chosen != key[0]:
            self.counters["elective_choice_conflict"] += 1
            return None
        snapshot = (dict(self.counters), len(self.offering_ids))
        try:
            with transaction.atomic():
                if offering is None:
                    offering = self._create(key, lesson_hours=lesson_hours, desired_id=desired_id, eligible=eligible)
                    if offering is None:
                        return None
                    self.counters["elective_from_task"] += 1
                if chosen is None:
                    self.counters["enrolled"] += record_group_choice(
                        organization=self.task.organization,
                        group=group,
                        period=period,
                        option=option,
                        subject=blocks.subjects[key[0]],
                        decided_by=self.actor_user,
                        preserve_existing=key in self._reviewed_options,
                    )
                    self.counters["elective_choice_recorded"] += 1
                    blocks.choices[(group.pk, key[1], option.elective_group)] = key[0]
        except (ValidationError, IntegrityError):
            logger.warning("workload: official elective choice rejected %s", key, exc_info=True)
            self.counters = snapshot[0]
            del self.offering_ids[snapshot[1] :]
            self.counters["elective_choice_failed"] += 1
            return None
        return offering
