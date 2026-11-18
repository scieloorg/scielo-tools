from django.conf import settings


def webapp_version(request):
    version = settings.WEBAPP_VERSION
    url = ""
    if version and version != "0.0.0":
        url = "https://github.com/scieloorg/scielo-tools/releases/tag/" + version
    return {"WEBAPP_VERSION": version, "WEBAPP_VERSION_URL": url}
