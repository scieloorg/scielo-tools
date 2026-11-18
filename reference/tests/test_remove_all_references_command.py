from unittest.mock import patch

import pytest
from django.core.management import call_command

from reference.models import ElementCitation, Reference, ReferenceStatus


def _create_reference(mixed_citation):
    reference = Reference.objects.create(
        mixed_citation=mixed_citation,
        status=ReferenceStatus.READY,
    )
    ElementCitation.objects.create(
        reference=reference,
        marked={"reftype": "journal"},
    )
    return reference


@pytest.mark.django_db
def test_remove_all_references_dry_run(capsys):
    _create_reference("Smith J. Nature. 2024.")

    call_command("remove_all_references", dry_run=True)

    assert Reference.objects.count() == 1
    assert ElementCitation.objects.count() == 1
    captured = capsys.readouterr()
    assert "Dry run" in captured.out


@pytest.mark.django_db
def test_remove_all_references_deletes_all():
    _create_reference("Smith J. Nature. 2024.")
    _create_reference("Doe A. Science. 2023.")

    call_command("remove_all_references", no_input=True)

    assert Reference.objects.count() == 0
    assert ElementCitation.objects.count() == 0


@pytest.mark.django_db
def test_remove_all_references_empty(capsys):
    call_command("remove_all_references", no_input=True)
    captured = capsys.readouterr()
    assert "No references to remove." in captured.out


@pytest.mark.django_db
def test_remove_all_references_aborts_without_yes():
    _create_reference("Smith J. Nature. 2024.")

    with patch("builtins.input", return_value="no"):
        call_command("remove_all_references")

    assert Reference.objects.count() == 1
    assert ElementCitation.objects.count() == 1


@pytest.mark.django_db
def test_remove_all_references_confirms_yes():
    _create_reference("Smith J. Nature. 2024.")

    with patch("builtins.input", return_value="yes"):
        call_command("remove_all_references")

    assert Reference.objects.count() == 0
    assert ElementCitation.objects.count() == 0
