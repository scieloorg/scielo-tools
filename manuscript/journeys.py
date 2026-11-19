import zipfile
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET
from wagtail.admin.auth import require_admin_access

SAMPLES_DIR = Path(settings.BASE_DIR) / "docs" / "guia" / "amostras"

FIGURES = tuple(
    {
        "name": f"imagens/ric-9999-0001-without-erro-gf0{number}.png",
        "label": _("Figura %(number)s") % {"number": number},
    }
    for number in range(1, 6)
)

COMPLEX_FIGURES = tuple(
    {
        "name": f"imagens/ric-9999-0001-complexo-gf0{number}.png",
        "label": _("Figura %(number)s") % {"number": number},
    }
    for number in range(1, 5)
)

JOURNEYS = (
    {
        "slug": "complete",
        "title": _("Artigo completo"),
        "zip_name": "ric-9999-0001-without-erro.zip",
        "summary": _(
            "Marca o artigo inteiro, revê o que o modelo deixou em aberto "
            "e gera o pacote SPS. O XML e o zip SPS são o gabarito sem "
            "CRITICAL, ERROR ou WARNING."
        ),
        "files": (
            {
                "name": "ric-9999-0001-without-erro.docx",
                "label": _("DOCX fonte"),
            },
            {
                "name": "ric-9999-0001-without-erro.xml",
                "label": _("Gabarito XML SPS"),
            },
            {
                "name": "ric-9999-0001-without-erro-sps.zip",
                "label": _("Gabarito pacote SPS"),
            },
            *FIGURES,
        ),
    },
    {
        "slug": "findings",
        "title": _("Artigo com erros na validação"),
        "zip_name": "ric-9999-0001-with-erro.zip",
        "summary": _(
            "O mesmo artigo com uma falha plantada: sem a data Accepted. "
            "O XML e o zip SPS são o gabarito depois de corrigir essa falha."
        ),
        "files": (
            {
                "name": "ric-9999-0001-with-erro.docx",
                "label": _("DOCX fonte"),
            },
            {
                "name": "ric-9999-0001-with-erro.xml",
                "label": _("Gabarito XML SPS"),
            },
            {
                "name": "ric-9999-0001-with-erro-sps.zip",
                "label": _("Gabarito pacote SPS"),
            },
            *FIGURES,
        ),
    },
    {
        "slug": "references",
        "title": _("Tipos de referência"),
        "zip_name": "ric-9999-0001-referencias.zip",
        "summary": _(
            "Duzentas referências fictícias, em dezesseis tipos SPS e oito "
            "estilos: Vancouver, APA, MLA, ABNT, Chicago, IEEE, Harvard e "
            "ISO 690. O XML e o zip SPS são o gabarito com o publication-type "
            "de cada uma."
        ),
        "files": (
            {
                "name": "ric-9999-0001-referencias.docx",
                "label": _("DOCX fonte"),
            },
            {
                "name": "ric-9999-0001-referencias.xml",
                "label": _("Gabarito XML SPS"),
            },
            {
                "name": "ric-9999-0001-referencias-sps.zip",
                "label": _("Gabarito pacote SPS"),
            },
            *FIGURES,
        ),
    },
    {
        "slug": "manual",
        "title": _("Inclusão manual"),
        "zip_name": "ric-9999-0001-manual.zip",
        "summary": _(
            "Sem DOCX. Front, body e referências vêm dos arquivos de texto. "
            "As cinco figuras são as mesmas do artigo completo. O XML e o "
            "zip SPS são o gabarito sem CRITICAL, ERROR ou WARNING."
        ),
        "files": (
            {
                "name": "ric-9999-0001-manual-front.txt",
                "label": _("Texto do front"),
            },
            {
                "name": "ric-9999-0001-manual-body.txt",
                "label": _("Texto do body"),
            },
            {
                "name": "ric-9999-0001-manual-referencias.txt",
                "label": _("Texto das referências"),
            },
            {
                "name": "ric-9999-0001-manual.xml",
                "label": _("Gabarito XML SPS"),
            },
            {
                "name": "ric-9999-0001-manual-sps.zip",
                "label": _("Gabarito pacote SPS"),
            },
            *FIGURES,
        ),
    },
    {
        "slug": "complex",
        "title": _("Equações, tabelas e imagens"),
        "zip_name": "ric-9999-0001-complexo.zip",
        "summary": _(
            "DOCX com cinco equações tipográficas, quatro tabelas densas e "
            "quatro figuras, para treinar a marcação de conteúdo complexo. "
            "O XML e o zip SPS são o gabarito sem CRITICAL, ERROR ou WARNING."
        ),
        "files": (
            {
                "name": "ric-9999-0001-complexo.docx",
                "label": _("DOCX fonte"),
            },
            {
                "name": "ric-9999-0001-complexo.xml",
                "label": _("Gabarito XML SPS"),
            },
            {
                "name": "ric-9999-0001-complexo-sps.zip",
                "label": _("Gabarito pacote SPS"),
            },
            *COMPLEX_FIGURES,
        ),
    },
)

SAMPLE_NAMES = frozenset(
    entry["name"] for journey in JOURNEYS for entry in journey["files"]
)


def sample_path(name):
    if name not in SAMPLE_NAMES or ".." in name.split("/"):
        raise Http404
    path = (SAMPLES_DIR / name).resolve()
    root = SAMPLES_DIR.resolve()
    if root not in path.parents or not path.is_file():
        raise Http404
    return path


def journey_by_slug(slug):
    journey = next((item for item in JOURNEYS if item["slug"] == slug), None)
    if journey is None:
        raise Http404
    return journey


def journey_files(journey):
    return [
        {
            "label": entry["label"],
            "name": entry["name"],
            "url": reverse(
                "manuscript_journey_sample",
                kwargs={"name": entry["name"]},
            ),
        }
        for entry in journey["files"]
    ]


def journey_zip_bytes(journey):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for entry in journey["files"]:
            path = sample_path(entry["name"])
            archive.write(path, arcname=entry["name"])
    return buffer.getvalue()


@require_admin_access
@require_GET
def journey_index(request):
    rows = []
    for index, journey in enumerate(JOURNEYS, start=1):
        rows.append(
            {
                "number": index,
                "menu_label": _("Exemplo %(number)s") % {"number": index},
                "slug": journey["slug"],
                "title": journey["title"],
                "summary": journey["summary"],
                "url": reverse("manuscript_journey_detail", args=[journey["slug"]]),
            }
        )
    return render(
        request,
        "wagtailadmin/manuscript/journeys.html",
        {
            "header_title": _("Exemplos de marcação"),
            "header_icon": "folder-open-inverse",
            "journeys": rows,
            "breadcrumbs_items": [
                {"url": reverse("wagtailadmin_home"), "label": _("Home")},
                {"url": "", "label": _("Exemplos de marcação")},
            ],
        },
    )


@require_admin_access
@require_GET
def journey_detail(request, slug):
    journey = journey_by_slug(slug)
    number = next(
        index for index, item in enumerate(JOURNEYS, start=1) if item["slug"] == slug
    )
    return render(
        request,
        "wagtailadmin/manuscript/journey_detail.html",
        {
            "header_title": _("Exemplo %(number)s") % {"number": number},
            "header_icon": "folder-open-inverse",
            "journey": {
                "number": number,
                "menu_label": _("Exemplo %(number)s") % {"number": number},
                "slug": journey["slug"],
                "title": journey["title"],
                "summary": journey["summary"],
                "files": journey_files(journey),
                "zip_name": journey["zip_name"],
                "zip_url": reverse("manuscript_journey_zip", args=[journey["slug"]]),
            },
            "breadcrumbs_items": [
                {"url": reverse("wagtailadmin_home"), "label": _("Home")},
                {
                    "url": reverse("manuscript_journeys"),
                    "label": _("Exemplos de marcação"),
                },
                {
                    "url": "",
                    "label": _("Exemplo %(number)s") % {"number": number},
                },
            ],
        },
    )


@require_admin_access
@require_GET
def journey_zip(request, slug):
    journey = journey_by_slug(slug)
    payload = journey_zip_bytes(journey)
    response = HttpResponse(payload, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{journey["zip_name"]}"'
    return response


@require_admin_access
@require_GET
def journey_sample(request, name):
    path = sample_path(name)
    if path.suffix == ".docx":
        content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    elif path.suffix == ".txt":
        content_type = "text/plain; charset=utf-8"
    elif path.suffix == ".png":
        content_type = "image/png"
    elif path.suffix == ".xml":
        content_type = "application/xml"
    elif path.suffix == ".zip":
        content_type = "application/zip"
    else:
        content_type = "application/octet-stream"
    return FileResponse(
        path.open("rb"),
        as_attachment=True,
        filename=path.name,
        content_type=content_type,
    )
