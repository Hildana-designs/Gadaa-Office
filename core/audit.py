"""Activity log: records who created, changed or deleted what, and when."""
from datetime import date, datetime
from decimal import Decimal

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, post_save, pre_save

from core.crypto import EncryptedTextField
from core.middleware import get_current_ip, get_current_user

SKIP_FIELDS = {"created_at", "updated_at", "last_login", "password"}
_snapshots = {}


def _plain(value):
    if isinstance(value, (Decimal,)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    from django.db.models.fields.files import FieldFile

    if isinstance(value, FieldFile):
        return value.name or ""
    return value if isinstance(value, (str, int, float, bool, type(None), list, dict)) else str(value)


def _snapshot(instance):
    data = {}
    for field in instance._meta.concrete_fields:
        if field.name in SKIP_FIELDS:
            continue
        if isinstance(field, EncryptedTextField):
            data[field.name] = "(hidden)" if getattr(instance, field.attname) else ""
            continue
        data[field.name] = _plain(getattr(instance, field.attname))
    return data


def log(action, instance=None, note="", changes=None, user=None):
    from core.models import AuditLog

    user = user or get_current_user()
    entry = AuditLog(
        action=action,
        user=user if user and user.pk else None,
        username=getattr(user, "username", "") or "system",
        note=note,
        changes=changes or {},
        ip=get_current_ip(),
    )
    if instance is not None:
        entry.content_type = ContentType.objects.get_for_model(instance.__class__)
        entry.object_id = str(instance.pk)
        entry.object_repr = str(instance)[:300]
    entry.save()
    return entry


def _pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            return
        _snapshots[(sender, instance.pk)] = _snapshot(old)


def _post_save(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    new = _snapshot(instance)
    if created:
        log("create", instance, changes={k: [None, v] for k, v in new.items() if v not in (None, "", False)})
        return
    old = _snapshots.pop((sender, instance.pk), {})
    diff = {k: [old.get(k), v] for k, v in new.items() if old.get(k) != v}
    if diff:
        log("update", instance, changes=diff)


def _post_delete(sender, instance, **kwargs):
    log("delete", instance, changes={"deleted": _snapshot(instance)})


def tracked_models():
    models = [get_user_model()]
    models += [m for m in apps.get_app_config("ops").get_models()]
    models += [apps.get_model("core", "AppSetting"), apps.get_model("core", "Choice")]
    return models


def connect():
    for model in tracked_models():
        uid = f"audit-{model._meta.label}"
        pre_save.connect(_pre_save, sender=model, dispatch_uid=uid + "-pre")
        post_save.connect(_post_save, sender=model, dispatch_uid=uid + "-post")
        post_delete.connect(_post_delete, sender=model, dispatch_uid=uid + "-del")
