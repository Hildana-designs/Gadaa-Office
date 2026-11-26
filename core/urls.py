from django.urls import path

from core import views

app_name = "core"
urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("login/code/", views.mfa_verify, name="mfa_verify"),
    path("login/setup-code/", views.mfa_setup, name="mfa_setup"),
    path("users/", views.users, name="users"),
    path("users/new/", views.user_edit, name="user_new"),
    path("users/<int:pk>/", views.user_edit, name="user_edit"),
    path("users/<int:pk>/reset-code/", views.user_reset_mfa, name="user_reset_mfa"),
    path("settings/", views.settings_list, name="settings"),
    path("settings/<int:pk>/", views.setting_edit, name="setting_edit"),
    path("activity/", views.activity, name="activity"),
    path("backups/", views.backups, name="backups"),
    path("backups/now/", views.backup_now, name="backup_now"),
    path("files/<path:path>", views.protected_file, name="file"),
]
