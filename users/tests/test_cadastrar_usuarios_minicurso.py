from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from wagtail.users.models import UserProfile

from users.management.commands.cadastrar_usuarios_minicurso import EMAILS

LIST = (
    "anna.kobayashi@scielo.org",
    "publicacao@scielo.org",
)


@pytest.mark.django_db
def test_creates_users_with_portuguese_admin():
    with patch("users.management.commands.cadastrar_usuarios_minicurso.EMAILS", LIST):
        call_command("cadastrar_usuarios_minicurso", password="secret")

    user_model = get_user_model()
    anna = user_model.objects.get(email="anna.kobayashi@scielo.org")
    assert anna.first_name == "Anna"
    assert anna.last_name == "Kobayashi"
    assert UserProfile.objects.get(user=anna).preferred_language == "pt-br"
    publicacao = user_model.objects.get(email="publicacao@scielo.org")
    assert publicacao.first_name == "Publicacao"
    assert publicacao.last_name == ""
    assert UserProfile.objects.get(user=publicacao).preferred_language == "pt-br"


@pytest.mark.django_db
def test_existing_user_gets_portuguese_admin_without_password_change():
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username="anna.kobayashi@scielo.org",
        email="anna.kobayashi@scielo.org",
        password="old-secret",
        first_name="Anna",
        last_name="Kobayashi",
    )
    with patch("users.management.commands.cadastrar_usuarios_minicurso.EMAILS", LIST):
        call_command("cadastrar_usuarios_minicurso", password="secret")
    user.refresh_from_db()
    assert user.check_password("old-secret")
    assert UserProfile.objects.get(user=user).preferred_language == "pt-br"


@pytest.mark.django_db
def test_remove_deletes_listed_users_and_keeps_others():
    user_model = get_user_model()
    with patch("users.management.commands.cadastrar_usuarios_minicurso.EMAILS", LIST):
        call_command("cadastrar_usuarios_minicurso", password="secret")
    outsider = user_model.objects.create_user(
        username="outsider", email="outsider@example.com", password="secret"
    )
    with patch("users.management.commands.cadastrar_usuarios_minicurso.EMAILS", LIST):
        call_command("cadastrar_usuarios_minicurso", remover=True, no_input=True)
    assert not user_model.objects.filter(email="anna.kobayashi@scielo.org").exists()
    assert not user_model.objects.filter(email="publicacao@scielo.org").exists()
    assert user_model.objects.filter(pk=outsider.pk).exists()


@pytest.mark.django_db
def test_remove_keeps_superuser_from_the_list():
    user_model = get_user_model()
    user_model.objects.create_superuser(
        username="anna.kobayashi@scielo.org",
        email="anna.kobayashi@scielo.org",
        password="secret",
    )
    with patch("users.management.commands.cadastrar_usuarios_minicurso.EMAILS", LIST):
        call_command("cadastrar_usuarios_minicurso", remover=True, no_input=True)
    assert user_model.objects.filter(email="anna.kobayashi@scielo.org").exists()


@pytest.mark.django_db
def test_remove_dry_run_does_not_delete(capsys):
    with patch("users.management.commands.cadastrar_usuarios_minicurso.EMAILS", LIST):
        call_command("cadastrar_usuarios_minicurso", password="secret")
        call_command("cadastrar_usuarios_minicurso", remover=True, dry_run=True)
    captured = capsys.readouterr()
    assert "Dry run" in captured.out
    assert get_user_model().objects.filter(email="anna.kobayashi@scielo.org").exists()


@pytest.mark.django_db
def test_remove_aborts_without_yes():
    with patch("users.management.commands.cadastrar_usuarios_minicurso.EMAILS", LIST):
        call_command("cadastrar_usuarios_minicurso", password="secret")
        with patch("builtins.input", return_value="no"):
            call_command("cadastrar_usuarios_minicurso", remover=True)
    assert get_user_model().objects.filter(email="anna.kobayashi@scielo.org").exists()


@pytest.mark.django_db
def test_create_requires_password():
    with pytest.raises(CommandError):
        call_command("cadastrar_usuarios_minicurso")


@pytest.mark.django_db
def test_command_list_has_original_emails():
    assert "anna.kobayashi@scielo.org" in EMAILS
    assert len(EMAILS) == 20
