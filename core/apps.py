from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Office"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed

        from core import audit

        audit.connect()

        def on_login(sender, request, user, **kwargs):
            audit.log("login", user, user=user)

        def on_logout(sender, request, user, **kwargs):
            if user:
                audit.log("logout", user, user=user)

        def on_failed(sender, credentials, request=None, **kwargs):
            audit.log("login_failed", note=f"username: {credentials.get('username', '')}")

        user_logged_in.connect(on_login, dispatch_uid="audit-login", weak=False)
        user_logged_out.connect(on_logout, dispatch_uid="audit-logout", weak=False)
        user_login_failed.connect(on_failed, dispatch_uid="audit-login-failed", weak=False)
