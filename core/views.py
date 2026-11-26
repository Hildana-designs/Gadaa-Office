import mimetypes
from io import BytesIO
from pathlib import Path

import segno
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django_otp import devices_for_user, login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice

from core import audit, roles
from core.backup import make_backup
from core.models import AppSetting, AuditLog, BackupRun, Choice, Role


def _safe_next(request, default="core:home"):
    nxt = request.GET.get("next") or request.POST.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, require_https=request.is_secure()):
        return nxt
    return redirect(default).url


# ------------------------------------------------------------ login
def login_view(request):
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect(_safe_next(request))
    return render(request, "core/login.html", {"form": form, "next": request.GET.get("next", "")})


def logout_view(request):
    if request.method == "POST":
        logout(request)
    return redirect("core:login")


class CodeForm(forms.Form):
    code = forms.CharField(label="6-digit code", max_length=6, min_length=6,
                           widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric", "autofocus": True}))


def mfa_verify(request):
    if not request.user.is_authenticated:
        return redirect("core:login")
    devices = list(devices_for_user(request.user, confirmed=True))
    if not devices:
        return redirect("core:mfa_setup")
    form = CodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        for device in devices:
            if device.verify_token(form.cleaned_data["code"]):
                otp_login(request, device)
                return redirect(_safe_next(request))
        audit.log("login_failed", request.user, note="wrong two-factor code", user=request.user)
        form.add_error("code", "That code is not right. Check the time on your phone and try again.")
    return render(request, "core/mfa_verify.html", {"form": form, "next": request.GET.get("next", "")})


def mfa_setup(request):
    if not request.user.is_authenticated:
        return redirect("core:login")
    if any(True for _ in devices_for_user(request.user, confirmed=True)) and not request.user.is_verified():
        return redirect("core:mfa_verify")
    device = TOTPDevice.objects.filter(user=request.user, confirmed=False).first()
    if device is None:
        device = TOTPDevice.objects.create(user=request.user, name="Phone", confirmed=False)
    form = CodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if device.verify_token(form.cleaned_data["code"]):
            device.confirmed = True
            device.save()
            otp_login(request, device)
            messages.success(request, "Phone code set up. You will be asked for a code at each login.")
            return redirect("core:home")
        form.add_error("code", "That code is not right. Scan the picture again and type the newest code.")
    qr = segno.make(device.config_url, micro=False)
    buf = BytesIO()
    qr.save(buf, kind="svg", scale=5, border=2)
    return render(request, "core/mfa_setup.html", {"form": form, "qr_svg": buf.getvalue().decode()})


# ------------------------------------------------------------ home
def home(request):
    from ops.models import HotelBooking, Task, Trip

    today = timezone.localdate()
    ctx = {
        "open_trips": Trip.objects.exclude(status__in=["Closed (reconciled)", "Cancelled"]).order_by("start_date")[:10],
        "tasks_due": Task.objects.filter(status="open", due_date__lte=today).order_by("due_date")[:20],
        "hotel_deadlines": HotelBooking.objects.filter(status="Confirmed", release_deadline__gte=today,
                                                       release_deadline__lte=today + timezone.timedelta(days=7)),
        "last_backup": BackupRun.objects.first(),
        "today": today,
    }
    return render(request, "core/home.html", ctx)


# ------------------------------------------------------------ users (admin)
def _admin_only(request):
    roles.require(roles.is_admin, request.user)


class UserForm(forms.Form):
    username = forms.CharField(max_length=150)
    full_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    role = forms.ChoiceField(choices=[(r, r) for r in Role.ALL if r != Role.GUIDE])
    active = forms.BooleanField(required=False, initial=True)
    password = forms.CharField(widget=forms.PasswordInput, required=False,
                               help_text="Leave empty to keep the current password.")


def users(request):
    _admin_only(request)
    User = get_user_model()
    return render(request, "core/users.html", {"users": User.objects.order_by("username").prefetch_related("groups")})


def user_edit(request, pk=None):
    _admin_only(request)
    User = get_user_model()
    user = get_object_or_404(User, pk=pk) if pk else None
    initial = {}
    if user:
        initial = {"username": user.username, "full_name": user.first_name, "email": user.email,
                   "role": (user.groups.first().name if user.groups.exists() else Role.OPERATIONS), "active": user.is_active}
    form = UserForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        target = user or User()
        if not user and User.objects.filter(username=data["username"]).exists():
            form.add_error("username", "That username is taken.")
        elif not user and not data["password"]:
            form.add_error("password", "A new login needs a password.")
        else:
            target.username = data["username"]
            target.first_name = data["full_name"]
            target.email = data["email"]
            target.is_active = data["active"]
            target.is_staff = data["role"] == Role.ADMIN
            if data["password"]:
                try:
                    validate_password(data["password"], target)
                except forms.ValidationError as exc:
                    form.add_error("password", exc)
                    return render(request, "core/user_form.html", {"form": form, "target": user})
                target.set_password(data["password"])
            target.save()
            target.groups.set([Group.objects.get_or_create(name=data["role"])[0]])
            messages.success(request, f"Saved {target.username}.")
            return redirect("core:users")
    return render(request, "core/user_form.html", {"form": form, "target": user})


@require_POST
def user_reset_mfa(request, pk):
    _admin_only(request)
    user = get_object_or_404(get_user_model(), pk=pk)
    TOTPDevice.objects.filter(user=user).delete()
    audit.log("update", user, note="two-factor phone code reset by admin")
    messages.success(request, f"{user.username} will set up a new phone code at next login.")
    return redirect("core:users")


# ------------------------------------------------------------ settings
class SettingForm(forms.ModelForm):
    class Meta:
        model = AppSetting
        fields = ["value", "confirmed", "source_note"]
        widgets = {"source_note": forms.Textarea(attrs={"rows": 2})}


def settings_list(request):
    roles.require(roles.can_view, request.user)
    return render(request, "core/settings.html", {"items": AppSetting.objects.all(),
                                                  "lists": Choice.objects.all()})


def setting_edit(request, pk):
    _admin_only(request)
    item = get_object_or_404(AppSetting, pk=pk)
    form = SettingForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Saved {item.label}.")
        return redirect("core:settings")
    return render(request, "core/setting_form.html", {"form": form, "item": item})


# ------------------------------------------------------------ activity log
def activity(request):
    _admin_only(request)
    qs = AuditLog.objects.select_related("content_type")
    action = request.GET.get("action")
    if action:
        qs = qs.filter(action=action)
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(request, "core/activity.html", {"page": page, "actions": AuditLog.ACTIONS, "action": action})


# ------------------------------------------------------------ backups
def backups(request):
    _admin_only(request)
    return render(request, "core/backups.html", {
        "runs": BackupRun.objects.all()[:30],
        "offsite": settings.BACKUP_OFFSITE_DIR,
        "backup_dir": settings.BACKUP_DIR,
    })


@require_POST
def backup_now(request):
    _admin_only(request)
    run = make_backup(trigger="manual", user=request.user)
    (messages.success if run.status == "ok" else messages.error)(request, f"Backup {run.get_status_display().lower()}: {run.message}")
    return redirect("core:backups")


# ------------------------------------------------------------ protected files
def protected_file(request, path):
    """Uploaded files are only served to logged-in staff, never publicly."""
    from ops.models import Document

    roles.require(roles.can_view, request.user)
    sensitive = Document.objects.filter(file=path, sensitive=True).exists()
    if sensitive:
        roles.require(roles.can_see_passports, request.user)
        doc = Document.objects.filter(file=path).first()
        audit.log("view_sensitive", doc, note=f"opened {path}")
    root = Path(settings.MEDIA_ROOT).resolve()
    target = (root / path).resolve()
    if root not in target.parents or not target.is_file():
        raise Http404
    ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    response = FileResponse(open(target, "rb"), content_type=ctype)
    response["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
    response["X-Content-Type-Options"] = "nosniff"
    if not ctype.startswith("image/") and ctype != "application/pdf":
        response["Content-Disposition"] = f'attachment; filename="{target.name}"'
    return response


def permission_denied(request, exception=None):
    return render(request, "core/403.html", status=403)
