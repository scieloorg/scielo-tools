import logging
import os
import tempfile

from django.utils import timezone

from xml_manager import utils
from xml_manager.forms import SPSPackageValidationForm
from xml_manager.models import SPSPackageValidation, SPSPackageValidationStatus


def run_sps_package_validation(validation_pk):
    try:
        validation = SPSPackageValidation.objects.get(pk=validation_pk)
    except SPSPackageValidation.DoesNotExist:
        logging.error(f"SPSPackageValidation pk={validation_pk} does not exist.")
        return False

    validation.status = SPSPackageValidationStatus.RUNNING
    validation.save()

    try:
        zip_path = validation.package_document.file.path
        rows, exceptions = utils.validate_zip(zip_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            base_name = os.path.splitext(validation.package_document.title)[0]
            csv_path = os.path.join(tmpdir, f"{base_name}.validation.csv")
            utils.write_csv(rows, csv_path)
            validation.validation_document = (
                SPSPackageValidationForm.save_or_replace_wagtail_document(
                    validation.validation_document,
                    csv_path,
                    title=f"{base_name}.validation.csv",
                )
            )

            exceptions_path = os.path.join(tmpdir, f"{base_name}.exceptions.json")
            utils.write_exceptions_json(exceptions, exceptions_path)
            validation.exceptions_document = (
                SPSPackageValidationForm.save_or_replace_wagtail_document(
                    validation.exceptions_document,
                    exceptions_path,
                    title=f"{base_name}.exceptions.json",
                )
            )

        validation.status = SPSPackageValidationStatus.DONE
        validation.validated_at = timezone.now()
        validation.error_message = ""

    except Exception as e:
        logging.error(f"Error during SPS package validation pk={validation_pk}: {e}")
        validation.status = SPSPackageValidationStatus.ERROR
        validation.error_message = str(e)

    validation.save()
    return True
