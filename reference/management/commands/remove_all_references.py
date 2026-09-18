from django.core.management.base import BaseCommand
from django.db import transaction

from reference.models import ElementCitation, Reference


class Command(BaseCommand):
    help = "Remove all Reference and ElementCitation records from the database."

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
        ref_count = Reference.objects.count()
        cite_count = ElementCitation.objects.count()

        if ref_count == 0 and cite_count == 0:
            self.stdout.write("No references to remove.")
            return

        self.stdout.write(
            f"Found {ref_count} Reference(s) and {cite_count} ElementCitation(s)."
        )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — nothing deleted."))
            return

        if not options["no_input"]:
            confirm = input("Type 'yes' to permanently delete all references: ")
            if confirm != "yes":
                self.stdout.write("Aborted.")
                return

        with transaction.atomic():
            ElementCitation.objects.all().delete()
            Reference.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {ref_count} Reference(s) and "
                f"{cite_count} ElementCitation(s)."
            )
        )
