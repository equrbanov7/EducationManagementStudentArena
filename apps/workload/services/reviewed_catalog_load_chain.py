"""Exactly two official contexts then Vefa fallback, one all-or-nothing transaction."""

import uuid

from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from . import reviewed_two_catalog_repair as core
from . import reviewed_two_catalog_spec as two
from . import reviewed_vefa_catalog_spec as vefa
from .reviewed_leyla_catalog_graph import digest, model, require

RESOURCE = "workload.reviewed_catalog_load_chain_v1"
STAGES = (("two_catalog", two, core.RESOURCE), ("vefa_catalog", vefa, vefa.RESOURCE))


def _states(organization, actor):
    return {
        name: core.run(organization=organization, actor=actor, contract=contract, resource=resource)
        for name, contract, resource in STAGES
    }


def _result(status, before, baseline, receipt):
    return {
        "status": status,
        "rows": 3 if status in ("dry_run", "applied") else 0,
        "applied": status == "applied",
        "baseline": baseline,
        "receipt": receipt,
        "graph": digest({name: r["graph"] for name, r in before.items()}),
        "models": sum(r["models"] for r in before.values()),
        "protected_rows": sum(r["protected_rows"] for r in before.values()),
    }


@transaction.atomic
def run(*, organization, actor, apply=False, expected_baseline=""):
    require(
        two.ORG == vefa.ORG
        and two.PERIOD == vefa.PERIOD
        and len(two.CASES) == 2
        and len(vefa.CASES) == 1
        and {p["row_id"] for p in two.CASES}.isdisjoint(p["row_id"] for p in vefa.CASES)
        and {o for p in two.CASES for o in p["offerings"]}.isdisjoint(o for p in vefa.CASES for o in p["offerings"]),
        "catalog_chain_fixed_disjoint_contracts_required",
    )
    # Both fresh native dry-runs retain their row/parent/role locks until this outer transaction ends.
    before = _states(organization, actor)
    baseline = digest(before)
    previous = (
        model("audit.AuditLog")
        ._base_manager.filter(organization=organization, resource_type=RESOURCE, new_values__operation="apply")
        .order_by("-created_at", "pk")
        .first()
    )
    if all(r["status"] == "already_applied" for r in before.values()):
        require(previous is not None and previous.new_values["after"] == before, "catalog_chain_exact_receipt_required")
        return _result("already_applied", before, baseline, previous.resource_id)
    require(
        all(r["status"] == "dry_run" for r in before.values()) and previous is None,
        "catalog_chain_partial_existing_state",
    )
    if not apply:
        return _result("dry_run", before, baseline, None)
    require(expected_baseline == baseline, "catalog_chain_fresh_baseline_required")
    receipts = {}
    for name, contract, resource in STAGES:
        result = core.run(
            organization=organization,
            actor=actor,
            contract=contract,
            resource=resource,
            apply=True,
            expected_baseline=before[name]["baseline"],
        )
        require(result["status"] == "applied" and result["applied"], "catalog_chain_native_apply_required")
        receipts[name] = result["receipt"]
    after = _states(organization, actor)
    require(
        all(r["status"] == "already_applied" and r["receipt"] == receipts[name] for name, r in after.items()),
        "catalog_chain_native_repeat_required",
    )
    require(
        all(all(before[name][k] == r[k] for k in ("graph", "models", "protected_rows")) for name, r in after.items()),
        "catalog_chain_protected_graph_changed",
    )
    receipt = str(uuid.uuid4())
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type=RESOURCE,
        resource_id=receipt,
        reason="Exactly two official source contexts then the explicit legacy fallback; load FKs only, atomic3.",
        old_values=before,
        new_values={"operation": "apply", "after": after, "native_receipts": receipts},
    )
    return _result("applied", before, baseline, receipt)
