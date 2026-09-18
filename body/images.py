import io
import os
import re
import zipfile

from PIL import Image

from body.exceptions import BodyImageError
from body.utils import float_number, iter_content_lists

FIG_FILE_RE = re.compile(r"^fig-(\d+)\.(tif|tiff|jpg|jpeg)$", re.IGNORECASE)
TIFF_EXTS = {"tif", "tiff"}


def parse_figure_filename(name):
    basename = os.path.basename(str(name or "").replace("\\", "/"))
    match = FIG_FILE_RE.match(basename)
    if not match:
        return None
    return str(int(match.group(1))), match.group(2).lower()


def figure_jpeg_bytes(name, data, ext):
    if not data:
        raise BodyImageError(f"Empty image file: {os.path.basename(name)}")
    if ext not in TIFF_EXTS:
        return data
    try:
        image = Image.open(io.BytesIO(data))
        image.seek(0)
        converted = io.BytesIO()
        image.convert("RGB").save(converted, format="JPEG")
        jpeg = converted.getvalue()
        if not jpeg:
            raise BodyImageError(f"Could not convert {os.path.basename(name)} to JPEG.")
        return jpeg
    except BodyImageError:
        raise
    except Exception:
        raise BodyImageError(f"Could not convert {os.path.basename(name)} to JPEG.")


def collect_image_assets(images=None, images_zip=None):
    assets = {}
    for uploaded in images or []:
        name = getattr(uploaded, "name", "") or ""
        parsed = parse_figure_filename(name)
        if parsed is None:
            raise BodyImageError(f"Invalid image filename: {os.path.basename(name)}")
        number, ext = parsed
        if number in assets:
            raise BodyImageError(f"Duplicate figure number: {number}")
        data = uploaded.read()
        if hasattr(uploaded, "seek"):
            uploaded.seek(0)
        jpeg = figure_jpeg_bytes(name, data, ext)
        assets[number] = {
            "href": f"fig-{number}.jpg",
            "bytes": jpeg,
            "original_name": os.path.basename(str(name).replace("\\", "/")),
        }
    if not images_zip:
        return assets
    zip_bytes = images_zip.read()
    if hasattr(images_zip, "seek"):
        images_zip.seek(0)
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise BodyImageError("Invalid zip file.")
    for info in archive.infolist():
        if info.is_dir():
            continue
        parsed = parse_figure_filename(info.filename)
        if parsed is None:
            continue
        number, ext = parsed
        if number in assets:
            raise BodyImageError(f"Duplicate figure number: {number}")
        data = archive.read(info)
        jpeg = figure_jpeg_bytes(info.filename, data, ext)
        assets[number] = {
            "href": f"fig-{number}.jpg",
            "bytes": jpeg,
            "original_name": os.path.basename(info.filename.replace("\\", "/")),
        }
    return assets


def collect_image_hrefs(images=None, images_zip=None):
    assets = collect_image_assets(images, images_zip)
    return {number: asset["href"] for number, asset in assets.items()}


def attach_figure_hrefs(marked, hrefs):
    data = marked if isinstance(marked, dict) else {}
    mapping = hrefs or {}
    for section in data.get("sections") or []:
        for content in iter_content_lists(section):
            for block in content:
                if not isinstance(block, dict):
                    continue
                figs = []
                if block.get("type") == "fig":
                    figs = [block]
                elif block.get("type") == "fig-group":
                    figs = [
                        item
                        for item in (block.get("figs") or [])
                        if isinstance(item, dict)
                    ]
                for fig in figs:
                    number = float_number(fig)
                    if number in mapping:
                        fig["href"] = mapping[number]
    return data
