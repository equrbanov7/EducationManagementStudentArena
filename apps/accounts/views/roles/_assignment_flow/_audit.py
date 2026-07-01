"""role_assignment flow — audit + deny cavabları mixin-i."""

from django.http import HttpResponse, HttpResponseForbidden, JsonResponse


class _AuditMixin:
    """audit + deny cavabları (RoleAssignmentFlow MRO ilə istifadə edir)."""

    def _wants_json_response(self):
        if self.request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return True
        accepted = self.request.headers.get("Accept", "")
        return "application/json" in accepted.lower()

    def _resolve_request_id(self):
        raw_request_id = (
            getattr(self.request, "request_id", None)
            or self.request.META.get("HTTP_X_REQUEST_ID")
            or self.request.META.get("HTTP_X_CORRELATION_ID")
        )
        return str(raw_request_id).strip() if raw_request_id else ""

    def _build_role_assignment_audit_values(
        self,
        *,
        status,
        action_name,
        target_role=None,
        target_membership=None,
        target_user=None,
        old_role=None,
        reason_code="",
        extra=None,
    ):
        resolved_target_user = target_user or (target_membership.user if target_membership is not None else None)
        resolved_old_role = old_role or (target_membership.role if target_membership is not None else None)
        values = {
            "status": status,
            "action_type": action_name or self.request.POST.get("action", ""),
            "actor_user_id": str(self.request.user.id),
            "org_id": str(self.org.id),
            "target_user_id": str(resolved_target_user.id) if resolved_target_user is not None else "",
            "membership_id": str(target_membership.id) if target_membership is not None else "",
            "old_role_id": str(resolved_old_role.id) if resolved_old_role is not None else "",
            "old_role_name": resolved_old_role.display_name if resolved_old_role is not None else "",
            "new_role_id": str(target_role.id) if target_role is not None else "",
            "new_role_name": target_role.display_name if target_role is not None else "",
            "reason_code": reason_code or "",
            "request_id": self._resolve_request_id(),
        }
        if extra:
            values.update(extra)
        return values

    def _deny_assignment(
        self,
        reason_code,
        reason_message,
        *,
        status=403,
        action_name=None,
        target_membership=None,
        target_user=None,
        target_role=None,
        extra=None,
        force_json=False,
    ):
        resource_type = "role_assignment"
        resource_id = ""
        resource_repr = action_name or (self.request.POST.get("action", "") if self.request.method == "POST" else "")
        if target_membership is not None:
            resource_type = "membership"
            resource_id = str(target_membership.id)
            resource_repr = str(target_membership)
        elif target_user is not None:
            resource_type = "user"
            resource_id = str(target_user.id)
            resource_repr = target_user.username
        denied_values = self._build_role_assignment_audit_values(
            status="denied",
            action_name=action_name,
            target_role=target_role,
            target_membership=target_membership,
            target_user=target_user,
            old_role=target_membership.role if target_membership is not None else None,
            reason_code=reason_code,
            extra={
                "action": action_name or self.request.POST.get("action", ""),
                "active_organization_id": str(self.org.id),
                "requested_membership_id": self.request.POST.get("membership_id"),
                "requested_user_id": self.request.POST.get("user_id"),
                "requested_role_id": self.request.POST.get("role_id"),
                "reason": reason_message,
            },
        )
        if target_role is not None:
            denied_values["requested_role_name"] = target_role.name
            denied_values["requested_role_level"] = target_role.level
        if extra:
            denied_values.update(extra)
        self.create_audit_log(
            user=self.request.user,
            organization=self.org,
            action="update",
            resource_type=resource_type,
            resource_id=resource_id,
            resource_repr=resource_repr,
            old_values=None,
            new_values=denied_values,
            reason=reason_message,
            request=self.request,
        )
        if force_json or self._wants_json_response():
            payload = {"success": False, "reason_code": reason_code, "message": reason_message}
            if extra:
                payload["details"] = extra
            return JsonResponse(payload, status=status)
        if status == 403:
            return HttpResponseForbidden(reason_message)
        return HttpResponse(reason_message, status=status)
