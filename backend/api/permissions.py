from rest_framework import permissions


def _normalized_role(user) -> str:
    """Return the user's role uppercased for consistent comparisons."""
    if not user or not user.is_authenticated:
        return ""
    return str(getattr(user, "role", "")).upper()


class IsFarmer(permissions.BasePermission):
    def has_permission(self, request, view):
        return _normalized_role(request.user) == "FARMER"


class IsVet(permissions.BasePermission):
    def has_permission(self, request, view):
        return _normalized_role(request.user) == "VET"

class IsAdminUserRole(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (request.user.role == 'ADMIN' or request.user.is_staff)