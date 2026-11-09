"""Typed source identities, exact current routes; unsupported rebindings stay explicit holds."""

import collections

from .ledger import effective_maps


class Proofs:
    def __init__(self, plan, snapshot):
        self.routes = {row["key"]: row for row in plan["routes"]}
        self.offerings = {row["id"]: row for row in snapshot["offerings"]}
        self.maps = collections.defaultdict(set)
        effective = effective_maps(snapshot["ledger"], snapshot["ledger_versions"])
        self.by_id = {row["id"]: row for row in effective}
        for row in effective:
            self.maps[(row["entity_type"], row["target_model_label"], row["legacy_pk"])].add(row["target_pk"])
        self.enrollments = collections.defaultdict(list)
        self.route_cache = {}
        self.classes = collections.Counter(
            tuple(row[k] for k in ("subject_id", "group_id", "instructor_id", "period_id"))
            for row in self.offerings.values()
        )
        for row in snapshot["enrollments"]:
            if row["status"] == "enrolled":
                self.enrollments[(row["offering_id"], str(row["student_id"]))].append(row)

    def mapped(self, entity, label, key, target):
        return self.maps[(entity, label, str(key))] == {str(target)}

    def route(self, key):
        if key not in self.route_cache:
            self.route_cache[key] = self._route(key)
        return self.route_cache[key]

    def _route(self, key):
        spec = self.routes.get(key)
        if spec is None:
            return None, "source_route_unknown"
        course = self.offerings.get(spec.get("offering_id"))
        if course is None:
            return None, "source_route_not_current"
        checks = (
            ("lesson_subject", "registrar.subject", "legacy_subject_id", "subject_id"),
            ("group_unit", "organizations.orgunit", "legacy_group_id", "group_id"),
            ("worker", "auth.user", "legacy_teacher_id", "instructor_id"),
        )
        if not all(
            self.mapped(entity, label, spec.get(source), course[target]) for entity, label, source, target in checks
        ):
            return None, "source_typed_class_identity_unresolved"
        if spec.get("mode") == "offering_ledger":
            if not self.mapped(
                "course_offering", "registrar.courseoffering", spec.get("legacy_offering_key"), course["id"]
            ):
                return None, "source_offering_ledger_unresolved"
        elif spec.get("mode") == "unique_typed_class":
            if self.classes[tuple(course[k] for k in ("subject_id", "group_id", "instructor_id", "period_id"))] != 1:
                return None, "source_class_not_unique"
        else:
            return None, "authoritative_alias_or_transfer_proof_required"
        return course, None

    def resolve(self, source):
        targets, reasons = [], set()
        users = self.maps[("student", "auth.user", str(source["legacy_student_id"]))]
        if len(users) != 1:
            return [], {"source_student_identity_unresolved"}
        student = next(iter(users))
        if not source.get("route_keys"):
            return [], {"source_route_unknown"}
        for key in source["route_keys"]:
            course, reason = self.route(key)
            if reason:
                reasons.add(reason)
                continue
            enrollments = self.enrollments.get((course["id"], student), [])
            if len(enrollments) == 1:
                targets.append((course, enrollments[0]))
            elif enrollments:
                reasons.add("current_enrollment_ambiguous")
        unique = {(course["id"], enrollment["id"]): (course, enrollment) for course, enrollment in targets}
        if len(unique) > 1:
            return [], {"source_student_class_route_ambiguous"}
        if not unique and not reasons:
            reasons.add("no_current_enrollment")
        return list(unique.values()), reasons
