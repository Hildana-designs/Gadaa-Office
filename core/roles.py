"""Who may do what."""
from django.core.exceptions import PermissionDenied

from core.models import Role


def roles_of(user):
    if not user.is_authenticated:
        return set()
    if user.is_superuser:
        return {Role.ADMIN}
    cached = getattr(user, "_gadaa_roles", None)
    if cached is None:
        cached = set(user.groups.values_list("name", flat=True))
        user._gadaa_roles = cached
    return cached


def is_admin(user):
    return Role.ADMIN in roles_of(user)


def can_edit(user):
    """Admin and Operations change records. The Accountant only reads."""
    return bool(roles_of(user) & {Role.ADMIN, Role.OPERATIONS})


def can_view(user):
    return bool(roles_of(user) & {Role.ADMIN, Role.OPERATIONS, Role.ACCOUNTANT})


def can_see_passports(user):
    return bool(roles_of(user) & {Role.ADMIN, Role.OPERATIONS})


def require(check, user):
    if not check(user):
        raise PermissionDenied("Your role does not allow this.")
