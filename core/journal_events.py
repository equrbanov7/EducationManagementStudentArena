"""A journal write publishes accepted cell deltas synchronously inside its DB transaction."""

from django.dispatch import Signal

journal_cells_changed = Signal()
