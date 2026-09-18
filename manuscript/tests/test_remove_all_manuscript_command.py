from unittest.mock import patch

import pytest
from django.core.management import call_command

from manuscript.models import Manuscript


def _create_manuscript(title):
    return Manuscript.objects.create(title=title)


@pytest.mark.django_db
def test_remove_all_manuscript_dry_run(capsys):
    _create_manuscript("Manuscript one")

    call_command("remove_all_manuscript", dry_run=True)

    assert Manuscript.objects.count() == 1
    captured = capsys.readouterr()
    assert "Dry run" in captured.out


@pytest.mark.django_db
def test_remove_all_manuscript_deletes_all():
    _create_manuscript("Manuscript one")
    _create_manuscript("Manuscript two")

    call_command("remove_all_manuscript", no_input=True)

    assert Manuscript.objects.count() == 0


@pytest.mark.django_db
def test_remove_all_manuscript_empty(capsys):
    call_command("remove_all_manuscript", no_input=True)
    captured = capsys.readouterr()
    assert "No manuscripts to remove." in captured.out


@pytest.mark.django_db
def test_remove_all_manuscript_aborts_without_yes():
    _create_manuscript("Manuscript one")

    with patch("builtins.input", return_value="no"):
        call_command("remove_all_manuscript")

    assert Manuscript.objects.count() == 1


@pytest.mark.django_db
def test_remove_all_manuscript_confirms_yes():
    _create_manuscript("Manuscript one")

    with patch("builtins.input", return_value="yes"):
        call_command("remove_all_manuscript")

    assert Manuscript.objects.count() == 0
