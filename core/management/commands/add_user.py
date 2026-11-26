import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import BaseCommand, CommandError

from core.models import Role


class Command(BaseCommand):
    help = "Add a staff login. Example: manage.py add_user matyas --role Admin"

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--role", choices=Role.ALL, default=Role.OPERATIONS)
        parser.add_argument("--full-name", default="")
        parser.add_argument("--password", help="Only for scripts; you are asked otherwise.")

    def handle(self, username, role, full_name, password, **options):
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            raise CommandError(f"{username} already exists.")
        if not password:
            password = getpass.getpass("Password (at least 10 characters): ")
            if password != getpass.getpass("Type it again: "):
                raise CommandError("The two passwords do not match.")
        user = User(username=username, first_name=full_name)
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages))
        user.set_password(password)
        user.is_staff = role == Role.ADMIN
        user.save()
        user.groups.add(Group.objects.get_or_create(name=role)[0])
        self.stdout.write(self.style.SUCCESS(
            f"Login '{username}' created with role {role}. At first login you will set up the phone code."))
