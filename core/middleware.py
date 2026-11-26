import threading

from django.conf import settings
from django.shortcuts import redirect
from django.urls import resolve, reverse

_local = threading.local()


def get_current_user():
    return getattr(_local, "user", None)


def get_current_ip():
    return getattr(_local, "ip", None)


class CurrentUserMiddleware:
    """Lets the activity log know who made each change."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        _local.ip = request.META.get("REMOTE_ADDR")
        try:
            return self.get_response(request)
        finally:
            _local.user = None
            _local.ip = None


OPEN_URL_NAMES = {"core:login", "core:mfa_verify", "core:mfa_setup", "core:logout"}


class LoginRequiredMiddleware:
    """Every page needs a login, and a two-factor check when that is switched on."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        if path.startswith(settings.STATIC_URL if settings.STATIC_URL.startswith("/") else "/" + settings.STATIC_URL):
            return self.get_response(request)
        try:
            match = resolve(path)
            name = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
        except Exception:
            name = None
        if name in OPEN_URL_NAMES:
            return self.get_response(request)
        user = request.user
        if not user.is_authenticated:
            return redirect(f"{reverse('core:login')}?next={path}")
        if settings.GADAA_MFA_REQUIRED and not user.is_verified():
            from django_otp import devices_for_user

            if any(True for _ in devices_for_user(user, confirmed=True)):
                return redirect(f"{reverse('core:mfa_verify')}?next={path}")
            return redirect(reverse("core:mfa_setup"))
        return self.get_response(request)
