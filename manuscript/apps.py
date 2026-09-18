from django.apps import AppConfig


class ManuscriptConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "manuscript"

    def ready(self):
        import manuscript.signals  # noqa: F401
