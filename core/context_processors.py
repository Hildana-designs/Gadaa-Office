from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core import roles


def backup_warning():
    """Plain-English warning shown on every page when backups need attention."""
    from core.models import BackupRun

    last = BackupRun.objects.first()
    last_ok = BackupRun.objects.filter(status="ok").first()
    if last is None:
        return "No backup has been made yet."
    if last.status == "failed":
        return f"The last backup failed ({timezone.localtime(last.started_at):%d %b %H:%M}): {last.message[:160]}"
    if last_ok and timezone.now() - last_ok.started_at > timedelta(hours=30):
        return f"The last successful backup is from {timezone.localtime(last_ok.started_at):%d %b %Y}. Check the GADAA worker is running."
    if not settings.BACKUP_OFFSITE_DIR:
        return "Backups are only on this computer. Plug in an external drive and set it in the settings file."
    if last_ok and not last_ok.offsite_copied:
        return "The last backup could not be copied to the external drive. Is it plugged in?"
    return ""


def app_context(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    from ops.resources import BY_SLUG, NAV

    verified = user.is_verified() if hasattr(user, "is_verified") else False
    nav = []
    for group, slugs in NAV:
        items = [(s, BY_SLUG[s].title) for s in slugs
                 if not (BY_SLUG[s].sensitive and not roles.can_see_passports(user))]
        nav.append((group, items))
    return {
        "show_nav": verified or not settings.GADAA_MFA_REQUIRED,
        "nav": nav,
        "role_names": sorted(roles.roles_of(user)),
        "can_edit": roles.can_edit(user),
        "is_admin": roles.is_admin(user),
        "can_see_passports": roles.can_see_passports(user),
        "backup_warning": backup_warning() if roles.is_admin(user) or roles.can_edit(user) else "",
    }
