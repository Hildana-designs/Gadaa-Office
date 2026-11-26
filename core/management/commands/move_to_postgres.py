"""
Copy everything from the current database into a PostgreSQL database.

    python manage.py move_to_postgres postgres://gadaa:password@localhost:5432/gadaa

The PostgreSQL database must exist and be empty. The current database is not
changed. Afterwards, set GADAA_DATABASE_URL in the settings file and restart.
"""
import io

from django.apps import apps
from django.core.management import BaseCommand, CommandError, call_command
from django.db import connections

from gadaa.envfile import parse_database_url


class Command(BaseCommand):
    help = "Copy all data from the current database to an empty PostgreSQL database and check the counts."

    def add_arguments(self, parser):
        parser.add_argument("target_url")

    def handle(self, target_url, **options):
        config = parse_database_url(target_url, default_sqlite=None)
        if not config["ENGINE"].endswith("postgresql"):
            raise CommandError("The target must be a postgres:// address.")
        base = dict(connections.databases["default"])
        base.update(config)
        base["OPTIONS"] = config.get("OPTIONS", {})
        connections.databases["target"] = base
        self.stdout.write("1/4 Creating tables in PostgreSQL...")
        call_command("migrate", database="target", interactive=False, verbosity=0)
        models = [m for m in apps.get_models() if m._meta.managed and not m._meta.proxy]
        busy = [m._meta.label for m in models
                if m._meta.label not in {"contenttypes.ContentType", "auth.Permission"} and m.objects.using("target").exists()]
        if busy:
            raise CommandError(f"The PostgreSQL database is not empty ({', '.join(busy[:5])}). Nothing was copied.")
        self.stdout.write("2/4 Reading the current database...")
        buf = io.StringIO()
        call_command("dumpdata", "--natural-foreign", "--natural-primary", "--exclude=contenttypes",
                     "--exclude=auth.permission", "--exclude=sessions", stdout=buf)
        path = "move_to_postgres.json"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(buf.getvalue())
        self.stdout.write("3/4 Writing to PostgreSQL...")
        call_command("loaddata", path, database="target", verbosity=0)
        self._reset_sequences()
        self.stdout.write("4/4 Checking every table has the same number of rows...")
        problems = []
        for m in models:
            if m._meta.label in {"contenttypes.ContentType", "auth.Permission", "sessions.Session"}:
                continue
            a, b = m.objects.using("default").count(), m.objects.using("target").count()
            if a != b:
                problems.append(f"{m._meta.label}: {a} here, {b} in PostgreSQL")
        import os

        os.remove(path)
        if problems:
            raise CommandError("Counts differ: " + "; ".join(problems))
        self.stdout.write(self.style.SUCCESS("All data copied and checked. Now set GADAA_DATABASE_URL and restart."))

    def _reset_sequences(self):
        from django.core.management.color import no_style

        conn = connections["target"]
        models = [m for m in apps.get_models() if m._meta.managed]
        with conn.cursor() as cur:
            for sql in conn.ops.sequence_reset_sql(no_style(), models):
                cur.execute(sql)
