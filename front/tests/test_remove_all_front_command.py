from unittest.mock import patch

import pytest
from django.core.management import call_command

from front.models import Front


def _create_front(source_text):
    return Front.objects.create(source_text=source_text)


@pytest.mark.django_db
def test_remove_all_front_dry_run(capsys):
    _create_front("Front matter one.")

    call_command("remove_all_front", dry_run=True)

    assert Front.objects.count() == 1
    captured = capsys.readouterr()
    assert "Dry run" in captured.out


@pytest.mark.django_db
def test_remove_all_front_deletes_all():
    _create_front("Front matter one.")
    _create_front("Front matter two.")

    call_command("remove_all_front", no_input=True)

    assert Front.objects.count() == 0


@pytest.mark.django_db
def test_remove_all_front_empty(capsys):
    call_command("remove_all_front", no_input=True)
    captured = capsys.readouterr()
    assert "No fronts to remove." in captured.out


@pytest.mark.django_db
def test_remove_all_front_aborts_without_yes():
    _create_front("Front matter one.")

    with patch("builtins.input", return_value="no"):
        call_command("remove_all_front")

    assert Front.objects.count() == 1


@pytest.mark.django_db
def test_remove_all_front_confirms_yes():
    _create_front("Front matter one.")

    with patch("builtins.input", return_value="yes"):
        call_command("remove_all_front")

    assert Front.objects.count() == 0
