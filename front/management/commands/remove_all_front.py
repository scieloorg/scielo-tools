from django.core.management.base import BaseCommand
from django.db import transaction

from front.models import Front


class Command(BaseCommand):
    help = "Remove all Front records from the database."

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
        count = Front.objects.count()

        if count == 0:
            self.stdout.write("No fronts to remove.")
            return

        self.stdout.write(f"Found {count} Front(s).")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — nothing deleted."))
            return

        if not options["no_input"]:
            confirm = input("Type 'yes' to permanently delete all fronts: ")
            if confirm != "yes":
                self.stdout.write("Aborted.")
                return

        with transaction.atomic():
            Front.objects.all().delete()

        self.stdout.write(self.style.SUCCESS(f"Deleted {count} Front(s)."))
