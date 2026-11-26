from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Role:
    """The four roles. Each is a Django group of the same name."""

    ADMIN = "Admin"
    OPERATIONS = "Operations"
    ACCOUNTANT = "Accountant"
    GUIDE = "Guide"  # not used until Phase 4
    ALL = [ADMIN, OPERATIONS, ACCOUNTANT, GUIDE]


class AppSetting(models.Model):
    """One business setting, for example the VAT rate or the default margin."""

    KIND_CHOICES = [("decimal", "Number"), ("percent", "Percentage"), ("text", "Text"), ("yesno", "Yes/No"), ("int", "Whole number")]

    key = models.SlugField(max_length=80, unique=True)
    label = models.CharField(max_length=200)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default="text")
    value = models.CharField(max_length=500, blank=True)
    source_note = models.TextField(blank=True, help_text="Where the value came from.")
    confirmed = models.BooleanField(default=False, help_text="Untick while the value is an assumption.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return self.label


class Choice(models.Model):
    """A value in a drop-down list (statuses, categories, currencies...)."""

    list_name = models.CharField(max_length=60)
    value = models.CharField(max_length=120)
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["list_name", "order", "value"]
        constraints = [models.UniqueConstraint(fields=["list_name", "value"], name="uniq_choice")]

    def __str__(self):
        return f"{self.list_name}: {self.value}"

    @classmethod
    def values(cls, list_name):
        return list(cls.objects.filter(list_name=list_name, active=True).values_list("value", flat=True))


class AuditLog(models.Model):
    ACTIONS = [
        ("create", "Created"),
        ("update", "Changed"),
        ("delete", "Deleted"),
        ("view_sensitive", "Viewed passport/ID data"),
        ("login", "Logged in"),
        ("login_failed", "Failed login"),
        ("logout", "Logged out"),
        ("backup", "Backup"),
        ("restore", "Restore"),
        ("import", "Import"),
        ("export", "Export"),
    ]

    at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=20, choices=ACTIONS)
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=300, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.username} {self.action} {self.object_repr}"


class BackupRun(models.Model):
    STATUS = [("ok", "Succeeded"), ("failed", "Failed")]

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS)
    file_name = models.CharField(max_length=300, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    offsite_copied = models.BooleanField(default=False)
    message = models.TextField(blank=True)
    trigger = models.CharField(max_length=20, default="schedule")

    class Meta:
        ordering = ["-started_at"]


class ImportRecord(models.Model):
    """Remembers which source row created which record, so re-imports never duplicate."""

    source_key = models.CharField(max_length=300, unique=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=64)
    imported_at = models.DateTimeField(auto_now=True)
    run_label = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.source_key
