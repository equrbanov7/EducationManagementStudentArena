"""Thirteen reviewed Source28 history rows; no resource-prefix or date-wide exemption.

Full immutable bytes pin one Sep5 empty/zero-mark cleanup, one official
vacant-fill allocation, and eleven positive Oct26 grade events. None affects
the fixed Oct29 PRESENT slot. Unknown/later/changed history remains a HOLD.
"""

from . import reviewed_content_28_spec as fixed
from .reviewed_content_contract import ContentError
from .reviewed_content_spec import ORG
from .reviewed_content_state import digest

REVIEW_EVIDENCE_SHA = "78a1c88b7a3459dcaea37aff2d2509d3285c4171d8df3be2b16df8b32c139ee5"
PINS = {
    "0fc41650-8906-445a-9142-46840ca432eb": {
        "action": "update",
        "change_count": 1,
        "changes_sha256": "57200077ca328c1e9bf89c060aad37733662b258c2fc5e262b9d15804dfc3154",
        "classification": "teacher_positive_other_day_2026_10_26",
        "new_values_sha256": "6aea6dfe6561984cdc5c54ead84d47d2cf29e48253ae282aef237404adad4661",
        "old_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "raw_record_sha256": "7a0ea38ce6adad803f6b7734b5771e21d32aedff0b54df5c1efb2530d5f09d38",
        "resource_id": "1aca3f3c-5677-494e-af12-5622d2c1ea0a",
        "resource_id_sha256": "91331c248bad5f89a94abab799b62a86b823eb515a380b86a1077e4ab073a691",
        "resource_kind": "registrar.grade.mark",
        "resource_kind_sha256": "868e6d8794c9690d1633f68567183ad1057dc9ca670a384acccbfc28ee315617",
        "user_id": 8149,
    },
    "51f831fb-bdb3-42b1-ad31-7499c94a24d3": {
        "action": "update",
        "change_count": 1,
        "changes_sha256": "132a729afd51046d360d34b452c239fa31715fe82001c15f68fdcd8e3be16104",
        "classification": "teacher_positive_other_day_2026_10_26",
        "new_values_sha256": "6aea6dfe6561984cdc5c54ead84d47d2cf29e48253ae282aef237404adad4661",
        "old_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "raw_record_sha256": "8e91933f3dce20d22cdd7898e45b733a72f3c6bd5e67ebe1eaccf7219ab5edbc",
        "resource_id": "1aca3f3c-5677-494e-af12-5622d2c1ea0a",
        "resource_id_sha256": "91331c248bad5f89a94abab799b62a86b823eb515a380b86a1077e4ab073a691",
        "resource_kind": "registrar.grade.mark",
        "resource_kind_sha256": "868e6d8794c9690d1633f68567183ad1057dc9ca670a384acccbfc28ee315617",
        "user_id": 8149,
    },
    "6835e55b-1049-431b-bb29-05c97eea27de": {
        "action": "update",
        "change_count": 1,
        "changes_sha256": "9ddff87d02644594af0d4b3bf9a6241b8aeb1a944c2b38fe624f5a7eb80541f7",
        "classification": "teacher_positive_other_day_2026_10_26",
        "new_values_sha256": "6aea6dfe6561984cdc5c54ead84d47d2cf29e48253ae282aef237404adad4661",
        "old_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "raw_record_sha256": "dc5aa28d876c256167ffc2366ffa5ef953700ab72dc9c75daa16e6a042d5674b",
        "resource_id": "1aca3f3c-5677-494e-af12-5622d2c1ea0a",
        "resource_id_sha256": "91331c248bad5f89a94abab799b62a86b823eb515a380b86a1077e4ab073a691",
        "resource_kind": "registrar.grade.mark",
        "resource_kind_sha256": "868e6d8794c9690d1633f68567183ad1057dc9ca670a384acccbfc28ee315617",
        "user_id": 8149,
    },
    "8910fc18-9d2c-49c7-b950-11dedc25a720": {
        "action": "update",
        "change_count": 1,
        "changes_sha256": "47a1c2a9093bb2ff980256bd53badd327670810769dda17e626d1e349411f32e",
        "classification": "teacher_positive_other_day_2026_10_26",
        "new_values_sha256": "6aea6dfe6561984cdc5c54ead84d47d2cf29e48253ae282aef237404adad4661",
        "old_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "raw_record_sha256": "6a4fa4bc7cf0568e3d770149e922ee050eee822de8fdf6ecc636bd20c16e1ae5",
        "resource_id": "1aca3f3c-5677-494e-af12-5622d2c1ea0a",
        "resource_id_sha256": "91331c248bad5f89a94abab799b62a86b823eb515a380b86a1077e4ab073a691",
        "resource_kind": "registrar.grade.mark",
        "resource_kind_sha256": "868e6d8794c9690d1633f68567183ad1057dc9ca670a384acccbfc28ee315617",
        "user_id": 8149,
    },
    "9df22bec-90ed-42d4-b1ed-b68d7e18eaac": {
        "action": "update",
        "change_count": 1,
        "changes_sha256": "7ebbe997c7b619632ba3544566e0dd90943e87a5471c78247b4019785e2d41e5",
        "classification": "teacher_positive_other_day_2026_10_26",
        "new_values_sha256": "6aea6dfe6561984cdc5c54ead84d47d2cf29e48253ae282aef237404adad4661",
        "old_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "raw_record_sha256": "5f3b8d25181360b814183534f299742f62e0055adcc9f8e4ae6e20641d3745f0",
        "resource_id": "1aca3f3c-5677-494e-af12-5622d2c1ea0a",
        "resource_id_sha256": "91331c248bad5f89a94abab799b62a86b823eb515a380b86a1077e4ab073a691",
        "resource_kind": "registrar.grade.mark",
        "resource_kind_sha256": "868e6d8794c9690d1633f68567183ad1057dc9ca670a384acccbfc28ee315617",
        "user_id": 8149,
    },
    "ac33f43f-6969-4c99-b267-2dffa208b844": {
        "action": "update",
        "change_count": 1,
        "changes_sha256": "d69a2ccbf08b300e5022eef4fd97c947b2f88a4aa187ad72bffb123c7e8a6904",
        "classification": "teacher_positive_other_day_2026_10_26",
        "new_values_sha256": "6aea6dfe6561984cdc5c54ead84d47d2cf29e48253ae282aef237404adad4661",
        "old_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "raw_record_sha256": "9ec1e0387bafeff1d77c906c194d7d16039a6ae1e11248ea9faf141f34c0040a",
        "resource_id": "1aca3f3c-5677-494e-af12-5622d2c1ea0a",
        "resource_id_sha256": "91331c248bad5f89a94abab799b62a86b823eb515a380b86a1077e4ab073a691",
        "resource_kind": "registrar.grade.mark",
        "resource_kind_sha256": "868e6d8794c9690d1633f68567183ad1057dc9ca670a384acccbfc28ee315617",
        "user_id": 8149,
    },
    "b239c78e-1ef4-47ff-a7ba-3c5184fbbed7": {
        "action": "update",
        "change_count": 1,
        "changes_sha256": "5913ab700da50c8fff1867d7e84fedda95d43769f443a64e957889b29ae6ff50",
        "classification": "teacher_positive_other_day_2026_10_26",
        "new_values_sha256": "6aea6dfe6561984cdc5c54ead84d47d2cf29e48253ae282aef237404adad4661",
        "old_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "raw_record_sha256": "98e40a72e1a2ec3e3423189d55e373dc65c3d4df47ff31cddd4707a46d0880d5",
        "resource_id": "1aca3f3c-5677-494e-af12-5622d2c1ea0a",
        "resource_id_sha256": "91331c248bad5f89a94abab799b62a86b823eb515a380b86a1077e4ab073a691",
        "resource_kind": "registrar.grade.mark",
        "resource_kind_sha256": "868e6d8794c9690d1633f68567183ad1057dc9ca670a384acccbfc28ee315617",
        "user_id": 8149,
    },
    "ba2208b2-f4e3-4eff-9272-367792a57f83": {
        "action": "update",
        "change_count": 1,
        "changes_sha256": "d0393d0650f1f40816fe51c48bb6017e0f4755692017d36c458c96b94efe0876",
        "classification": "teacher_positive_other_day_2026_10_26",
        "new_values_sha256": "6aea6dfe6561984cdc5c54ead84d47d2cf29e48253ae282aef237404adad4661",
        "old_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "raw_record_sha256": "71a70089acae64296f68b5eb1c935ad2f7c724354ef0e531c97bdf6133a16218",
        "resource_id": "1aca3f3c-5677-494e-af12-5622d2c1ea0a",
        "resource_id_sha256": "91331c248bad5f89a94abab799b62a86b823eb515a380b86a1077e4ab073a691",
        "resource_kind": "registrar.grade.mark",
        "resource_kind_sha256": "868e6d8794c9690d1633f68567183ad1057dc9ca670a384acccbfc28ee315617",
        "user_id": 8149,
    },
    "bb644242-7f44-4d1b-a692-adccd54b8198": {
        "action": "update",
        "change_count": 1,
        "changes_sha256": "e10585dd5338611d8c75d014b4480e5fce4231a90af8455889167987a081a1dc",
        "classification": "teacher_positive_other_day_2026_10_26",
        "new_values_sha256": "6aea6dfe6561984cdc5c54ead84d47d2cf29e48253ae282aef237404adad4661",
        "old_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "raw_record_sha256": "5c9e0ed325374bc0f98537c3d7f1fc4a5787766769ad879773083ab6c0802628",
        "resource_id": "1aca3f3c-5677-494e-af12-5622d2c1ea0a",
        "resource_id_sha256": "91331c248bad5f89a94abab799b62a86b823eb515a380b86a1077e4ab073a691",
        "resource_kind": "registrar.grade.mark",
        "resource_kind_sha256": "868e6d8794c9690d1633f68567183ad1057dc9ca670a384acccbfc28ee315617",
        "user_id": 8149,
    },
    "d08f62b0-f2ab-468d-87d3-7d2a17388691": {
        "action": "update",
        "change_count": 29,
        "changes_sha256": "27781af7092ce1dba6e214bc4a641416c1c8b7718d6ba8b0902277a1c5b53b51",
        "classification": "teacher_positive_other_day_2026_10_26",
        "new_values_sha256": "f2715110bf46132c4555c9aa8eafcb4d7c58740623ed89681655c25fbd69581f",
        "old_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "raw_record_sha256": "100d70054b05c679db26efb1cf261af7183c7e5324c5b75007d14fcdc8d8b7fc",
        "resource_id": "1aca3f3c-5677-494e-af12-5622d2c1ea0a",
        "resource_id_sha256": "91331c248bad5f89a94abab799b62a86b823eb515a380b86a1077e4ab073a691",
        "resource_kind": "registrar.grade.mark",
        "resource_kind_sha256": "868e6d8794c9690d1633f68567183ad1057dc9ca670a384acccbfc28ee315617",
        "user_id": 8149,
    },
    "ea9333dc-c64d-4a56-9c8a-366ff52124d2": {
        "action": "update",
        "change_count": 1,
        "changes_sha256": "08096f6ad03c1baf97027c75a425e06b862065eeb6105660c5129d74b6899558",
        "classification": "teacher_positive_other_day_2026_10_26",
        "new_values_sha256": "6aea6dfe6561984cdc5c54ead84d47d2cf29e48253ae282aef237404adad4661",
        "old_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "raw_record_sha256": "48b28f540062491b4972407abbffa18a6fba32863bf646b3c1ad871a23334c8d",
        "resource_id": "1aca3f3c-5677-494e-af12-5622d2c1ea0a",
        "resource_id_sha256": "91331c248bad5f89a94abab799b62a86b823eb515a380b86a1077e4ab073a691",
        "resource_kind": "registrar.grade.mark",
        "resource_kind_sha256": "868e6d8794c9690d1633f68567183ad1057dc9ca670a384acccbfc28ee315617",
        "user_id": 8149,
    },
    "f36a51a2-c05c-4f7c-b10b-089def9188c4": {
        "action": "update",
        "change_count": 0,
        "changes_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "classification": "released_vacantfill_allocation",
        "new_values_sha256": "eaf1bbfade031f13f8798afb3b98a943f8e0361a729dbe99dc873f77d3fdf1b5",
        "old_values_sha256": "ed483a3dcfd7300ee528a9fa2c5db70541f6cdf64b3a95199b1a1d145a898a25",
        "raw_record_sha256": "8cfd0806d46785512264e07617484aee389d232d127177d714592249d581e907",
        "resource_id": None,
        "resource_id_sha256": "1b8c0a1c9a991731b13229dcb8ec27d2ba4afe1e1917be01183997edb0514b12",
        "resource_kind": "other",
        "resource_kind_sha256": "075c092204414a121d16913d76e26205c54e72b7859cc1437d847fcb5102cbde",
        "user_id": 8444,
    },
    "fae64b4a-88cb-4277-a9a6-5e9bba5f185f": {
        "action": "delete",
        "change_count": 0,
        "changes_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "classification": "empty_september_column_zero_marks",
        "new_values_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",
        "old_values_sha256": "6a244741c258d1b4514fa3eaab55e1ef5363cc71c2f0d250fd8db4b681fc8304",
        "raw_record_sha256": "07436cf86d62ffc4d73acdcf4fa47aac5910d08a79efa5d53aabf9d3a788ffef",
        "resource_id": "1aca3f3c-5677-494e-af12-5622d2c1ea0a",
        "resource_id_sha256": "91331c248bad5f89a94abab799b62a86b823eb515a380b86a1077e4ab073a691",
        "resource_kind": "other",
        "resource_kind_sha256": "27cf0f6c56ed36d5a268fce7d74a6b0f08b3242a84e19e7cdf97f69cab27fe5c",
        "user_id": 8444,
    },
}


def _scope(data):
    raw = {k: v for k, v in data.items() if k not in {"selected_target_ids", "until_date"}}
    return bool(
        data.get("selected_target_ids") == [fixed.TARGET]
        and digest(raw) == fixed.PAYLOAD_DIGEST
        and {p["id"] for p in data.get("points", [])} == set(fixed.CASES)
        and all(p["point"] == "ie" and str(p["sem_muh"]) == "0" and not int(p["lab"]) for p in data["points"])
        and all(c["date"] == "2026-10-29" and c["kind"] == "seminar" for c in fixed.CASES.values())
    )


def permits(row, data):
    """Only server-produced complete row hashes and fixed Source28 payload authorize classification."""
    pin = PINS.get(row.get("id"))
    if (
        pin is None
        or pin.get("classification")
        not in {
            "empty_september_column_zero_marks",
            "released_vacantfill_allocation",
            "teacher_positive_other_day_2026_10_26",
        }
        or not _scope(data)
    ):
        return False
    expected_cases = sorted(fixed.CASES) if pin["classification"] == "empty_september_column_zero_marks" else []
    return bool(
        row.get("organization_id") == ORG
        and all(row.get(k) == v for k, v in pin.items() if k not in {"classification", "change_count"})
        and row.get("case_ids") == expected_cases
        and row.get("contrary_clear_evidence") is False
        and row.get("contrary_delete_evidence") is (pin["classification"] == "empty_september_column_zero_marks")
        and row.get("unresolved_scope_row") is (pin["classification"] != "empty_september_column_zero_marks")
        and row.get("malformed_intent") is False
        and row.get("source_undo_marker") is False
        and row.get("reason_present") is True
    )


def classify(rows, data):
    """Every reviewed anchor must still exist byte-for-byte; retain all original evidence flags."""
    if not _scope(data):
        raise ContentError("reviewed_source28_reviewed_history_fixed_scope_required")
    matched = [r for r in rows if r["id"] in PINS]
    found = {r["id"]: r for r in matched}
    if set(found) != set(PINS):
        raise ContentError("reviewed_source28_reviewed_history_anchor_missing")
    if len(matched) != len(found) or not all(permits(row, data) for row in found.values()):
        raise ContentError("reviewed_source28_reviewed_history_anchor_changed")
    return {
        key: {
            "audit_id": key,
            "raw_record_sha256": found[key]["raw_record_sha256"],
            "classification": PINS[key]["classification"],
            "change_count": PINS[key]["change_count"],
            "review_evidence_sha256": REVIEW_EVIDENCE_SHA,
        }
        for key in sorted(found)
    }
