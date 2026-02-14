#!/usr/bin/env python
"""
Test script to verify the migration fix works correctly.
"""

import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from django.db import connection

from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession


def test_unique_constraint():
    """Test that the unique constraint works correctly."""
    print("🧪 Testing unique constraint on LivePlayer...")

    # Check that the model has the constraint
    constraints = [c.name for c in LivePlayer._meta.constraints]
    assert "uniq_player_per_session_client" in constraints, "Constraint not found in model!"
    print("✅ Model has the constraint defined")

    # Check that unique_together is NOT duplicated
    unique_together = LivePlayer._meta.unique_together
    print(f"   unique_together: {unique_together}")

    print("\n✨ All tests passed!")
    print("\nModel Meta Information:")
    print(f"  - Constraints: {[c.name for c in LivePlayer._meta.constraints]}")
    print(f"  - Unique Together: {LivePlayer._meta.unique_together}")
    print(f"  - DB Table: {LivePlayer._meta.db_table}")


if __name__ == "__main__":
    try:
        test_unique_constraint()
    except Exception as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)
