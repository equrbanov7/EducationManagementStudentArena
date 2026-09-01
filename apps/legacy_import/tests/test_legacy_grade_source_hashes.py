"""Read-only grade source hash yenidən-hesablama testləri."""

import datetime

from apps.legacy_import.services.legacy_grade_field_contracts import EXAM_ENTRY_EXIT_FIELDS
from apps.legacy_import.services.rehearsal_contracts import source_row_hash
from scripts.legacy_reconcile.grade_source_hashes import collect_source_grade_hashes
from scripts.legacy_reconcile.transport import assert_read_only


class FakeSource:
    def __init__(self):
        self.queries = []

    def query(self, label, sql):
        self.queries.append((label, sql))
        assert_read_only(sql)
        if label.startswith("yekun"):
            return [[1, 101, 64, 2, "39", "32", "71", 4, 0, 0, 1, 0]]
        if label.startswith("journals_dates_points_archive"):
            return [
                [
                    3,
                    "journal-x",
                    "im2",
                    "0",
                    101,
                    "49",
                    "2022-01-01 10:00:00",
                    "14:00:00",
                    0,
                    "",
                    "NULL",
                    0,
                    0,
                    "NULL",
                    0,
                    "NULL",
                ]
            ]
        if label.startswith("journals_dates_points"):
            return [
                [
                    2,
                    "journal-x",
                    "im",
                    "0",
                    101,
                    "45",
                    "2022-01-01 10:00:00",
                    "14:00:00",
                    0,
                    "",
                    2,
                    0,
                    0,
                    "",
                    0,
                    "2022-01-01 11:00:00",
                ]
            ]
        if label.startswith("imthngrscxsblr"):
            return [[4, 101, 64, 3010, 2437, 3, "2022-04-01 09:00:00"]]
        raise AssertionError(label)


def test_every_grade_source_contract_hash_is_recomputed_with_typed_values():
    source = FakeSource()

    hashes = collect_source_grade_hashes(source)

    assert set(hashes) == {
        ("yekun", 1),
        ("journals_dates_points", 2),
        ("journals_dates_points_archive", 3),
        ("imthngrscxsblr", 4),
    }
    assert all(len(value) == 64 for value in hashes.values())
    attempt = {
        "id": 4,
        "student_id": 101,
        "lesson_id": 64,
        "giris_point": 3010,
        "cixis_point": 2437,
        "type": 3,
        "added_date": datetime.datetime(2022, 4, 1, 9, 0),
    }
    assert hashes[("imthngrscxsblr", 4)] == source_row_hash(
        contract=EXAM_ENTRY_EXIT_FIELDS,
        legacy_pk=4,
        projected_row=attempt,
    )
    assert len(source.queries) == 4


def test_selected_j12_calendar_hash_is_fetched_without_scanning_all_calendar_rows():
    class ExtraSource(FakeSource):
        def query(self, label, sql):
            if "seçilmiş J12" in label:
                self.queries.append((label, sql))
                assert_read_only(sql)
                assert "WHERE id IN (5)" in sql
                return [
                    [
                        5,
                        "journal-x",
                        "03",
                        "9",
                        101,
                        "7",
                        "2022-01-01 10:00:00",
                        "14:00:00",
                        0,
                        "",
                        2,
                        0,
                        0,
                        "",
                        0,
                        "2022-01-01 11:00:00",
                    ]
                ]
            return super().query(label, sql)

    source = ExtraSource()
    hashes = collect_source_grade_hashes(
        source,
        extra_keys={("journals_dates_points", 5)},
    )

    assert ("journals_dates_points", 5) in hashes
    assert len(source.queries) == 5
