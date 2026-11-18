from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from wagtail.users.models import UserProfile

EMAILS = (
    "anderson.santos@scielo.org",
    "anna.kobayashi@scielo.org",
    "felipe.esteves@scielo.org",
    "francine.curivil@scielo.org",
    "gabriel.flores@scielo.org",
    "gabriela.alfonso@scielo.org",
    "gabriela.carvalho@scielo.org",
    "gestao.editorial@scielo.org",
    "isabela.fonseca@scielo.org",
    "jessica.nascimento@scielo.org",
    "joyce.souza@scielo.org",
    "luzia.saeko@scielo.org",
    "marianie.moreira@scielo.org",
    "marina.chagas@scielo.org",
    "publicacao@scielo.org",
    "renata.almeida@scielo.org",
    "roberta.takenaka@scielo.org",
    "solange.santos@scielo.org",
    "suely.lucena@scielo.org",
    "taina.carneiro@scielo.org",
)

GROUP_NAME = "Mini-curso JATS"
ADMIN_LANGUAGE = "pt-br"

PERMISSIONS = (
    ("wagtailadmin", "access_admin"),
    ("manuscript", "add_manuscript"),
    ("manuscript", "change_manuscript"),
    ("manuscript", "view_manuscript"),
    ("manuscript", "delete_manuscript"),
)


def user_from_email(user_model, email):
    existing = user_model.objects.filter(email__iexact=email).first()
    if existing is None:
        existing = user_model.objects.filter(username__iexact=email).first()
    return existing


def set_admin_portuguese(user):
    profile = UserProfile.get_for_user(user)
    if profile.preferred_language == ADMIN_LANGUAGE:
        return
    profile.preferred_language = ADMIN_LANGUAGE
    profile.save(update_fields=["preferred_language"])


class Command(BaseCommand):
    help = (
        "Cadastra a lista do mini-curso em português no admin. "
        "O login é o e-mail. Use --remover para apagar as contas da lista."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="",
            help="Senha única aplicada a cada conta nova.",
        )
        parser.add_argument(
            "--remover",
            action="store_true",
            help="Remove as contas da lista. Superusuários ficam.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra o que seria feito sem gravar.",
        )
        parser.add_argument(
            "--no-input",
            "--noinput",
            action="store_true",
            help="Não pede confirmação ao remover.",
        )

    def handle(self, *args, **options):
        user_model = get_user_model()
        if options["remover"]:
            kept = 0
            to_delete = []
            for email in EMAILS:
                user = user_from_email(user_model, email)
                if user is None:
                    continue
                if user.is_superuser:
                    kept += 1
                    self.stdout.write(f"superusuário mantido: {email}")
                    continue
                to_delete.append(user)
                if options["dry_run"]:
                    self.stdout.write(f"removeria: {email}")
                else:
                    self.stdout.write(f"remove: {email}")

            if not to_delete:
                self.stdout.write("Nenhuma conta da lista para remover.")
                return

            if options["dry_run"]:
                self.stdout.write(
                    self.style.WARNING(
                        f"Dry run — {len(to_delete)} conta(s), "
                        f"{kept} superusuário(s) mantido(s)."
                    )
                )
                return

            if not options["no_input"]:
                confirm = input("Type 'yes' to delete the listed mini-course users: ")
                if confirm != "yes":
                    self.stdout.write("Aborted.")
                    return

            deleted_count = 0
            for user in to_delete:
                user.delete()
                deleted_count += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"{deleted_count} removido(s), {kept} superusuário(s) mantido(s)."
                )
            )
            return

        password = options["password"]
        if not str(password).strip():
            raise CommandError("Informe a senha em --password ou use --remover.")

        permissions = []
        missing = []
        for app_label, codename in PERMISSIONS:
            permission = Permission.objects.filter(
                codename=codename,
                content_type__app_label=app_label,
            ).first()
            if permission is None:
                missing.append(f"{app_label}.{codename}")
            else:
                permissions.append(permission)
        if missing:
            raise CommandError("Permissões em falta: " + ", ".join(missing))

        group, _created = Group.objects.get_or_create(name=GROUP_NAME)
        dry_run = options["dry_run"]
        if not dry_run:
            group.permissions.add(*permissions)

        created_count = 0
        skipped_count = 0
        for email in EMAILS:
            local_part = email.split("@", 1)[0]
            given, _, family = local_part.partition(".")
            first_name = given.capitalize()
            last_name = " ".join(
                part.capitalize() for part in family.split(".") if part
            )
            full_name = f"{first_name} {last_name}".strip()
            existing = user_from_email(user_model, email)
            if existing is not None:
                if not dry_run:
                    existing.groups.add(group)
                    set_admin_portuguese(existing)
                skipped_count += 1
                self.stdout.write(f"já existia: {full_name} <{email}>")
                continue
            if dry_run:
                created_count += 1
                self.stdout.write(f"criaria: {full_name} <{email}>")
                continue
            user = user_model.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
            user.name = full_name
            user.save(update_fields=["name"])
            user.groups.add(group)
            set_admin_portuguese(user)
            created_count += 1
            self.stdout.write(self.style.SUCCESS(f"criado: {full_name} <{email}>"))

        prefix = "dry run — " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}{created_count} criado(s), {skipped_count} já existente(s)."
            )
        )
