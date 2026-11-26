from django.contrib.auth.models import Group
from django.core.management import BaseCommand, call_command

from core.models import Role


class Command(BaseCommand):
    help = "Create or update the database tables and the four roles."

    def handle(self, *args, **options):
        call_command("migrate", interactive=False, verbosity=1)
        for name in Role.ALL:
            Group.objects.get_or_create(name=name)
        call_command("collectstatic", interactive=False, verbosity=0)
        self.stdout.write(self.style.SUCCESS("Database ready."))
