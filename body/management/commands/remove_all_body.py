from django.core.management.base import BaseCommand
from django.db import transaction

from body.models import Body


class Command(BaseCommand):
    help = "Remove all Body records from the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many records would be deleted without deleting them.",
        )
        parser.add_argument(
            "--no-input",
            "--noinput",
            action="store_true",
            help="Do not prompt for confirmation.",
        )

    def handle(self, *args, **options):
        count = Body.objects.count()

        if count == 0:
            self.stdout.write("No bodies to remove.")
            return

        self.stdout.write(f"Found {count} Body(s).")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — nothing deleted."))
            return

        if not options["no_input"]:
            confirm = input("Type 'yes' to permanently delete all bodies: ")
            if confirm != "yes":
                self.stdout.write("Aborted.")
                return

        with transaction.atomic():
            Body.objects.all().delete()

        self.stdout.write(self.style.SUCCESS(f"Deleted {count} Body(s)."))
