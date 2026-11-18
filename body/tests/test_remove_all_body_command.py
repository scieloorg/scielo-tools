from unittest.mock import patch

import pytest
from django.core.management import call_command

from body.models import Body


def _create_body(source_text):
    return Body.objects.create(source_text=source_text)


@pytest.mark.django_db
def test_remove_all_body_dry_run(capsys):
    _create_body("Body text one.")

    call_command("remove_all_body", dry_run=True)

    assert Body.objects.count() == 1
    captured = capsys.readouterr()
    assert "Dry run" in captured.out


@pytest.mark.django_db
def test_remove_all_body_deletes_all():
    _create_body("Body text one.")
    _create_body("Body text two.")

    call_command("remove_all_body", no_input=True)

    assert Body.objects.count() == 0


@pytest.mark.django_db
def test_remove_all_body_empty(capsys):
    call_command("remove_all_body", no_input=True)
    captured = capsys.readouterr()
    assert "No bodies to remove." in captured.out


@pytest.mark.django_db
def test_remove_all_body_aborts_without_yes():
    _create_body("Body text one.")

    with patch("builtins.input", return_value="no"):
        call_command("remove_all_body")

    assert Body.objects.count() == 1


@pytest.mark.django_db
def test_remove_all_body_confirms_yes():
    _create_body("Body text one.")

    with patch("builtins.input", return_value="yes"):
        call_command("remove_all_body")

    assert Body.objects.count() == 0
