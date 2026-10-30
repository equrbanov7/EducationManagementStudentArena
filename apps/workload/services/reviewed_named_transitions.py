"""Exact source-backed corrections for twelve reviewed named workload rows.

These pins cannot confer arbitrary ownership: normal tenant, source identity,
assignment and complete academic-fingerprint guards still run before writes.
"""

from .sbio235_state import RepairError

PINS = {
    "502cfe57-2781-42d0-b5f9-f480d95401fa": {
        "source_sha": "99f45965b5bf00579e0a84e9845131393452666a2ecb0f2e6723baafb6d1418c",
        "source_line": 63,
        "teacher": 8429,
        "totals": {"lecture": 30, "seminar": 30, "lab": 0},
        "groups": ["4bbfa907-90ec-4439-81c7-29df5c7656c9"],
        "journals": ["f90ca270-3279-43c3-83fe-c2ae27d7b574"],
        "old_owners": [8429],
        "unowned": False,
    },
    "f5e11e9e-8b20-46d9-a54d-35926e2a6344": {
        "source_sha": "57f0fdb5babaa7ab693c5623426982ac268a84691702fac6b68610f567bd3f9d",
        "source_line": 7,
        "teacher": 7847,
        "totals": {"lecture": 30, "seminar": 0, "lab": 0},
        "groups": ["73668610-5489-4af2-972b-1c6d7668f216"],
        "journals": ["1098c530-c934-43ff-96fa-cf6a4aa5d450"],
        "old_owners": [7847],
        "unowned": False,
    },
    "2c141438-7064-4a0b-b3f6-0f5b45f5899b": {
        "source_sha": "5e5bb05a993956c0519e0b5fc0e72548391de44b110f8460cb2ed7ca9493314d",
        "source_line": 77,
        "teacher": 8391,
        "totals": {"lecture": 30, "seminar": 15, "lab": 0},
        "groups": ["4c8e770a-f2a1-4db4-8337-6bbe4505e6d4"],
        "journals": ["83452cab-9bc4-4168-acc0-eedc971b3485"],
        "old_owners": [None, 8391],
        "unowned": False,
    },
    "33d151a6-f636-4dc7-b380-e8befdd094dc": {
        "source_sha": "5e5bb05a993956c0519e0b5fc0e72548391de44b110f8460cb2ed7ca9493314d",
        "source_line": 56,
        "teacher": 7723,
        "totals": {"lecture": 15, "seminar": 30, "lab": 0},
        "groups": ["0a712bea-10b2-4a42-abc8-9acde96e3134", "694c4117-3871-4d66-b8a9-802abe4a52b9"],
        "journals": ["6c6a7276-958b-4f6e-8231-94f66a41e837", "e6eb947a-b498-4eca-823f-0fbfd746ed6b"],
        "old_owners": [None],
        "unowned": True,
    },
    "f4c1e73f-5174-4032-a9d4-d40c0ac6406b": {
        "source_sha": "5e5bb05a993956c0519e0b5fc0e72548391de44b110f8460cb2ed7ca9493314d",
        "source_line": 62,
        "teacher": 7723,
        "totals": {"lecture": 15, "seminar": 30, "lab": 0},
        "groups": ["5d343cf9-cfb3-4b74-8bef-5cd1e08d8a63", "75fba3b9-bca9-4f5d-8e8b-be2b3eb0223f"],
        "journals": ["8cbb37d4-7c9b-40df-8cd4-dae9ec27bbd8", "ed75cc7f-2634-457b-bad9-f1897afea895"],
        "old_owners": [None],
        "unowned": True,
    },
    "02ef32f9-0f3a-484b-8ebb-e71a4f93d088": {
        "groups": ["436536bc-91cf-4bad-b854-17e59859efe1"],
        "journals": ["7f30c5fb-aaca-4ed6-8e24-23cad8e43b1d"],
        "old_owners": [None],
        "source_line": 79,
        "source_sha": "5e5bb05a993956c0519e0b5fc0e72548391de44b110f8460cb2ed7ca9493314d",
        "teacher": 8391,
        "totals": {"lab": 0, "lecture": 30, "seminar": 15},
        "unowned": True,
    },
    "cd201de8-46a8-4f1d-bd78-cf07d7ea8f86": {
        "source_sha": "99f45965b5bf00579e0a84e9845131393452666a2ecb0f2e6723baafb6d1418c",
        "source_line": 41,
        "teacher": 8348,
        "totals": {"lecture": 30, "seminar": 15, "lab": 0},
        "groups": ["2618b6dc-1ebf-49c0-8e26-337421d7550f"],
        "journals": ["95e6a7d0-5c91-4a96-8b7a-cbd1e43a8510"],
        "old_owners": [8348],
        "unowned": False,
    },
    "a0b27e4d-ca93-4101-bd1f-22c923bd47d4": {
        "source_sha": "99f45965b5bf00579e0a84e9845131393452666a2ecb0f2e6723baafb6d1418c",
        "source_line": 89,
        "teacher": 9548,
        "totals": {"lecture": 30, "seminar": 30, "lab": 0},
        "groups": ["ab21a8e2-beab-4bd8-9700-531c602a0556"],
        "journals": ["0b4c29b4-6a3d-491f-951d-32f589eda37d"],
        "old_owners": [9548],
        "unowned": False,
    },
    "8207e13d-d046-4bd4-bfc2-6889ba4637e1": {
        "source_sha": "57f0fdb5babaa7ab693c5623426982ac268a84691702fac6b68610f567bd3f9d",
        "source_line": 47,
        "teacher": 7885,
        "totals": {"lecture": 60, "seminar": 0, "lab": 0},
        "groups": ["4e5ad122-f2a9-4685-9fcb-45f4f9e05d4c"],
        "journals": ["86236c69-0011-46e3-88a4-0e5124290d0f"],
        "old_owners": [7885],
        "unowned": False,
    },
    "ced79a5a-d4d7-48d0-93b5-57df9825c200": {
        "source_sha": "38c3ed762cc25426e8966006432928525a9e66f58605c6d506ed93557e9f60da",
        "source_line": 19,
        "teacher": 7942,
        "totals": {"lecture": 0, "seminar": 30, "lab": 0},
        "groups": ["2b5f29de-6fc3-40d4-866f-e177fb5cf070"],
        "journals": ["aea5d4cf-1f7c-4cd9-a2a6-ca839abeac43"],
        "old_owners": [7942],
        "unowned": False,
    },
    "7df5f2ce-a280-4c4c-bb41-362777006a19": {
        "source_sha": "38c3ed762cc25426e8966006432928525a9e66f58605c6d506ed93557e9f60da",
        "source_line": 27,
        "teacher": 7942,
        "totals": {"lecture": 0, "seminar": 30, "lab": 0},
        "groups": ["9d1b56cf-0a24-4fb2-9be0-4eed5b979d61"],
        "journals": ["41ff13ba-694d-4601-be6c-b12a5959a422"],
        "old_owners": [7942],
        "unowned": False,
    },
    "b4deca53-3d82-492f-b4e3-0160ed865960": {
        "source_sha": "1c6df8cae8632609e5b13e791afd207095258fdafe28925393770019f226f92d",
        "source_line": 79,
        "teacher": 7850,
        "totals": {"lecture": 45, "seminar": 0, "lab": 0},
        "groups": ["390c5966-36d1-4032-bb97-7e1de0acc397", "cd3fe4ff-c3dc-44be-a5a1-7d43dc37325c"],
        "journals": ["5c2881b0-568d-4889-81db-bcbf01bf8f27", "b9ca698e-0eed-44a3-afc9-722682826973"],
        "old_owners": [7850],
        "unowned": False,
    },
}


def attach(item):
    pin = PINS.get(item["row_id"])
    if not pin:
        return
    if (
        item["source_sha"] != pin["source_sha"]
        or item["source_line"] != pin["source_line"]
        or item["mode"] != "patch"
        or item["totals"] != pin["totals"]
        or item["group_ids"] != pin["groups"]
        or sorted(j["id"] for j in item["existing_journals"]) != pin["journals"]
        or {a["teacher_id"] for a in item["assignments"]} != {pin["teacher"]}
        or {a["teacher_id"] for a in item["existing_rows"][0]["assignments"]} != set(pin["old_owners"])
        or {h["offering_id"] for h in item["policy"].get("legacy_history", [])} != set(pin["journals"])
    ):
        raise RepairError("named_source_transition_identity_changed")
    item["policy"]["named_transition"] = pin


def policy(item):
    return item.get("policy", {}).get("named_transition")


def prepare_assignments(row, item, *, actor):
    from .assignments import unassign
    from .reviewed_batch_actions import assign

    pin = policy(item)
    expected = {a["activity"]: a for a in item["assignments"]}
    for old in list(row.assignments.filter(activity__in=("lecture", "seminar", "lab"))):
        if old.teacher_id not in pin["old_owners"]:
            raise RepairError("named_source_assignment_owner_changed")
        desired = expected.get(old.activity)
        if desired is None:
            unassign(assignment=old, actor=actor, sync_offerings=False)
        elif old.teacher_id is None:
            assign(row, {**desired, "hours": min(old.hours, desired["hours"])}, actor=actor, old=old)


def owner_targets(plan):
    return {
        pk: pin["teacher"] for item in plan.items if (pin := policy(item)) and pin["unowned"] for pk in pin["journals"]
    }
